#!/usr/bin/env python3
"""Ask the model once per problem and save its log probability for A to E.

    python3 reason/collect_logprobs.py --input data/train.jsonl --limit 300
    python3 reason/collect_logprobs.py --input data/val.jsonl --limit 0

The model is the slow part (about 10 s per problem), so we run it once and save
the numbers. Then reason/fit_bias.py tries many corrections offline, in seconds.
The run can stop and resume: problems already in the output file are skipped.
"""
import argparse
import csv
import json
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from copilot.client import post  # noqa: E402
from copilot.config import CONFIG  # noqa: E402
from copilot.llm import URL, build_messages  # noqa: E402

LETTERS = "ABCDE"
TOP = 300  # raw tokens to ask for: enough for the five letters to appear


def letter_logprobs(problem):
    """Return (grammar answer, {letter: logprob}) for one problem."""
    response = post(URL, {
        "messages": build_messages(problem),
        "grammar": "root ::= [A-E]",
        "max_tokens": 1,
        "temperature": 0,
        "seed": int(CONFIG["SEED"]),
        "cache_prompt": True,
        "logprobs": True,
        "top_logprobs": TOP,
    }, timeout=60)
    choice = response["choices"][0]
    top = choice["logprobs"]["content"][0]["top_logprobs"]
    found = {}
    for t in top:  # sorted, most likely first: keep the first match per letter
        key = t["token"].strip()
        if key in LETTERS and len(key) == 1 and key not in found:
            found[key] = t["logprob"]
    floor = min(t["logprob"] for t in top) - 1.0  # a letter not in the list is less likely than all of them
    return choice["message"]["content"].strip(), {l: found.get(l, floor) for l in LETTERS}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--input", required=True)
    p.add_argument("--limit", type=int, default=300, help="0 means every problem")
    p.add_argument("--output", default="", help="default: results/logprobs-<input name>.csv")
    args = p.parse_args()

    with open(args.input) as f:
        problems = [json.loads(line) for line in f if line.strip()]
    random.Random(42).shuffle(problems)  # the same order as eval.py
    if args.limit:
        problems = problems[:args.limit]

    os.makedirs("results", exist_ok=True)
    name = os.path.splitext(os.path.basename(args.input))[0]
    out_path = args.output or f"results/logprobs-{name}.csv"
    done = set()
    if os.path.exists(out_path):
        with open(out_path) as f:
            done = {r["id"] + "|" + r["language"] for r in csv.DictReader(f)}

    new_file = not os.path.exists(out_path)
    with open(out_path, "a", newline="") as out:
        writer = csv.writer(out)
        if new_file:
            writer.writerow(["id", "language", "level", "has_options", "label", "answer", "seconds"]
                            + [f"lp_{l}" for l in LETTERS])
        for n, problem in enumerate(problems, 1):
            key = problem["id"] + "|" + problem["language"]
            if key in done:
                continue
            start = time.perf_counter()
            try:
                answer, lps = letter_logprobs(problem)
            except Exception as error:  # keep going: one bad problem shouldn't stop a long run
                print(f"[{n}/{len(problems)}] {key}: error {error}", file=sys.stderr, flush=True)
                continue
            seconds = time.perf_counter() - start
            writer.writerow([problem["id"], problem["language"], problem.get("level", ""),
                             bool(problem.get("options")), problem["label"], answer, f"{seconds:.2f}"]
                            + [f"{lps[l]:.4f}" for l in LETTERS])
            out.flush()
            print(f"[{n}/{len(problems)}] {key}: {answer} (truth {problem['label']}) {seconds:.1f} s",
                  flush=True)
    print(f"Saved: {out_path}")


if __name__ == "__main__":
    main()
