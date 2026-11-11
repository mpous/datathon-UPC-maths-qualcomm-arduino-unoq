#!/usr/bin/env bash
# Check the whole pipeline end to end: both servers, one embedding, and the
# baseline answering the five sample problems.
source "$(dirname "$0")/common.sh"
cd "$REPO_DIR"

step "Servers"
curl -sf "http://127.0.0.1:$LLM_PORT/health" >/dev/null && ok "LLM server answers on port $LLM_PORT" \
  || die "LLM server is down. Start it: sudo systemctl start math-llm"
curl -sf "http://127.0.0.1:$EMBED_PORT/health" >/dev/null && ok "embedding server answers on port $EMBED_PORT" \
  || die "embedding server is down. Start it: sudo systemctl start math-embed"

step "One embedding"
python3 - <<'PY'
import time
from copilot.embed import embed
t = time.perf_counter()
a, b, c = embed(["A triangle has three sides.", "Every triangle has three edges.", "I like pizza."])
dot = lambda x, y: sum(i * j for i, j in zip(x, y))
print(f"  {len(a)} dimensions in {time.perf_counter() - t:.2f} s")
print(f"  similar pair: {dot(a, b):.2f}   unrelated pair: {dot(a, c):.2f}")
assert len(a) == 384 and dot(a, b) > dot(a, c) + 0.1, "the embeddings look wrong"
PY
ok "embeddings look right"

step "Baseline on the 5 sample problems"
python3 predict.py --input data/sample_problems.jsonl --output results/smoke.csv
python3 - <<'PY'
import csv, json
truth = {p["id"]: p["label"] for p in map(json.loads, open("data/sample_problems.jsonl"))}
rows = list(csv.DictReader(open("results/smoke.csv")))
right = sum(r["answer"] == truth[r["id"]] for r in rows)
worst = max(float(r["seconds"]) for r in rows)
print(f"  {right}/{len(rows)} correct, worst latency {worst:.1f} s")
assert all(r["answer"] in "ABCDE" and len(r["answer"]) == 1 for r in rows), "invalid output"
assert worst < 60, "too slow"
PY
ok "the minimum pipeline works. Next: prepare M3Kang on your laptop (README, step 8)"
