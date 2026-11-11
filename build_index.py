#!/usr/bin/env python3
"""Embed the training problems into a SQLite index for retrieval (RAG).

    python3 build_index.py                       # data/train.jsonl -> data/index.db
    python3 build_index.py --only-with-options   # skip problems whose options are pictures

Run it once on the board, before the code freeze. Only training problems go
in, so validation problems can never retrieve themselves.
"""
import argparse
import json
import os
import time

from copilot import rag


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--input", default="data/train.jsonl")
    p.add_argument("--db", default="data/index.db")
    p.add_argument("--languages", default="", help="e.g. eng,cat (default: all in the file)")
    p.add_argument("--only-with-options", action="store_true")
    args = p.parse_args()

    languages = set(filter(None, args.languages.split(",")))
    with open(args.input) as f:
        problems = [json.loads(line) for line in f if line.strip()]
    problems = [x for x in problems
                if (not languages or x["language"] in languages)
                and (x.get("options") or not args.only_with_options)]
    if os.path.exists(args.db):
        os.remove(args.db)

    start = time.perf_counter()
    for done in rag.build(args.db, problems):
        rate = done / (time.perf_counter() - start)
        print(f"\r{done}/{len(problems)} problems embedded, {rate:.1f}/s", end="", flush=True)
    size = os.path.getsize(args.db) / 1e6
    print(f"\nWrote {args.db} ({size:.1f} MB) in {time.perf_counter() - start:.0f} s")


if __name__ == "__main__":
    main()
