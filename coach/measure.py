#!/usr/bin/env python3
"""Measure the Teach copilot with numbers: speed, hint quality, and simulated students.

    python3 coach/measure.py

1. Speed: how long each step takes on this machine (run it on the board).
2. The first rung: how often there's an easier, similar problem, and how similar it is.
3. The model's hints and live answers: how many passed the checks, and why the others didn't.
4. Simulated students: one who is always right up to a level and always wrong
   above it. Does the trainer settle at that level, and stay on topic?

Nothing here uses the language model, and the students' real profile isn't touched.
"""
import argparse
import json
import os
import sqlite3
import statistics
import sys
import tempfile
import time
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from copilot.config import ROOT  # noqa: E402
from coach.core import LEVELS, RUNGS, TWIN, Bank, Trainer  # noqa: E402


def scratch_trainer(bank):
    return Trainer(bank, os.path.join(tempfile.mkdtemp(), "profile.db"))


def timed(times, name, function, *args):
    start = time.perf_counter()
    result = function(*args)
    times.setdefault(name, []).append(1000 * (time.perf_counter() - start))
    return result


def speed(bank, rounds=60):
    """Every step a student can take, timed."""
    trainer, times = scratch_trainer(bank), {}
    for n in range(rounds):
        name, language = f"s{n}", bank.languages[n % len(bank.languages)]
        problem = timed(times, "start", trainer.start, name, language, n % 8)["problem"]
        label = bank.problems[(problem["id"], language)]["label"]
        wrong = next(letter for letter in "ABCDE" if letter != label)
        timed(times, "answer", trainer.answer, name, problem["id"], wrong)
        for _ in problem["ladder"][:-1]:
            timed(times, "hint", trainer.hint, name, problem["id"])
        timed(times, "answer", trainer.answer, name, problem["id"], label)
        timed(times, "next", trainer.next, name)
        timed(times, "progress", trainer.progress, name)
    return {step: {"median_ms": round(statistics.median(v), 2), "worst_ms": round(max(v), 2), "calls": len(v)}
            for step, v in times.items()}


def first_rung(bank):
    """The easier, similar problem: how often it exists, and how good it is."""
    out = {}
    for language in bank.languages:
        scores, gaps, same_topic, lower, total = [], [], 0, 0, 0
        for pid, level in bank.level.items():
            if not bank.has(pid, language):
                continue
            total += 1
            found = bank.easier(pid, language)
            if not found:
                continue
            score, other = found
            scores.append(score)
            gaps.append(level - bank.level[other])
            lower += bank.level[other] < level
            same_topic += bank.topic[other] == bank.topic[pid]
        out[language] = {
            "problems": total, "with_a_similar_problem": len(scores),
            "at_a_lower_level": lower, "same_topic": same_topic,
            "median_similarity": round(statistics.median(scores), 3),
            "lowest_similarity": round(min(scores), 3),
            "median_levels_easier": statistics.median(gaps)}
    return out


def hints(bank):
    db = sqlite3.connect(bank.path)
    try:
        rows = db.execute("SELECT ok, reason, seconds FROM hints").fetchall()
    except sqlite3.OperationalError:
        rows = []
    db.close()
    if not rows:
        return {"written": 0}
    reasons = Counter(reason.split(":")[0] if not reason.startswith("human") else "a person rejected it"
                      for ok, reason, _s in rows if not ok)
    return {"written": len(rows), "passed": sum(r[0] for r in rows),
            "rejected_by_the_code_checks": sum(1 for ok, reason, _s in rows if not ok and not reason.startswith("human")),
            "reviewed_by_a_person": sum(1 for _ok, reason, _s in rows if reason.startswith("human")),
            "rejected": dict(reasons), "median_seconds_to_write": round(statistics.median(r[2] for r in rows), 1)}


