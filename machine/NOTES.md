# Qualcomm "Math on the Edge": laptop-side evidence (Sat 14 Nov, 12:00–12:45)

Spec: github.com/mpous/datathon-UPC-maths-qualcomm-arduino-unoq (reference clone in `../qualcomm-starter`, not in this repo).
Data: M3Kang text columns only (18 MB parquet in `../qualcomm-data/`, NOT committed; research-only licence).
The images/options were not downloaded: event Wi-Fi gave ~100 KB/s, the full set is 5.8 GB, one HQ shard 393 MB.

Scripts (all `uv run --with ... python3 -I <script> DATA_DIR`):
- `fetch_text.py`: duckdb range-reads only id/language/level/text_only/label/text (no image bytes) from HF.
- `eda.py`: sizes, letter prior, near-duplicate leakage, no-model baselines, `baselines.png`.
- `xlang_leak.py`: if a test problem is a translation of an M3Kang problem, can text matching find it?
- `token_budget.py`: prompt tokens per level via local ollama qwen3:0.6b -> board prefill seconds.

## Data (measured)
- 1,747 unique problems (Catalan Kangaroo 2007–2024, levels 0–7 = grades 5–12), 108 languages.
  `high_quality` 40,617 rows (23 langs/problem on avg), `standard` 108,677 rows (62 langs/problem).
- **Catalan: all 1,747** (as is English). fra 1,427, por 1,369, esp 1,368 in HQ.
- Per level (eng): 142 / 106 / 146 / 123 / 339 / 296 / 305 / 290. Per year: 61–136, rising after 2015.
- Text-only (no figure): 46% overall; 20% at level 0 up to ~55% at levels 5–7. The `text` field has NO options:
  A–E are only in the image. Organisers' README: OCR reads all five options for 62% (74% of text-only).
  I did not re-measure OCR noise (no images downloaded).
- Labels identical across languages for every id (0 inconsistent).

## Letter prior (unique problems)
A 16.0 / B 19.9 / C 21.8 / **D 24.7** / E 17.6 %. Strongest at levels 0–1: D 33–36%, A only 6–7%.
Levels 2–7 are close to flat (D 22–26%).

## No-model baselines (official split = sha256(id) 15% val, 281 English problems)
| method | acc |
|---|---|
| random | 20.0 |
| always D (= train majority) | 23.1 |
| per-level majority letter | **24.6** |
| per-(level, question band) majority | 21.4 |
| copy label of nearest train problem if TF-IDF sim ≥0.9, else per-level majority | 26.0 |
| year holdout 2024 (n=114): always D / per-level majority | 28.1 / 28.9 |

Organisers' Qwen3.5 0.8B baseline = 22.5% on 40 problems (95% CI roughly ±13 pp, so it is not distinguishable
from always-D). Any Reason claim needs ≥250 val problems to separate 5 pp differences.

## Leakage
1. Cross-language, same id: the official prep script splits by id, so its val has 0 leakage by construction.
   But IF the hidden test is drawn from M3Kang rows (any language), the answer is recoverable:
   a crude no-model matcher (TF-IDF on numbers + char n-grams, against the English bank) finds the same problem
   top-1 for cat 86% / esp 91% / fra 92% / ita 85% / deu 80% / zho 52% / arb 41%, giving label accuracy
   cat 89.5% / esp 92% / fra 94%. If the test file carries M3Kang-style ids (`lvl-L_YEAR_N`), an id lookup is 100%.
   A multilingual embedding would close the zho/arb gap. **Ask the organisers whether the hidden test comes from
   M3Kang or from new problems (e.g. Kangaroo 2025), and whether retrieving a test problem's own translation is allowed.**
2. Same problem, different id (Kangaroo reuses problems across adjacent levels in the same year):
   82 problems have a near-twin (sim ≥0.9), 138 at ≥0.8. Copying the twin's *letter* is right only 56–67%:
   option order changes between levels. Copying the twin's *answer value* and finding it among this problem's
   options (needs OCR'd options) should be far better. Covers ~3% of val at sim ≥0.9, so worth ≈+1–2 pp.

## Time budget (estimate from measured token counts)
Baseline prompt (system + problem + 5 short options) = 86 + 0.23·chars tokens with a Qwen tokenizer
(measured on 80 problems): median ~130 tokens, 95th pct ~16 s prefill at 11 tok/s, on every level.
Organisers measured 9 s/problem and ~30 s with 2 RAG examples, so ~3–4 retrieved examples is the ceiling.
Lever: llama-server `cache_prompt` reuses an unchanged prefix, so a FIXED few-shot block is paid once,
retrieved examples are paid every problem.

## Laptop model check
ollama + qwen3:0.6b already installed and runs (used for token counts). The board's Qwen3.5 0.8B Q8_0 GGUF is 835 MB:
~2 h at event Wi-Fi speed; get it via phone hotspot/USB if we go Qualcomm. Laptop: 12 cores, 31 GB RAM, no GPU,
no llama.cpp built.

## Teach ideas (strongest given the data)
- Catalan hint ladder: student solves in Catalan (all 1,747 present), retrieval via the English twin (same id),
  nearest easier problem from a lower level/near-twin, then a one-line hint. Measure: hint answer-leak rate by code
  on all val; % of retrieved problems with lower level and same topic (hand-label 20); seconds per rung.
- Adaptive trainer with no LM in the loop: problems ordered by level + question number (difficulty proxy), embedding
  clusters as topics, LED matrix tick/cross, SQLite profile. Measure: latency (<1 s), topic coverage, simulated
  learner reaching target level in fewer problems than random order.
- "Same problem, other level" explainer: use the 138 cross-level twins to show how one idea is asked at grade 7 vs 9.
  Measure: twin precision on 30 hand-checked pairs.
