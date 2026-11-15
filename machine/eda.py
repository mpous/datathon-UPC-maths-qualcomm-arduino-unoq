"""EDA + no-model baselines for M3Kang (text columns only).

    uv run --with pandas --with pyarrow --with scikit-learn python3 -I eda.py DATA_DIR OUT_DIR

DATA_DIR/m3kang_text.parquet comes from fetch_text.py.
Writes a few CSVs and charts to OUT_DIR and prints the key numbers.
"""
import hashlib
import json
import sys
from collections import Counter

import numpy as np
import pandas as pd

data_dir, out = sys.argv[1], sys.argv[2]
df = pd.read_parquet(f"{data_dir}/m3kang_text.parquet")
df["year"] = df["id"].str.split("_").str[1].astype(int)
df["qnum"] = df["id"].str.split("_").str[2].astype(int)
df["label"] = df["label"].str.strip()
R = {}

def pr(title, obj):
    print(f"\n== {title}\n{obj}")

# ---------- sizes ----------
pr("rows per split", df.groupby("split").size())
pr("unique ids per split", df.groupby("split")["id"].nunique())
R["rows"] = df.groupby("split").size().to_dict()
R["unique_ids"] = df.groupby("split")["id"].nunique().to_dict()
R["n_languages"] = df.groupby("split")["language"].nunique().to_dict()
langs = df.groupby(["split", "language"]).size().unstack(0).fillna(0).astype(int)
langs = langs.sort_values("high_quality", ascending=False)
langs.to_csv(f"{out}/rows_by_language.csv")
pr("top languages", langs.head(15))
for l in ("eng", "cat", "esp", "spa", "fra"):
    if l in langs.index:
        R[f"rows_{l}"] = langs.loc[l].to_dict()

hq = df[df.split == "high_quality"]
eng = hq[hq.language == "eng"].drop_duplicates("id").copy()
R["eng_unique_ids"] = int(eng.id.nunique())
pr("eng by level", eng.groupby("level").size())
pr("eng by year", eng.groupby("year").size())
R["eng_by_level"] = eng.groupby("level").size().to_dict()
R["eng_by_year"] = eng.groupby("year").size().to_dict()
R["text_only_frac_eng"] = round(float(eng.text_only.mean()), 3)
R["text_only_frac_by_level"] = eng.groupby("level").text_only.mean().round(3).to_dict()

# label consistency: same id -> same label in every language?
cons = df.groupby("id")["label"].nunique()
R["ids_with_inconsistent_label_across_langs"] = int((cons > 1).sum())
langs_per_id = hq.groupby("id")["language"].nunique()
R["hq_languages_per_id"] = {"mean": round(float(langs_per_id.mean()), 1),
                            "min": int(langs_per_id.min()), "max": int(langs_per_id.max())}
std_langs_per_id = df[df.split == "standard"].groupby("id")["language"].nunique()
R["std_languages_per_id"] = {"mean": round(float(std_langs_per_id.mean()), 1)}

# ---------- letter prior (per unique problem, not per translation) ----------
lab = eng.label.value_counts(normalize=True).sort_index()
pr("eng label distribution (unique problems)", lab.round(3))
R["label_dist_unique"] = lab.round(3).to_dict()
R["label_dist_rows_hq"] = hq.label.value_counts(normalize=True).sort_index().round(3).to_dict()
bylev = pd.crosstab(eng.level, eng.label, normalize="index").round(3)
pr("label by level", bylev)
bylev.to_csv(f"{out}/label_by_level.csv")
eng["band"] = pd.cut(eng.qnum, [0, 8, 16, 30], labels=["q1-8", "q9-16", "q17+"])
pr("label by question band", pd.crosstab(eng.band, eng.label, normalize="index").round(3))
byyear = pd.crosstab(eng.year, eng.label, normalize="index").round(2)
byyear.to_csv(f"{out}/label_by_year.csv")

# ---------- text length -> prefill seconds ----------
hq_len = hq.assign(chars=hq.text.str.len())
lens = hq_len.groupby("language").chars.describe()[["mean", "50%", "max"]]
pr("chars per problem text, eng/cat", lens.loc[[l for l in ("eng", "cat") if l in lens.index]])
R["chars_eng"] = {k: round(float(v)) for k, v in eng.text.str.len().describe()[["mean", "50%", "max"]].items()}

# ---------- official split (sha256(id) % 1000 < 150) ----------
def is_val(i):
    return int(hashlib.sha256(i.encode()).hexdigest(), 16) % 1000 < 150
eng["val"] = eng.id.map(is_val)
tr, va = eng[~eng.val], eng[eng.val]
R["official_split_eng"] = {"train": len(tr), "val": len(va)}

def acc(pred, truth):
    return round(100 * float((np.asarray(pred) == np.asarray(truth)).mean()), 1)

B = {}
B["random (expected)"] = 20.0
for L in "ABCDE":
    B[f"always {L}"] = acc([L] * len(va), va.label)
top = tr.label.value_counts().idxmax()
B[f"train-majority ({top})"] = acc([top] * len(va), va.label)
lvl_major = tr.groupby("level").label.agg(lambda s: s.value_counts().idxmax())
B["per-level majority"] = acc(va.level.map(lvl_major).fillna(top), va.label)
tr_band = pd.cut(tr.qnum, [0, 8, 16, 30], labels=False)
va_band = pd.cut(va.qnum, [0, 8, 16, 30], labels=False)
lb = tr.assign(b=tr_band).groupby(["level", "b"]).label.agg(lambda s: s.value_counts().idxmax())
B["per-(level, q-band) majority"] = acc([lb.get((l, b), top) for l, b in zip(va.level, va_band)], va.label)
# year-holdout: train <=2023, test 2024
t2, v2 = eng[eng.year < 2024], eng[eng.year == 2024]
top2 = t2.label.value_counts().idxmax()
B[f"year-holdout 2024: train-majority ({top2})"] = acc([top2] * len(v2), v2.label)
lm2 = t2.groupby("level").label.agg(lambda s: s.value_counts().idxmax())
B["year-holdout 2024: per-level majority"] = acc(v2.level.map(lm2).fillna(top2), v2.label)

