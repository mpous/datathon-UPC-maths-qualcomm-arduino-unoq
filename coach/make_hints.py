#!/usr/bin/env python3
"""Write the model's one-sentence hints ahead of time, and check each one in code.

    python3 coach/make_hints.py --limit 120

A hint takes the board 10 to 20 seconds to write, too long while a student
waits. So the model writes them in advance, into the hints table of
data/teach.db, and the page shows them instantly. The run can stop and resume.

The model names a method or a first step. It doesn't see the options, and a
hint is rejected when:
- it contains the correct answer's value or a letter, or
- it contains a number that isn't in the problem (the model calculated, and
  small models calculate badly), or
- it's cut off at the length limit.
The checks are core.check_model_text, the same ones a live answer goes through.
Rejected hints are kept with ok = 0, so the rejection rate can be measured.
"""
import argparse
import os
import random
import sqlite3
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from copilot.client import post  # noqa: E402
from copilot.config import CONFIG, ROOT  # noqa: E402
from copilot.llm import URL  # noqa: E402
from coach.core import MAX_CHARS, Bank, check_model_text  # noqa: E402

LANGUAGE = {"eng": "English", "cat": "Catalan"}
SYSTEM = ("You are a maths coach for school students. Give ONE short hint for the problem: "
          "name the method or the first step, in one sentence of at most 25 words. "
          "Do not calculate anything. Do not give any result or the answer. Write the hint in {language}.")
GRAMMAR = f'root ::= [^\\n]{{15,{MAX_CHARS}}}'

SCHEMA = """
CREATE TABLE IF NOT EXISTS hints (
    id TEXT NOT NULL, language TEXT NOT NULL, hint TEXT NOT NULL,
    ok INTEGER NOT NULL, reason TEXT NOT NULL, seconds REAL NOT NULL,
    PRIMARY KEY (id, language)
)"""


def write_hint(problem):
    response = post(URL, {
        "messages": [{"role": "system", "content": SYSTEM.format(language=LANGUAGE[problem["language"]])},
                     {"role": "user", "content": problem["text"].strip()}],
        "grammar": GRAMMAR,
        "max_tokens": 80,
        "temperature": 0,
        "seed": int(CONFIG["SEED"]),
        "cache_prompt": True,
    }, timeout=90)
    return response["choices"][0]["message"]["content"].strip()


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--bank", default="data/teach.db")
    p.add_argument("--limit", type=int, default=120, help="hints to have in total; 0 means every problem")
    args = p.parse_args()
    os.chdir(ROOT)

    bank = Bank(args.bank)
    db = sqlite3.connect(args.bank)
    db.execute(SCHEMA)
    done = {(pid, lang) for pid, lang in db.execute("SELECT id, language FROM hints")}

    # The same order every run: shuffle the ids once, then both languages of each id,
    # so a problem has its hint in Catalan and in English.
    ids = sorted(bank.level)
    random.Random(42).shuffle(ids)
    todo = [(pid, lang) for pid in ids for lang in bank.languages if bank.has(pid, lang)]
    if args.limit:
        todo = todo[:args.limit]

    kept = rejected = 0
    for n, (pid, lang) in enumerate(todo, 1):
        if (pid, lang) in done:
            continue
        problem = bank.problems[(pid, lang)]
        start = time.perf_counter()
        try:
            hint = write_hint(problem)
        except OSError as error:
            print(f"[{n}/{len(todo)}] {pid} {lang}: error {error}", flush=True)
            continue
        seconds = time.perf_counter() - start
        reason = check_model_text(hint, problem)
        kept, rejected = kept + (not reason), rejected + bool(reason)
        db.execute("INSERT OR REPLACE INTO hints VALUES (?, ?, ?, ?, ?, ?)",
                   (pid, lang, hint, int(not reason), reason, round(seconds, 2)))
        db.commit()
        print(f"[{n}/{len(todo)}] {pid} {lang} {seconds:.1f} s {'OK ' if not reason else 'NO (' + reason + ')'}: {hint}",
              flush=True)
    total = db.execute("SELECT COUNT(*), SUM(ok) FROM hints").fetchone()
    print(f"\nThis run: {kept} kept, {rejected} rejected. In the bank: {total[1] or 0} of {total[0]} hints pass the checks.")


if __name__ == "__main__":
    main()
