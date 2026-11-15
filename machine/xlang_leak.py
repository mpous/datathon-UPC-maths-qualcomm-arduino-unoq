"""If the hidden test reused M3Kang problems in another language, how often could
we find the same problem (and so its label) in the English bank by text alone?

    uv run --with pandas --with pyarrow --with scikit-learn python3 -I xlang_leak.py DATA_DIR

Cheap, language-agnostic matcher: TF-IDF over the numbers and capitalised names in
the text plus char 3-5-grams (proper names and numbers survive translation).
Reports top-1 id hit rate and the resulting label accuracy per language.
"""
import re
import sys

import numpy as np
import pandas as pd
from scipy.sparse import hstack
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize

df = pd.read_parquet(f"{sys.argv[1]}/m3kang_text.parquet")
df = df[df.split == "high_quality"]
eng = df[df.language == "eng"].drop_duplicates("id").reset_index(drop=True)


def strip(t):
    return re.sub(r"^\s*\d+\.\s*", "", t)


def nums(t):
    return " ".join(re.findall(r"\d+(?:[.,]\d+)?", strip(t))) or "none"


vn = TfidfVectorizer(token_pattern=r"[^ ]+", ngram_range=(1, 2), sublinear_tf=True).fit(eng.text.map(nums))
vc = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True, min_df=2).fit(eng.text.map(strip).str.lower())


def feats(texts):
    a = vn.transform(texts.map(nums))
    b = vc.transform(texts.map(strip).str.lower())
    return normalize(hstack([a * 0.7, b * 0.3]).tocsr())


E = feats(eng.text)
lab = dict(zip(eng.id, eng.label))
rows = []
for lang in ["cat", "esp", "fra", "deu", "ita", "zho", "arb", "rus"]:
    q = df[df.language == lang]
    if q.empty:
        continue
    q = q.sample(min(len(q), 600), random_state=0)
    S = feats(q.text) @ E.T
    best = np.asarray(S.argmax(axis=1)).ravel()
    hit = (eng.id.values[best] == q.id.values)
    lab_ok = np.array([lab[i] for i in eng.id.values[best]]) == q.label.values
    rows.append({"language": lang, "n": len(q), "same_id_top1_%": round(100 * hit.mean(), 1),
                 "label_acc_%": round(100 * lab_ok.mean(), 1)})
print(pd.DataFrame(rows).to_string(index=False))