# ---------- leakage 1: cross-language ids ----------
# Under the official split, no id is on both sides (by construction). Under a
# random row split, or if the hidden test is drawn from M3Kang rows, translations leak.
hq_rows = hq.copy()
hq_rows["val"] = hq_rows.id.map(is_val)
# if a test row's id has ANY other-language row in the bank, label lookup is exact:
R["leak_if_test_from_m3kang"] = "every id has rows in %.1f languages on average (HQ); id->label is identical across languages: %d inconsistent ids" % (
    langs_per_id.mean(), int((cons > 1).sum()))

# ---------- leakage 2: same problem, different id (reused across levels/years) ----------
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.neighbors import NearestNeighbors
import re
def norm(t):
    t = re.sub(r"^\s*\d+\.\s*", "", t)  # drop "11. "
    return re.sub(r"\s+", " ", t.lower()).strip()
eng["norm"] = eng.text.map(norm)
vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=2, sublinear_tf=True)
X = vec.fit_transform(eng.norm)
Xtr, Xva = X[~eng.val.values], X[eng.val.values]
nn = NearestNeighbors(n_neighbors=1, metric="cosine").fit(Xtr)
d, idx = nn.kneighbors(Xva)
sim = 1 - d[:, 0]
nn_label = tr.label.values[idx[:, 0]]
nn_id = tr.id.values[idx[:, 0]]
res = va.assign(sim=sim, nn_label=nn_label, nn_id=nn_id)
rows = []
for th in (0.95, 0.9, 0.8, 0.7, 0.6, 0.5):
    m = res.sim >= th
    rows.append({"threshold": th, "val_covered": int(m.sum()), "coverage_%": round(100 * m.mean(), 1),
                 "nn_label_acc_%": acc(res[m].nn_label, res[m].label) if m.any() else None})
leak = pd.DataFrame(rows)
pr("cross-id near-duplicates (eng, official split): val problem -> nearest train problem", leak)
leak.to_csv(f"{out}/near_dup_leak.csv", index=False)
res.sort_values("sim", ascending=False)[["id", "nn_id", "sim", "label", "nn_label", "text"]].head(40).to_csv(
    f"{out}/near_dup_examples.csv", index=False)
R["near_dup"] = rows

# hybrid: copy NN label if sim >= th else per-level majority
for th in (0.9, 0.8, 0.7):
    pred = np.where(res.sim >= th, res.nn_label, res.level.map(lvl_major).fillna(top))
    B[f"NN-copy if sim>={th} else per-level majority"] = acc(pred, res.label)

# all-pairs: how many distinct ids have a near-twin anywhere in the dataset (all years)
nn2 = NearestNeighbors(n_neighbors=2, metric="cosine").fit(X)
d2, i2 = nn2.kneighbors(X)
s2 = 1 - d2[:, 1]
twin_lab_same = eng.label.values == eng.label.values[i2[:, 1]]
R["ids_with_near_twin_ge_0.9"] = int((s2 >= 0.9).sum())
R["ids_with_near_twin_ge_0.9_same_label_%"] = round(100 * float(twin_lab_same[s2 >= 0.9].mean()), 1) if (s2 >= 0.9).any() else None
R["ids_with_near_twin_ge_0.8"] = int((s2 >= 0.8).sum())

pr("BASELINES on official eng val (n=%d unique problems; year-holdout n=%d)" % (len(va), len(v2)),
   pd.Series(B))
R["baselines"] = B
R["n_val_eng"] = len(va)
R["n_val_2024"] = len(v2)
json.dump(R, open(f"{out}/summary.json", "w"), indent=1, default=str)

# ---------- charts ----------
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
fig, axes = plt.subplots(1, 2, figsize=(12, 4.2))
ax = axes[0]
bl = pd.crosstab(eng.level, eng.label, normalize="index")
bottom = np.zeros(len(bl))
colors = ["#4C78A8", "#F58518", "#54A24B", "#E45756", "#72B7B2"]
for L, c in zip("ABCDE", colors):
    ax.bar(bl.index.astype(str), bl[L], bottom=bottom, color=c, label=L)
    bottom += bl[L].values
ax.axhline(0.2, color="k", lw=0.5, ls=":")
ax.set_title("Answer letter share by level (unique English problems)")
ax.set_xlabel("level (0 = grade 5)"); ax.legend(ncol=5, loc="upper center", bbox_to_anchor=(0.5, -0.15), frameon=False)
ax = axes[1]
names = list(B.keys())
vals = [B[n] for n in names]
ax.barh(names, vals, color=["#E45756" if "NN" in n else "#4C78A8" for n in names])
ax.axvline(22.5, color="k", ls="--", lw=1); ax.text(22.7, -0.6, "Qwen 0.8B\nbaseline 22.5%", fontsize=7)
ax.set_xlabel("accuracy % on held-out English problems"); ax.set_title("No-model baselines")
ax.invert_yaxis(); ax.tick_params(axis="y", labelsize=7)
plt.tight_layout(); plt.savefig(f"{out}/baselines.png", dpi=130)
print("\nwrote", out)
