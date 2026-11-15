"""Prompt tokens -> board prefill seconds, by level. Needs a local ollama with qwen3:0.6b
(Qwen-family tokenizer; the board runs Qwen3.5 0.8B, so counts are an approximation).

    uv run --with pandas --with pyarrow --with numpy python3 -I token_budget.py DATA_DIR

Measures real prompt token counts (baseline system prompt + problem + 5 short options)
for a stratified sample, fits tokens ~ a + b*chars, and applies it to every English problem.
"""
import json
import sys
import urllib.request

import numpy as np
import pandas as pd

SYSTEM = ("You solve multiple-choice math competition problems for school students. "
          "Read the problem and the options, then reply with the letter of the correct option.")
OPTS = "\nA) 12\nB) 15\nC) 18\nD) 20\nE) 24\nAnswer:"
PREFILL, GEN, LIMIT, MARGIN = 11.0, 5.5, 60.0, 3.0

df = pd.read_parquet(f"{sys.argv[1]}/m3kang_text.parquet")
eng = df[(df.split == "high_quality") & (df.language == "eng")].drop_duplicates("id").copy()
eng["chars"] = eng.text.str.strip().str.len()
sample = eng.groupby("level", group_keys=False).apply(lambda g: g.sample(10, random_state=0))


def count(text):
    body = json.dumps({"model": "qwen3:0.6b", "prompt": text, "system": SYSTEM, "stream": False,
                       "think": False, "options": {"num_predict": 1, "temperature": 0}}).encode()
    req = urllib.request.Request("http://127.0.0.1:11434/api/generate", body, {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=120))["prompt_eval_count"]


sample["tokens"] = [count(t.strip() + OPTS) for t in sample.text]
b, a = np.polyfit(sample.chars, sample.tokens, 1)
print(f"fit: tokens = {a:.1f} + {b:.3f} * chars   (n={len(sample)}, measured)")
eng["tokens"] = a + b * eng.chars
eng["prefill_s"] = eng.tokens / PREFILL
# One RAG example = problem + options + answer; a typical example costs the median problem's tokens minus system prompt.
ex_tokens = float((eng.tokens - a).median() + 10)
out = eng.groupby("level").agg(chars=("chars", "median"), tokens=("tokens", "median"),
                               prefill_s=("prefill_s", "median"), p95_prefill_s=("prefill_s", lambda s: s.quantile(.95)))
out["rag_examples_fit_p95"] = ((LIMIT - MARGIN - out.p95_prefill_s - 1 / GEN) * PREFILL // ex_tokens).astype(int)
out["gen_tokens_left_p95"] = ((LIMIT - MARGIN - out.p95_prefill_s) * GEN).astype(int)
print(out.round(1).to_string())
print(f"one RAG example ~ {ex_tokens:.0f} tokens ~ {ex_tokens / PREFILL:.1f} s prefill (estimate)")
