#!/usr/bin/env python3
"""Build fine-tuning examples: the exact prompt llama-server sends (reasoning off) -> the answer letter.

    uv run --with duckdb python3 -I qualcomm/make_ft_data.py
Output (not for git, M3Kang is research-only): qualcomm-data/ft/bank.jsonl
English text+options come from the organisers' prepare_m3kang.py output; other languages take their
text from M3Kang and borrow the English options of the same problem id.
"""
import json
import sys
import duckdb
from paths import ROOT

sys.path.insert(0, f"{ROOT}")
from copilot.llm import SYSTEM, format_problem  # noqa: E402

LANGS = sys.argv[1].split(",") if len(sys.argv) > 1 else ["eng", "cat", "esp"]
TEMPLATE = ("<|im_start|>system\n{system}<|im_end|>\n<|im_start|>user\n{user}<|im_end|>\n"
            "<|im_start|>assistant\n<think>\n\n</think>\n\n")  # from llama-server /apply-template

eng = {}
for split in ("train", "val"):
    for line in open(f"{ROOT}/data/{split}.jsonl"):
        r = json.loads(line)
        r["split"] = split
        eng[r["id"]] = r

rows = duckdb.sql(f"""select distinct id, language, text from '{ROOT}/m3kang_text.parquet'
                      where language in ({','.join("'" + x + "'" for x in LANGS)})""").fetchall()
n = 0
with open(f"{ROOT}/ft/bank.jsonl", "w") as f:
    for pid, lang, text in sorted(rows):
        base = eng[pid]
        problem = base if lang == "eng" else {**base, "text": text.strip(), "language": lang}
        prompt = TEMPLATE.format(system=SYSTEM, user=format_problem(problem) + "\nAnswer:")
        f.write(json.dumps({"id": pid, "language": lang, "split": base["split"], "level": base["level"],
                            "label": base["label"], "prompt": prompt}, ensure_ascii=False) + "\n")
        n += 1
print(n, "examples")
