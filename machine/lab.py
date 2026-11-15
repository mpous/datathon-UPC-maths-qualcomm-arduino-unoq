#!/usr/bin/env python3
"""Laptop experiment harness for the Reason side (same model + llama.cpp commit as the board).

Runs one prompt variant over a problem file, sharded over several llama-server instances, and
stores per-problem letter log-probabilities so calibration can be analysed offline (analyse.py).

    python3 -I qualcomm/lab.py --variant letter --input val --name base-letter
    python3 -I qualcomm/lab.py --variant rag --k 2 --input val --name base-rag2
    python3 -I qualcomm/lab.py --variant cot --input val --name base-cot
    python3 -I qualcomm/lab.py --variant pot --input val --name base-pot

Variants
  letter  organisers' exact prompt; read log-probs of A..E for the first token (no generation)
  rag     same, with k retrieved solved problems as examples (organisers' index + bge-small)
  cot     one or two sentences of reasoning (<=60 tokens), then letter log-probs
  pot     model writes one Python expression; we evaluate it and match the value to an option
  think   thinking mode on (server flag) with a token budget, then parse the letter
Board time is estimated from token counts: new prompt tokens / 11.1 + generated tokens / 5.7.
"""
import argparse
import ast
import json
import math
import os
import queue
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from paths import ROOT

STARTER = os.environ.get("STARTER", "{ROOT}")
OUT = os.environ.get("LAB_OUT", "{ROOT}/lab")
sys.path.insert(0, STARTER)
from copilot.client import post  # noqa: E402
from copilot.llm import SYSTEM, build_messages, format_problem  # noqa: E402

LETTERS = "ABCDE"
READ_TPS, WRITE_TPS = 11.1, 5.7  # measured on our board


def chat(url, messages, max_tokens=1, logprobs=True, stop=None):
    payload = {"messages": messages, "max_tokens": max_tokens, "temperature": 0, "seed": 42,
               "cache_prompt": True}
    if logprobs:
        payload.update({"logprobs": True, "top_logprobs": 40})
    if stop:
        payload["stop"] = stop
    r = post(url + "/v1/chat/completions", payload, timeout=300)
    t = r.get("timings", {})
    return r["choices"][0], t.get("prompt_n", 0), t.get("predicted_n", 0)


def letter_logprobs(choice):
    """Log-prob of each letter as the first generated token (-20 if not in the top 40)."""
    lp = {c: -20.0 for c in LETTERS}
    content = (choice.get("logprobs") or {}).get("content") or []
    if content:
        for t in content[0]["top_logprobs"]:
            tok = t["token"].strip()
            if tok in lp:
                lp[tok] = max(lp[tok], t["logprob"])
    return lp


def numeric(text):
    """Value of an option such as '12', '3.5', '1/2', '20 %', '15 cm'; None if not a plain number."""
    m = re.match(r"^\s*([-+−]?\d+(?:[.,]\d+)?)(?:\s*/\s*(\d+))?\s*[^\d\s]{0,6}\s*$", text or "")
    if not m:
        return None
    v = float(m.group(1).replace(",", ".").replace("−", "-"))
    return v / float(m.group(2)) if m.group(2) else v


SAFE_NODES = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant, ast.Call, ast.Name, ast.Load,
              ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow, ast.USub, ast.UAdd,
              ast.Tuple, ast.List)
SAFE_NAMES = {"sqrt", "factorial", "comb", "perm", "gcd", "lcm", "pi", "min", "max", "abs", "round",
              "sum", "floor", "ceil"}


def safe_eval(expr):
    """Evaluate one arithmetic expression in a subprocess; None on anything else."""
    expr = expr.strip().strip("`").split("\n")[0].replace("^", "**").replace("×", "*").replace("÷", "/")
    expr = re.sub(r"^(python|answer|result)\s*[:=]\s*", "", expr, flags=re.I)
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError:
        return None
    for node in ast.walk(tree):
        if not isinstance(node, SAFE_NODES):
            return None
        if isinstance(node, ast.Name) and node.id not in SAFE_NAMES:
            return None
    code = ("from math import *\nimport sys\nsys.set_int_max_str_digits(2000)\n"
            f"v = {expr}\nprint(float(v))")
    try:
        out = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, timeout=2)
        return float(out.stdout.strip()) if out.returncode == 0 else None
    except (subprocess.TimeoutExpired, ValueError):
        return None


