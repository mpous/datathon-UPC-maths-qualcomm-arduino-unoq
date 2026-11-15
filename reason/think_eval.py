#!/usr/bin/env python3
"""Let the model think in a few sentences before it answers, and measure it.

    python3 reason/think_eval.py --input data/demo/train.jsonl --limit 0

One request per problem. A grammar lets the model write one short line of
reasoning (at most MAX_CHARS characters), then forces "Answer: X". Writing is
the slow part on the board (about 6 tokens per second), so the line is capped
to stay inside 60 seconds. Problems already in the output file are skipped.
"""
import argparse
import csv
import json
import os
import random
import re
import socket
import sys
import time
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from copilot.client import post  # noqa: E402
from copilot.config import CONFIG  # noqa: E402
from copilot.llm import URL, format_problem  # noqa: E402

FALLBACK = CONFIG["FALLBACK_ANSWER"]
TIME_LIMIT = float(CONFIG["TIME_LIMIT_SECONDS"])
MARGIN = 3.0
MAX_CHARS = 300  # about 80 tokens of reasoning

SYSTEM = ("You solve multiple-choice math competition problems for school students. "
          "Think about the problem in at most three short sentences on one line, "
          "then give the letter of the correct option as 'Answer: X'.")
GRAMMAR = f'root ::= think "\\nAnswer: " [A-E]\nthink ::= [^\\n]{{1,{MAX_CHARS}}}'


def solve(problem):
    start = time.perf_counter()
    messages = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": format_problem(problem)}]
    try:
        response = post(URL, {
            "messages": messages,
            "grammar": GRAMMAR,
            "max_tokens": 200,
            "temperature": 0,
            "seed": int(CONFIG["SEED"]),
            "cache_prompt": True,
        }, timeout=TIME_LIMIT - MARGIN)
        text = response["choices"][0]["message"]["content"]
        found = re.search(r"Answer: ([A-E])\s*$", text)
        status = "ok" if found else "no answer"
        letter = found.group(1) if found else FALLBACK
        tokens = response.get("usage", {}).get("completion_tokens", 0)
    except (socket.timeout, TimeoutError, urllib.error.URLError) as error:
        text, letter, tokens = "", FALLBACK, 0
        status = "timeout" if "timed out" in str(error) or isinstance(error, (socket.timeout, TimeoutError)) else f"error: {error}"
    return letter, status, text, tokens, time.perf_counter() - start


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--input", required=True)
    p.add_argument("--limit", type=int, default=0, help="0 means every problem")
    p.add_argument("--output", default="", help="default: results/think-<input name>.csv")
    args = p.parse_args()

    with open(args.input) as f:
        problems = [json.loads(line) for line in f if line.strip()]
    random.Random(42).shuffle(problems)
    if args.limit:
        problems = problems[:args.limit]

    os.makedirs("results", exist_ok=True)
    name = os.path.basename(os.path.dirname(args.input)) + "-" + os.path.splitext(os.path.basename(args.input))[0]
    out_path = args.output or f"results/think-{name}.csv"
    done = set()
    if os.path.exists(out_path):
        with open(out_path) as f:
            done = {r["id"] + "|" + r["language"] for r in csv.DictReader(f)}

    new_file = not os.path.exists(out_path)
    right = total = 0
    with open(out_path, "a", newline="") as out:
        writer = csv.writer(out)
        if new_file:
            writer.writerow(["id", "language", "level", "has_options", "label", "answer", "correct",
                             "seconds", "status", "tokens", "reasoning"])
        for n, problem in enumerate(problems, 1):
            key = problem["id"] + "|" + problem["language"]
            if key in done:
                continue
            letter, status, text, tokens, seconds = solve(problem)
            correct = letter == problem["label"]
            right, total = right + correct, total + 1
            writer.writerow([problem["id"], problem["language"], problem.get("level", ""),
                             bool(problem.get("options")), problem["label"], letter, int(correct),
                             f"{seconds:.2f}", status, tokens, text.replace("\n", " ")])
            out.flush()
            print(f"[{n}/{len(problems)}] {key}: {letter} (truth {problem['label']}) {seconds:.1f} s "
                  f"{tokens} tok {status}, running {100 * right / total:.1f}%", flush=True)
    print(f"Saved: {out_path}")


if __name__ == "__main__":
    main()
