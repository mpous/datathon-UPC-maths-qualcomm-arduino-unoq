#!/usr/bin/env python3
"""Official entry point: answer every problem with one letter, A to E.

    python3 predict.py --input problems.jsonl --output predictions.csv
    python3 predict.py --input problems.jsonl --output predictions.csv --rag 1

Input: one JSON object per line with at least "id" and "text", plus
"options" ({"A": ..., "E": ...}) and "language" when available.
Output: a CSV with id, language, answer, seconds, status.

Rules: runs offline, at most 60 seconds per problem, deterministic.
"""
import argparse
import csv
import json
import os
import sys

from copilot.config import CONFIG
from copilot.pipeline import solve
from copilot.reason import balance

COLUMNS = ["id", "language", "answer", "seconds", "status"]


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--rag", type=int, default=0, metavar="K", help="add K similar solved problems")
    p.add_argument("--index", default="data/index.db")
    p.add_argument("--no-balance", action="store_true", help="keep each problem's own letter (see copilot/reason.py)")
    args = p.parse_args()

    index = None
    if args.rag:
        if not os.path.exists(args.index):
            sys.exit(f"{args.index} not found. Build it first: python3 build_index.py")
        from copilot.rag import Index
        index = Index(args.index)

    with open(args.input, encoding="utf-8") as f:
        problems = [json.loads(line) for line in f if line.strip()]

    # Each answer is written as soon as it exists, so a stopped run still leaves a valid file
    results = []
    with open(args.output, "w", newline="", encoding="utf-8") as out:
        writer = csv.writer(out)
        writer.writerow(COLUMNS)
        for n, problem in enumerate(problems, 1):
            result = solve(problem, index=index, k=args.rag)
            results.append(result)
            writer.writerow([problem["id"], problem.get("language", ""), result["answer"],
                             result["seconds"], result["status"]])
            out.flush()
            print(f"[{n}/{len(problems)}] {problem['id']} -> {result['answer']} "
                  f"in {result['seconds']:.1f} s ({result['status']}, {result.get('how', 'letter')})",
                  file=sys.stderr)

    # Balancing: the answer keys use every letter about equally; the model over-uses A and D
    if CONFIG.get("BALANCE_LETTERS", "1") == "1" and not args.no_balance and len(results) >= 5:
        letters = balance(results)
        changed = sum(a != r["answer"] for a, r in zip(letters, results))
        tmp = args.output + ".tmp"
        with open(tmp, "w", newline="", encoding="utf-8") as out:
            writer = csv.writer(out)
            writer.writerow(COLUMNS)
            for problem, result, letter in zip(problems, results, letters):
                writer.writerow([problem["id"], problem.get("language", ""), letter,
                                 result["seconds"], result["status"]])
        os.replace(tmp, args.output)  # atomic: the file is always complete
        print(f"Balanced the letters: {changed} of {len(results)} answers changed", file=sys.stderr)


if __name__ == "__main__":
    main()