def run_one(url, problem, args, index):
    rec = {"id": problem["id"], "language": problem["language"], "level": problem["level"],
           "label": problem["label"], "has_options": bool(problem.get("options")),
           "text_only": problem.get("text_only")}
    t0 = time.perf_counter()
    examples = []
    if args.variant == "rag":
        hits = index.search(problem, k=args.k, exclude_id=problem["id"])
        examples = [p for _s, p in hits]
        rec["retrieved"] = [(p["id"], round(s, 3)) for s, p in hits]
    messages = build_messages(problem, examples)
    read = wrote = 0

    if args.variant in ("letter", "rag"):
        choice, pn, gn = chat(url, messages)
        read, wrote = pn, gn
        rec["lp"] = letter_logprobs(choice)

    elif args.variant == "cot":
        ask = (format_problem(problem) + "\nThink step by step in one or two short sentences, "
               "then give the letter.")
        m = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": ask}]
        c1, pn, gn = chat(url, m, max_tokens=args.max_tokens, logprobs=False)
        thought = c1["message"]["content"].strip()
        m += [{"role": "assistant", "content": thought},
              {"role": "user", "content": "So the letter of the correct option is:"}]
        c2, pn2, gn2 = chat(url, m)
        read, wrote = pn + pn2, gn + gn2
        rec["lp"] = letter_logprobs(c2)
        rec["thought"] = thought

    elif args.variant == "pot":
        opts = {k: numeric(v) for k, v in (problem.get("options") or {}).items()}
        rec["numeric_options"] = len(opts) == 5 and all(v is not None for v in opts.values())
        rec["value"], rec["match"] = None, None
        if rec["numeric_options"]:
            ask = (problem["text"].strip() + "\nWrite one Python arithmetic expression that computes "
                   "the answer. Reply with the expression only, no words.")
            m = [{"role": "system", "content": "You translate math problems into one Python expression."},
                 {"role": "user", "content": ask}]
            c1, pn, gn = chat(url, m, max_tokens=args.max_tokens, logprobs=False, stop=["\n"])
            read, wrote = pn, gn
            rec["expr"] = c1["message"]["content"].strip()
            rec["value"] = safe_eval(rec["expr"])
            if rec["value"] is not None:
                hit = [k for k, v in opts.items() if math.isclose(v, rec["value"], rel_tol=1e-6, abs_tol=1e-6)]
                if len(hit) == 1:
                    rec["match"] = hit[0]
        # always record the plain letter log-probs too, as the fallback
        c2, pn2, gn2 = chat(url, messages)
        read, wrote = read + pn2, wrote + gn2
        rec["lp"] = letter_logprobs(c2)

    elif args.variant == "think":
        # server started with --reasoning on --reasoning-budget N: the model thinks, then answers
        c1, pn, gn = chat(url, messages, max_tokens=args.max_tokens, logprobs=False)
        read, wrote = pn, gn
        content = (c1["message"].get("content") or "").strip()
        m = re.search(r"\b([A-E])\b", content)
        rec["parsed"] = bool(m)
        rec["content"] = content[:200]
        rec["thinking_chars"] = len(c1["message"].get("reasoning_content") or "")
        answer = m.group(1) if m else "D"  # organisers' fallback letter
        rec["lp"] = {c: (0.0 if c == answer else -20.0) for c in LETTERS}

    rec["read_tokens"], rec["written_tokens"] = read, wrote
    rec["board_s"] = round(read / READ_TPS + wrote / WRITE_TPS, 1)
    rec["laptop_s"] = round(time.perf_counter() - t0, 2)
    return rec


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--variant", required=True, choices=["letter", "rag", "cot", "pot", "think"])
    p.add_argument("--input", default="val", help="val, train, or a jsonl path")
    p.add_argument("--languages", default="eng")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--sample", type=int, default=0, help="fixed random subset (seed 0) for quick screens")
    p.add_argument("--k", type=int, default=2)
    p.add_argument("--max-tokens", type=int, default=60)
    p.add_argument("--ports", default="18081,18082,18083")
    p.add_argument("--name", required=True)
    args = p.parse_args()

    path = args.input if args.input.endswith(".jsonl") else f"{STARTER}/data/{args.input}.jsonl"
    langs = set(args.languages.split(","))
    with open(path) as f:
        problems = [json.loads(line) for line in f if line.strip()]
    problems = [x for x in problems if x["language"] in langs]
    if args.limit:
        problems = problems[:args.limit]
    if args.sample and args.sample < len(problems):
        import random
        problems = random.Random(0).sample(problems, args.sample)

    index = None
    if args.variant == "rag":
        from copilot.rag import Index
        index = Index(f"{STARTER}/data/index.db")

    urls = queue.Queue()
    for port in args.ports.split(","):
        urls.put(f"http://127.0.0.1:{port}")

    def work(problem):
        url = urls.get()
        try:
            return run_one(url, problem, args, index)
        finally:
            urls.put(url)

    os.makedirs(OUT, exist_ok=True)
    out = f"{OUT}/{args.name}.jsonl"
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=urls.qsize()) as pool, open(out, "w") as f:
        for n, rec in enumerate(pool.map(work, problems), 1):
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
            if n % 50 == 0:
                print(f"  {n}/{len(problems)} in {time.time() - t0:.0f} s", flush=True)
    recs = [json.loads(line) for line in open(out)]
    acc = sum(max(r["lp"], key=r["lp"].get) == r["label"] for r in recs) / len(recs)
    print(f"{args.name}: n={len(recs)} argmax-letter acc={100 * acc:.1f}% "
          f"mean board_s={sum(r['board_s'] for r in recs) / len(recs):.1f} "
          f"max board_s={max(r['board_s'] for r in recs):.1f} wall={time.time() - t0:.0f}s -> {out}")


if __name__ == "__main__":
    main()
