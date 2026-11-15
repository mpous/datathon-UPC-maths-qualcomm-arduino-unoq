#!/usr/bin/env python3
"""Show what the Qwen model actually writes, problem by problem.

Sends problems to a running llama-server and prints, for each one: the prompt, the model's full reply,
the letter we read from it, the correct letter, and how long it took. Also saves everything to
results/outputs-<mode>-<time>.jsonl and a readable .md next to it.

    python3 machine/show_outputs.py --limit 5
    python3 machine/show_outputs.py --input data/demo/train.jsonl --mode reason --language cat --limit 10
    python3 machine/show_outputs.py --ids lvl-0_2026_2,lvl-3_2026_7 --mode python --run-code

Modes:
  letter  one letter, as predict.py does today; also shows the model's probability for each letter
  reason  the model thinks step by step (up to --max-tokens), then we read "Answer: X"
  python  the model writes a short Python program; with --run-code we run it and match the result to an option

Only the Python standard library. Works from any folder and on Windows, Linux and the board.
The server address comes from config.env (127.0.0.1:LLM_PORT) unless you pass --url.
"""
import argparse
import json
import math
import re
import subprocess
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # machine/show_outputs.py -> repository root
sys.path.insert(0, str(ROOT))
from copilot.client import post  # noqa: E402
from copilot.config import CONFIG  # noqa: E402
from copilot.llm import SYSTEM, format_problem  # noqa: E402

PROMPTS = {
    "letter": SYSTEM,
    "reason": ("You solve multiple-choice math competition problems for school students. Think step by step, "
               "briefly. End with a line 'Answer: X' where X is the letter of the correct option."),
    "python": ("You solve multiple-choice math competition problems for school students. Write a short Python "
               "program that computes the answer and prints only the final value. Reply with the code in a "
               "```python block, then a line 'Answer: X' with the letter you expect."),
}


def ask(url, mode, problem, max_tokens, timeout):
    body = {
        "messages": [{"role": "system", "content": PROMPTS[mode]},
                     {"role": "user", "content": format_problem(problem) + "\nAnswer:" * (mode == "letter")}],
        "temperature": 0,
        "seed": int(CONFIG["SEED"]),
        "max_tokens": 1 if mode == "letter" else max_tokens,
    }
    if mode == "letter":
        body.update({"grammar": "root ::= [A-E]", "logprobs": True, "top_logprobs": 20})
    start = time.perf_counter()
    reply = post(url, body, timeout=timeout)
    seconds = time.perf_counter() - start
    choice = reply["choices"][0]
    text = choice["message"].get("content") or ""
    probs = {}
    if mode == "letter":
        try:
            # The probabilities come from before the A-E grammar, so keep the letters and rescale them to 100%
            for item in choice["logprobs"]["content"][0]["top_logprobs"]:
                token = item["token"].strip()
                if token in tuple("ABCDE") and token not in probs:
                    probs[token] = math.exp(item["logprob"])
            total = sum(probs.values()) or 1
            probs = {k: round(v / total, 3) for k, v in sorted(probs.items(), key=lambda kv: -kv[1])}
        except (KeyError, IndexError, TypeError):
            pass
    return text, probs, seconds, reply.get("timings", {})


def letter_from(text):
    found = re.findall(r"Answer\s*[:：]?\s*\(?([A-E])\b", text)
    if found:
        return found[-1]
    found = re.findall(r"\b([A-E])\b", text)
    return found[-1] if found else ""


def run_code(text, options, timeout=5):
    """Run the model's Python in a separate process (isolated mode, time limit) and match its output."""
    blocks = re.findall(r"```(?:python)?\n(.*?)```", text, re.S)
    if not blocks:
        return "", "", "no code"
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(blocks[0])
    try:
        out = subprocess.run([sys.executable, "-I", f.name], capture_output=True, text=True, timeout=timeout)
        value = (out.stdout.strip().splitlines() or [""])[-1]
        status = "ran" if out.returncode == 0 else "error: " + (out.stderr.strip().splitlines() or ["?"])[-1]
    except subprocess.TimeoutExpired:
        value, status = "", "timeout"
    finally:
        Path(f.name).unlink(missing_ok=True)
    return value, match_option(value, options), status