def live_asks(profile_path):
    """The questions students asked the model live, from the real profile on this machine."""
    if not os.path.exists(profile_path):
        return {"asked": 0}
    db = sqlite3.connect(profile_path)
    try:
        rows = db.execute("SELECT ok, reason, seconds FROM asks").fetchall()
    except sqlite3.OperationalError:
        rows = []
    db.close()
    if not rows:
        return {"asked": 0}
    seconds = [r[2] for r in rows]
    return {"asked": len(rows), "shown_to_the_student": sum(r[0] for r in rows),
            "replaced_by_the_method_tip": dict(Counter(r[1].split(":")[0] for r in rows if not r[0])),
            "median_seconds": round(statistics.median(seconds), 1), "worst_seconds": max(seconds)}


def simulate(bank, ability, language, start_level, problems=30):
    """A student who is right at the first try up to `ability`, and needs the whole ladder above it."""
    trainer, name = scratch_trainer(bank), "sim"
    step = trainer.start(name, language, start_level)
    path, on_topic, after_fail = [], 0, 0
    last_topic, failed = None, False
    for _ in range(problems):
        problem, level = step["problem"], step["level"]
        path.append(level)
        if failed:
            after_fail += 1
            on_topic += problem["topic"] == last_topic
        if level <= ability:
            trainer.answer(name, problem["id"], bank.problems[(problem["id"], language)]["label"])
            failed = False
        else:
            for _rung in problem["ladder"]:
                trainer.hint(name, problem["id"])
            failed = True
        last_topic = problem["topic"]
        step = trainer.next(name)
    tail = path[-10:]
    return {"ability": ability, "start": start_level, "language": language, "path": path,
            "mean_level_last_10": round(statistics.mean(tail), 2),
            "problems_to_reach_ability": next((i for i, lvl in enumerate(path) if lvl == ability), None),
            "same_topic_after_a_failure": f"{on_topic}/{after_fail}"}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--bank", default="data/teach.db")
    p.add_argument("--profile", default="data/teach_profile.db", help="read only, for the live questions")
    p.add_argument("--out", default="results/teach-measure.json")
    args = p.parse_args()
    os.chdir(ROOT)
    bank = Bank(args.bank)

    report = {
        "bank": {"problems": len(bank.level), "rows": len(bank.problems), "languages": bank.languages,
                 "per_level": dict(sorted(Counter(bank.level.values()).items())),
                 "per_topic": dict(Counter(bank.topic.values()).most_common()),
                 "twin_threshold": TWIN, "rungs": list(RUNGS), "levels": [min(LEVELS), max(LEVELS)]},
        "speed": speed(bank),
        "first_rung": first_rung(bank),
        "model_hints": hints(bank),
        "live_questions": live_asks(args.profile),
        "simulated_students": [simulate(bank, ability, language, start)
                               for ability, start in ((1, 4), (3, 0), (5, 2), (6, 7))
                               for language in bank.languages],
    }
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"Bank: {report['bank']['problems']} problems, per level {report['bank']['per_level']}")
    print(f"      per topic {report['bank']['per_topic']}")
    print("\nSpeed (no language model in the loop):")
    for step, t in report["speed"].items():
        print(f"  {step:9} median {t['median_ms']:7.2f} ms   worst {t['worst_ms']:7.2f} ms   ({t['calls']} calls)")
    print("\nFirst rung, the easier similar problem:")
    for language, r in report["first_rung"].items():
        n = r["problems"]
        print(f"  {language}: found for {r['with_a_similar_problem']}/{n}, at a lower level {r['at_a_lower_level']}/{n}, "
              f"same topic {r['same_topic']}/{r['with_a_similar_problem']}, median similarity {r['median_similarity']}, "
              f"median {r['median_levels_easier']} levels easier")
    print(f"\nModel hints: {report['model_hints']}")
    print(f"Live questions to the coach: {report['live_questions']}")
    print("\nSimulated students (right up to their ability, wrong above it):")
    for s in report["simulated_students"]:
        print(f"  ability {s['ability']}, start {s['start']}, {s['language']}: last 10 at level {s['mean_level_last_10']}, "
              f"reached in {s['problems_to_reach_ability']} problems, same topic after a failure "
              f"{s['same_topic_after_a_failure']}\n      path {''.join(map(str, s['path']))}")
    print(f"\nSaved: {args.out}")


if __name__ == "__main__":
    main()
