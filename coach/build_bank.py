#!/usr/bin/env python3
"""Build the problem bank for the Teach copilot from the retrieval index.

    python3 coach/build_bank.py

Reads data/index.db (step 12) and writes data/teach.db with:

- problems: every text-only problem whose five options OCR could read, so a
  student can solve it from the page alone. One row per language.
- neighbours: for each problem, the most similar other problems.

The multilingual bridge: bge-small is an English embedding model, so the
similarity always comes from the English text. A Catalan student gets the
neighbours of the English twin (same id), shown in Catalan.

Standard library only. The search is a plain loop: about a minute on the board.
"""
import argparse
import json
import os
import sqlite3
import sys
import time
from array import array

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from copilot.config import ROOT  # noqa: E402

KEEP = 40  # neighbours stored per problem

SCHEMA = """
CREATE TABLE problems (
    id TEXT NOT NULL, language TEXT NOT NULL, level INTEGER NOT NULL,
    problem TEXT NOT NULL,          -- the full problem as JSON
    PRIMARY KEY (id, language)
);
CREATE TABLE neighbours (
    id TEXT NOT NULL, other TEXT NOT NULL, score REAL NOT NULL,
    PRIMARY KEY (id, other)
);
"""


def usable(problem):
    options = problem.get("options") or {}
    return problem.get("text_only") and all(options.get(letter) for letter in "ABCDE")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--index", default="data/index.db")
    p.add_argument("--out", default="data/teach.db")
    args = p.parse_args()
    os.chdir(ROOT)

    source = sqlite3.connect(args.index)
    problems, vectors = [], {}
    for _key, text, blob in source.execute("SELECT key, problem, vec FROM problems"):
        problem = json.loads(text)
        if not usable(problem):
            continue
        problems.append(problem)
        if problem["language"] == "eng":
            vec = array("f")
            vec.frombytes(blob)
            vectors[problem["id"]] = vec
    source.close()

    # Keep only the problems that have an English twin to search with
    problems = [x for x in problems if x["id"] in vectors]
    ids = sorted(vectors)
    print(f"{len(problems)} problems, {len(ids)} with an English vector")

    if os.path.exists(args.out):
        os.remove(args.out)
    db = sqlite3.connect(args.out)
    db.executescript(SCHEMA)
    db.executemany("INSERT INTO problems VALUES (?, ?, ?, ?)", [
        (x["id"], x["language"], x["level"], json.dumps(x, ensure_ascii=False)) for x in problems])

    start = time.perf_counter()
    for n, a in enumerate(ids, 1):
        va = vectors[a]
        scored = [(sum(x * y for x, y in zip(va, vectors[b])), b) for b in ids if b != a]
        scored.sort(reverse=True)
        db.executemany("INSERT INTO neighbours VALUES (?, ?, ?)",
                       [(a, b, round(score, 4)) for score, b in scored[:KEEP]])
        if n % 50 == 0 or n == len(ids):
            print(f"\r{n}/{len(ids)} neighbours", end="", flush=True)
    db.commit()
    db.close()
    print(f"\nWrote {args.out} in {time.perf_counter() - start:.0f} s")


if __name__ == "__main__":
    main()
