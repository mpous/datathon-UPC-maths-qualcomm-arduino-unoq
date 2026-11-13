---
name: m3kang-copilot
description: Change and measure the Math on the Edge copilot that answers M3Kang (Kangaroo) math problems on the Arduino UNO Q. Covers the predict.py contract, the code in copilot/, retrieval with embeddings, the experiment loop with eval.py and ablations.csv, error analysis by topic, language and level, and teaching features such as hints and adaptive practice. Use it for any change to the prompt, the pipeline, retrieval, or a teaching feature, and for any accuracy or latency question.
---

# Build and measure the M3Kang copilot

The copilot runs on an Arduino UNO Q, offline. A small language model (Qwen3.5 0.8B, port 8081) and an embedding model (bge-small-en-v1.5, port 8082) run as llama.cpp servers. The Python code uses only the standard library. For board operations, use the `unoq-board` skill.

## The contract: never break it

`predict.py` is what the organizers run on the hidden test set:

```bash
python3 predict.py --input data/val.jsonl --output results/predictions.csv [--rag K]
```

Whatever you build, it must keep:

- **One letter, A to E, for every problem.** The CSV has `id`, `language`, `answer`, `seconds`, `status`.
- **At most 60 seconds per problem** (`TIME_LIMIT_SECONDS`). `copilot/pipeline.py` keeps a 3-second margin and answers `FALLBACK_ANSWER` (D) on a timeout or an error.
- **No network.** Only `127.0.0.1` servers. No downloads at run time, no cloud APIs.
- **The same answers every time.** Temperature 0, `SEED` from `config.env`.
- **No new dependencies on the board** unless they're installed by a documented step, and work offline.

After every change, run `python3 predict.py --input data/sample_problems.jsonl --output results/check.csv` and check that every row has a letter.

## The code

| File | What it does |
| --- | --- |
| `copilot/pipeline.py` | `solve(problem, index, k, exclude_id, image_b64)`: one problem in, `{"answer", "seconds", "status", "prompt_tokens", "examples"}` out. Change this first. |
| `copilot/llm.py` | `format_problem`, `build_messages`, `answer_letter`. The grammar `root ::= [A-E]` with `max_tokens: 1` forces one letter. Keep `SYSTEM` stable: `cache_prompt` reuses the start of the prompt. |
| `copilot/rag.py` | `build(db, problems)` and `Index(db).search(problem, k, exclude_id)`, returning `(score, problem)` pairs, best first |
| `copilot/embed.py` | `embed(texts, query=False)`. Queries get the bge prefix from `config.env`; stored documents don't. |
| `copilot/client.py` | `post(url, payload, timeout)` and `get(url)`, JSON over `urllib` |
| `copilot/config.py` | `CONFIG`, parsed from `config.env` |
| `build_index.py` | Embeds `data/train.jsonl` into `data/index.db`. `--only-with-options`, `--languages eng` |
| `eval.py` | Scores against the labels, and logs each run |
| `explorer/server.py` | A web page to try problems one by one, with RAG and the image |

## The data

`data/train.jsonl` and `data/val.jsonl`, one problem per line, split by `id`, so translations of a problem stay on the same side:

```json
{"id": "lvl-0_2015_13", "language": "eng", "level": 0, "year": 2015, "text_only": true,
 "text": "13. For 3 days, ...", "options": {"A": "12", "B": "15", "C": "18", "D": "20", "E": "24"}, "label": "C"}
```

- `options` is `{}` when OCR couldn't read five text options. Then the model only sees the question. OCR reads the options of about 62% of problems.
- The same `id` exists in many languages, Catalan (`cat`) included. bge-small is an English model: search with the English version of a problem when you can.
- There's no topic field. Derive one from embedding clusters, keywords, or hand labels, and say how in the write-up.
- **M3Kang is for research use only.** Never commit `data/*.jsonl`, `data/images/`, or `data/index.db`, and never print whole problem sets into files that get committed.
- Retrieval only ever indexes training problems, and `exclude_id` skips the problem being answered, in every language. Keep both, or the validation score is a lie.

## The time budget

Measured on the board: prefill about 11 tokens per second, generation about 6. Baseline: 9 seconds per problem on average. Two RAG examples: about 30 seconds. One line of reasoning: 26 seconds. Embedding a problem and searching the index: well under a second.

Before you propose a change, estimate its prompt tokens and its time. Prefer work that needs no model: retrieval, Python arithmetic, rules. Use the model for short outputs. Read `timings.prompt_n` from the server response to see what it really read.

## The experiment loop

1. One change per experiment.
2. `python3 eval.py --limit 50 --name <short-name>` on the board. Same 50 problems every time.
3. Read the output: accuracy against always-D (about 25%) and random (20%), latency (mean, median, worst, over the limit), accuracy by language, level, and with or without options, and letter counts.
4. Each run writes `results/eval-<time>-<name>.csv` (per problem: `id`, `language`, `level`, `has_options`, `label`, `answer`, and more) and one line in `results/ablations.csv` with the Git commit.
5. Commit, so the commit in `ablations.csv` points at the code that made the number.
6. Confirm a promising result with `--limit 0` (281 problems, about 45 minutes) before reporting it.

Report the result honestly, including changes that made things worse. On 50 problems, a difference of one or two answers is noise.

The baseline, on 40 English problems with OCR options: 22.5% (9/40), 8.7 seconds on average, with a strong letter bias (21 D and 14 A). Asking for the value instead of the letter, or one line of reasoning, both gave 17.5%.

## Error analysis

The deliverable asks for errors by topic, language, and difficulty (level). Join the `eval-*.csv` rows with `data/val.jsonl` on `id` and `language`. Produce a table per dimension, with the count of problems next to each accuracy, and look at 10 wrong answers one by one, in the explorer, before you explain them.

## Teaching features

The copilot should guide, not hand out answers. Patterns that fit the board:

- **Hint ladder:** a similar, easier solved problem from the index (lower `level`), then the topic of the neighbours, then a one-sentence model hint, then the solution only on request. Check every model hint in code: reject it if it contains the correct option's value.
- **Adaptive practice:** pick the next problem from the nearest neighbours, one level up after a right answer, same topic one level down after a wrong one. No model in the loop. Keep the student profile in SQLite on the board.
- **Debate:** send the problem to the server as soon as it's shown, so `cache_prompt` has it. When the class votes, the model only reads the short request.

Keep teaching code separate from `predict.py`, for example in `copilot/tutor.py`, so the official run never changes by accident. For a web page and the LED matrix, use the `unoq-hardware-ui` skill. Teams use no external modules.
