#!/usr/bin/env python3
"""Summarise lab.py runs: accuracy, letter-bias calibration, splits by options/level, board time.

    python3 -I qualcomm/analyse.py base        # reads <LAB_OUT>/base-*.jsonl, writes base-summary.json
"""
import json
import math
import os
import sys
from collections import Counter, defaultdict
from paths import ROOT

OUT = os.environ.get("LAB_OUT", f"{ROOT}/lab")
LETTERS = "ABCDE"

def load(name):
    path = f"{OUT}/{name}.jsonl"
    return [json.loads(line) for line in open(path)] if os.path.exists(path) else None


def acc(recs, pred):
    return 100 * sum(pred(r) == r["label"] for r in recs) / len(recs) if recs else float("nan")


def ci(p, n):
    return 196 * math.sqrt(max(p / 100 * (1 - p / 100), 1e-9) / n)


def main():
    tag = sys.argv[1] if len(sys.argv) > 1 else "base"
    train = load(f"{tag}-letter-train")
    summary = {"tag": tag, "runs": {}}

    # letter bias learned on TRAIN only: mean log-prob the model gives each letter
    bias = {c: 0.0 for c in LETTERS}
    prior = defaultdict(lambda: {c: 0.2 for c in LETTERS})
    if train:
        bias = {c: sum(r["lp"][c] for r in train) / len(train) for c in LETTERS}
        by_level = defaultdict(Counter)
        for r in train:
            by_level[r["level"]][r["label"]] += 1
        for level, cnt in by_level.items():
            n = sum(cnt.values())
            prior[level] = {c: (cnt[c] + 2) / (n + 10) for c in LETTERS}
        summary["letter_bias_train"] = {c: round(v, 2) for c, v in bias.items()}

    def raw(r):
        return max(LETTERS, key=lambda c: r["lp"][c])

    def cal(r):
        return max(LETTERS, key=lambda c: r["lp"][c] - bias[c])

    def cal_prior(r):
        return max(LETTERS, key=lambda c: r["lp"][c] - bias[c] + math.log(prior[r["level"]][c]))

    def level_majority(r):
        return max(LETTERS, key=lambda c: prior[r["level"]][c])

    for variant in ("letter", "rag1", "rag2", "cot", "pot"):
        recs = load(f"{tag}-{variant}")
        if not recs:
            continue
        n = len(recs)
        row = {"n": n,
               "raw": round(acc(recs, raw), 1),
               "calibrated": round(acc(recs, cal), 1),
               "calibrated_plus_level_prior": round(acc(recs, cal_prior), 1),
               "ci95": round(ci(acc(recs, raw), n), 1),
               "with_options": round(acc([r for r in recs if r["has_options"]], raw), 1),
               "n_with_options": sum(r["has_options"] for r in recs),
               "without_options": round(acc([r for r in recs if not r["has_options"]], raw), 1),
               "cal_with_options": round(acc([r for r in recs if r["has_options"]], cal), 1),
               "cal_without_options": round(acc([r for r in recs if not r["has_options"]], cal), 1),
               "pred_letters_raw": dict(Counter(raw(r) for r in recs)),
               "pred_letters_cal": dict(Counter(cal(r) for r in recs)),
               "board_s_mean": round(sum(r["board_s"] for r in recs) / n, 1),
               "board_s_p95": sorted(r["board_s"] for r in recs)[int(0.95 * n)],
               "board_s_max": max(r["board_s"] for r in recs),
               "by_level_cal": {lv: round(acc([r for r in recs if r["level"] == lv], cal), 1)
                                for lv in sorted({r["level"] for r in recs})}}
        if variant == "letter":
            row["level_majority_baseline"] = round(acc(recs, level_majority), 1)
            row["always_D"] = round(acc(recs, lambda r: "D"), 1)
        if variant == "pot":
            num = [r for r in recs if r.get("numeric_options")]
            evald = [r for r in num if r.get("value") is not None]
            matched = [r for r in num if r.get("match")]
            row.update({
                "n_numeric_options": len(num), "n_expr_evaluated": len(evald), "n_value_matches_option": len(matched),
                "acc_when_matched": round(acc(matched, lambda r: r["match"]), 1) if matched else None,
                "letter_cal_on_same_matched": round(acc(matched, cal), 1) if matched else None,
                "pot_else_cal": round(acc(recs, lambda r: r.get("match") or cal(r)), 1),
            })
        summary["runs"][variant] = row
    with open(f"{OUT}/{tag}-summary.json", "w") as f:
        json.dump(summary, f, indent=1)
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
