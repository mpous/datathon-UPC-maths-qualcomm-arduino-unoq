#!/usr/bin/env python3
"""Score a predict.py run against a labelled jsonl, broken down by level, language and answer source.

    python3 machine/score_run.py results/practice-board.csv data/demo/practice.jsonl [results/practice-board.log]

The optional log is predict.py's stderr: it says, per problem, whether the letter came from the model's
Python program ('code') or its letter probabilities ('letter'), and holds the pre-balancing letters.
Prints Markdown tables (accuracy with the number of problems next to it).
"""
import csv
import json
import re
import sys
from collections import Counter, defaultdict


def pct(right, n):
    return f"{100 * right / n:.0f}% ({right}/{n})" if n else "-"


def main():
    pred_path, gold_path = sys.argv[1], sys.argv[2]
    log_path = sys.argv[3] if len(sys.argv) > 3 else None
    gold = {}
    for line in open(gold_path, encoding="utf-8"):
        if line.strip():
            p = json.loads(line)
            gold[(p["id"], p.get("language", ""))] = p
    rows = list(csv.DictReader(open(pred_path, encoding="utf-8")))
    plain, how = [None] * len(rows), ["?"] * len(rows)
    if log_path:
        lines = [l for l in open(log_path, encoding="utf-8") if l.startswith("[")]
        for i, l in enumerate(lines[:len(rows)]):
            m = re.search(r"-> ([A-E]) in .*?\(([^,)]+)(?:, (\w+))?\)", l)
            if m:
                plain[i], how[i] = m.group(1), m.group(3) or "letter"

    def table(title, key):
        groups = defaultdict(list)
        for i, r in enumerate(rows):
            g = gold[(r["id"], r["language"])]
            groups[key(i, g)].append(i)
        print(f"\n| {title} | Final (balanced) | Before balancing | Problems |\n| --- | --- | --- | --- |")
        for k in sorted(groups, key=str):
            idx = groups[k]
            final = sum(rows[i]["answer"] == gold[(rows[i]["id"], rows[i]["language"])]["label"] for i in idx)
            before = sum(plain[i] == gold[(rows[i]["id"], rows[i]["language"])]["label"] for i in idx if plain[i])
            print(f"| {k} | {pct(final, len(idx))} | {pct(before, len(idx)) if any(plain) else '-'} | {len(idx)} |")

    table("All", lambda i, g: "all")
    table("Language", lambda i, g: g.get("language", ""))
    table("Level", lambda i, g: g.get("level"))
    table("Needs the figure", lambda i, g: "yes" if g.get("text_only") is False else "no")
    if any(plain):
        table("Answer source", lambda i, g: how[i])
    secs = [float(r["seconds"]) for r in rows]
    print(f"\nTime per problem: mean {sum(secs) / len(secs):.1f} s, max {max(secs):.1f} s, over 60 s: "
          f"{sum(s > 60 for s in secs)}; status {dict(Counter(r['status'] for r in rows))}")
    print(f"Letters used: final {dict(sorted(Counter(r['answer'] for r in rows).items()))}"
          + (f", before balancing {dict(sorted(Counter(p for p in plain if p).items()))}" if any(plain) else "")
          + f", key {dict(sorted(Counter(gold[(r['id'], r['language'])]['label'] for r in rows).items()))}")


if __name__ == "__main__":
    main()