def match_option(value, options):
    """The letter whose option equals the printed value (numbers compared as numbers), or ''."""
    def num(s):
        try:
            return float(str(s).replace(",", ".").replace("−", "-").strip())
        except ValueError:
            return None
    v = num(value)
    hits = [k for k, o in (options or {}).items()
            if (v is not None and num(o) is not None and abs(num(o) - v) < 1e-6) or str(o).strip() == value.strip()]
    return hits[0] if len(hits) == 1 else ""


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--input", default="data/val.jsonl", help="jsonl of problems, relative to the repo root or absolute")
    p.add_argument("--mode", choices=sorted(PROMPTS), default="letter")
    p.add_argument("--limit", type=int, default=10, help="how many problems (0 = all)")
    p.add_argument("--ids", default="", help="comma-separated problem ids to show")
    p.add_argument("--language", default="", help="only this language, e.g. eng or cat")
    p.add_argument("--max-tokens", type=int, default=300, help="reply length for reason and python modes")
    p.add_argument("--run-code", action="store_true", help="python mode: run the model's code (it's untrusted code!)")
    p.add_argument("--url", default=f"http://127.0.0.1:{CONFIG['LLM_PORT']}/v1/chat/completions")
    p.add_argument("--timeout", type=float, default=300, help="seconds per request (the official limit is 60)")
    p.add_argument("--quiet", action="store_true", help="don't print the prompts")
    args = p.parse_args()

    path = Path(args.input) if Path(args.input).is_absolute() else ROOT / args.input
    problems = [json.loads(line) for line in path.open(encoding="utf-8") if line.strip()]
    if args.language:
        problems = [q for q in problems if q.get("language") == args.language]
    if args.ids:
        wanted = set(args.ids.split(","))
        problems = [q for q in problems if q["id"] in wanted]
    if args.limit:
        problems = problems[:args.limit]

    out_dir = ROOT / "results"
    out_dir.mkdir(exist_ok=True)
    stem = out_dir / f"outputs-{args.mode}-{time.strftime('%Y%m%d-%H%M%S')}"
    rows = []
    with open(f"{stem}.jsonl", "w", encoding="utf-8") as jf, open(f"{stem}.md", "w", encoding="utf-8") as mf:
        mf.write(f"# Model outputs: mode {args.mode}, {path.name}\n\n")
        for n, q in enumerate(problems, 1):
            try:
                text, probs, seconds, timings = ask(args.url, args.mode, q, args.max_tokens, args.timeout)
                error = ""
            except Exception as e:  # keep going: one bad problem shouldn't stop the run
                text, probs, seconds, timings, error = "", {}, 0.0, {}, f"{type(e).__name__}: {e}"
            letter = text.strip() if args.mode == "letter" else letter_from(text)
            row = {"id": q["id"], "language": q.get("language", ""), "level": q.get("level"),
                   "label": q.get("label", ""), "letter": letter, "seconds": round(seconds, 2),
                   "prompt_tokens": timings.get("prompt_n"), "reply_tokens": timings.get("predicted_n"),
                   "probs": probs, "reply": text, "error": error}
            if args.mode == "python" and args.run_code:
                value, code_letter, status = run_code(text, q.get("options"))
                row.update({"code_value": value, "code_letter": code_letter, "code_status": status})
                letter = row["letter"] = code_letter or letter
            rows.append(row)
            jf.write(json.dumps(row, ensure_ascii=False) + "\n")

            mark = "" if not row["label"] else ("✓" if letter == row["label"] else "✗")
            head = (f"[{n}/{len(problems)}] {q['id']} ({row['language']}, level {row['level']}): "
                    f"model {letter or '-'} | correct {row['label'] or '?'} {mark} | {seconds:.1f} s")
            print("=" * 100 + "\n" + head)
            if not args.quiet:
                print("--- problem\n" + format_problem(q))
            print("--- reply\n" + (text.strip() or "(empty)") + (f"\n!!! {error}" if error else ""))
            if probs:
                print("--- letter probabilities: " + "  ".join(f"{k} {v:.0%}" for k, v in probs.items()))
            if "code_status" in row:
                print(f"--- code printed {row['code_value']!r} -> option {row['code_letter'] or 'none'} ({row['code_status']})")
            mf.write(f"## {head}\n\n```\n{format_problem(q)}\n```\n\n**Reply**\n\n```\n{text.strip()}\n```\n\n")
            if probs:
                mf.write("Probabilities: " + ", ".join(f"{k} {v:.0%}" for k, v in probs.items()) + "\n\n")

        labelled = [r for r in rows if r["label"]]
        right = sum(r["letter"] == r["label"] for r in labelled)
        summary = (f"{len(rows)} problems, {right}/{len(labelled)} right"
                   f"{f' ({100 * right / len(labelled):.0f}%)' if labelled else ''}, "
                   f"mean {sum(r['seconds'] for r in rows) / max(len(rows), 1):.1f} s, "
                   f"letters {dict(sorted(Counter(r['letter'] for r in rows).items()))}")
        print("=" * 100 + "\n" + summary + f"\nSaved {stem}.jsonl and {stem}.md")
        mf.write(f"---\n\n**{summary}**\n")


if __name__ == "__main__":
    main()
