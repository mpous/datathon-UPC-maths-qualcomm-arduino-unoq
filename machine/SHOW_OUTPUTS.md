# See what the Qwen model writes: `machine/show_outputs.py`

The script sends problems to a running `llama-server` and prints, for each problem:
- the problem and its options
- the model's **full reply**
- the letter we read from it, and the **correct letter**, with ✓ or ✗
- how long it took
- in letter mode, the model's probability for each letter A–E

It also saves everything to `results/outputs-<mode>-<time>.jsonl` (for analysis) and a readable `.md` next to it. It needs only the Python standard library, and works from any folder on Windows, Linux, macOS and the board. Paths are relative to the repository root.

## 1. Start a model server

**On the board**, the service is already running on port 8081, so skip this step.

**On a laptop**, start `llama-server` with the same model and flags as the board:

```bash
llama-server -m models/Qwen_Qwen3.5-0.8B-Q8_0.gguf --host 127.0.0.1 --port 8081 \
  --ctx-size 4096 --parallel 1 --cache-ram 0 --jinja --reasoning off --reasoning-budget 0
```

On Windows it's the same command with `llama-server.exe` on one line.

To use the board's server from your laptop over USB, run `adb forward tcp:8081 tcp:8081` first.

## 2. Run it (from the repository root)

```bash
# 10 problems from data/val.jsonl, one letter each (what predict.py does today)
python3 machine/show_outputs.py

# The 50 practice problems from Discord (after prepare_m3kang.py), Catalan only, step-by-step reasoning
python3 machine/show_outputs.py --input data/demo/train.jsonl --language cat --mode reason --limit 10

# The model writes Python; we run it and match the printed value to an option
python3 machine/show_outputs.py --input data/demo/train.jsonl --mode python --run-code --limit 10

# Specific problems only, without printing the problem text
python3 machine/show_outputs.py --ids lvl-0_2026_2,lvl-3_2026_7 --quiet
```

On Windows use `python` instead of `python3`.

## Options

| Option | Default | What it does |
| --- | --- | --- |
| `--input` | `data/val.jsonl` | jsonl of problems, relative to the repo root or absolute |
| `--mode` | `letter` | `letter` = one letter + probabilities; `reason` = step-by-step, then "Answer: X"; `python` = writes code |
| `--limit` | `10` | how many problems (`0` = all) |
| `--ids` | | comma-separated problem ids |
| `--language` | | only `eng` or `cat` |
| `--max-tokens` | `300` | reply length in `reason` and `python` modes |
| `--run-code` | off | `python` mode: run the model's code (5 s limit, isolated process). It is untrusted code, so leave it off if you're unsure |
| `--url` | `127.0.0.1:<LLM_PORT>` from `config.env` | a different server, e.g. `http://127.0.0.1:18081/v1/chat/completions` |
| `--timeout` | `300` | seconds per request (the official limit is 60; this script is for looking, not scoring) |
| `--quiet` | off | don't print the problem text |

## Example output

```
[1/1] lvl-0_2026_2 (eng, level 0): model B | correct B ✓ | 13.2 s
--- reply
def kangaroo_jump(n): ...
print(kangaroo_jump(10))
--- code printed '10' -> option B (ran)
```

The last line is a summary: problems, right/total, mean seconds, how often each letter was chosen.

## Things to know

- On the board, `reason` and `python` replies take time: the model writes ~6 tokens per second, so 300 tokens is ~50 s.
- Temperature is 0 and the seed is fixed, so the same problem gives the same reply every time.
- `results/` is in `.gitignore`. Don't commit outputs on M3Kang problems: the dataset is for research use only.
