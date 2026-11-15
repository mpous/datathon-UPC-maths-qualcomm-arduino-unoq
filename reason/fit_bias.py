#!/usr/bin/env python3
"""Find a correction for the model's letter bias, offline, in seconds.

    python3 reason/fit_bias.py --fit results/logprobs-train.csv --test results/logprobs-val.csv

It reads the log probabilities saved by collect_logprobs.py, learns one offset
per letter on --fit (train), and reports the accuracy on --test (val). Learn
on train, score on val: tuning on the problems you score on inflates the score.

The last method answers the most common train letter when OCR found no options,
because then the model guesses blind.
"""
import argparse
import csv
import math
from collections import Counter

LETTERS = "ABCDE"


def load(path):
    rows = []
    with open(path) as f:
        for r in csv.DictReader(f):
            lp = [float(r[f"lp_{l}"]) for l in LETTERS]
            top = max(lp)
            total = top + math.log(sum(math.exp(x - top) for x in lp))
            r["lp"] = [x - total for x in lp]  # log probabilities over A-E only, summing to 1
            rows.append(r)
    return rows


def predict(row, offsets):
    scores = [lp + b for lp, b in zip(row["lp"], offsets)]
    return LETTERS[scores.index(max(scores))]


def accuracy(rows, offsets):
    return sum(predict(r, offsets) == r["label"] for r in rows) / len(rows)


def center(rows):
    """Subtract each letter's average log probability: no letter is favoured on average."""
    return [-sum(r["lp"][i] for r in rows) / len(rows) for i in range(5)]


def search(rows, start, step=0.1, span=4.0, passes=4):
    """Move one offset at a time to the value that gets the most right on rows."""
    offsets = list(start)
    grid = [round(-span + step * k, 4) for k in range(int(2 * span / step) + 1)]
    for _ in range(passes):
        for i in range(1, 5):  # A stays fixed: only the differences matter
            best = (accuracy(rows, offsets), -abs(offsets[i] - start[i]), offsets[i])
            for delta in grid:
                trial = offsets[:i] + [start[i] + delta] + offsets[i + 1:]
                score = (accuracy(rows, trial), -abs(delta), trial[i])
                if score > best:
                    best = score
            offsets[i] = best[2]
    return offsets


def interval(p, n):
    return 1.96 * math.sqrt(p * (1 - p) / n)  # 95% margin of a proportion


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--fit", required=True, help="CSV to learn the offsets on (train)")
    p.add_argument("--test", required=True, help="CSV to report the accuracy on (val)")
    args = p.parse_args()

    fit, test = load(args.fit), load(args.test)
    with_opts = [r for r in fit if r["has_options"] == "True"]

    centered = center(fit)
    searched = search(fit, centered)
    # Without options the model can't see the choices: its letter is a blind guess.
    # Then the most common answer in train is a better guess.
    prior = Counter(r["label"] for r in fit if r["has_options"] == "False").most_common(1)[0][0]
    searched_opts = search(with_opts, center(with_opts)) if with_opts else searched

    methods = {
        "model as is (grammar)": lambda r: r["answer"],
        "always " + prior: lambda r: prior,
        "centered": lambda r: predict(r, centered),
        "centered + search": lambda r: predict(r, searched),
        "search + prior": lambda r: predict(r, searched_opts) if r["has_options"] == "True" else prior,
    }

    print(f"Fit on {len(fit)} problems, test on {len(test)}\n")
    print(f"{'method':24} {'fit acc':>8} {'test acc':>16}   letters on test (predicted)")
    for name, rule in methods.items():
        acc_fit = sum(rule(r) == r["label"] for r in fit) / len(fit)
        acc_test = sum(rule(r) == r["label"] for r in test) / len(test)
        counts = Counter(rule(r) for r in test)
        letters = " ".join(f"{l}:{counts[l]}" for l in LETTERS)
        print(f"{name:24} {100 * acc_fit:7.1f}% {100 * acc_test:7.1f}% ±{100 * interval(acc_test, len(test)):4.1f}   {letters}")

    truth = Counter(r["label"] for r in test)
    print(f"{'(true letters on test)':24} {'':8} {'':16}   " + " ".join(f"{l}:{truth[l]}" for l in LETTERS))

    print("\nOn test, split by whether OCR found the options:")
    print(f"  {'method':24} {'with options':>14} {'without':>10}")
    for name, rule in methods.items():
        cells = []
        for flag in ("True", "False"):
            group = [r for r in test if r["has_options"] == flag]
            cells.append(f"{sum(rule(r) == r['label'] for r in group)}/{len(group)}")
        print(f"  {name:24} {cells[0]:>14} {cells[1]:>10}")

    print("\nSettings for the copilot (A is the reference, 0):")
    for name, o in (("centered", centered), ("centered + search", searched), ("search + prior", searched_opts)):
        print(f"  {name:18} LETTER_BIAS=" + ",".join(f"{x - o[0]:.2f}" for x in o))
    print(f"  search + prior     NO_OPTIONS_ANSWER={prior}")


if __name__ == "__main__":
    main()
