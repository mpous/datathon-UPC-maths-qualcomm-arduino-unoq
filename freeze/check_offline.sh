#!/usr/bin/env bash
# Test like the jury: no network, same answers twice, nothing over the time limit.
#
# Turning Wi-Fi off drops SSH, so run this from a USB connection (adb shell):
#   sudo nmcli radio wifi off
#   ./freeze/check_offline.sh                       # the 5 sample problems
#   ./freeze/check_offline.sh data/val.jsonl 20     # the first 20 validation problems
#   sudo nmcli radio wifi on
source "$(dirname "$0")/../board/common.sh"
cd "$REPO_DIR"

input="${1:-data/sample_problems.jsonl}"
count="${2:-0}"
failures=0

step "Network must be off"
if [ -n "$(ip route show default)" ] || curl -s --max-time 5 -o /dev/null https://huggingface.co; then
  fail "the board is online. Turn the network off first: sudo nmcli radio wifi off"
  exit 1
fi
ok "no default route and no internet"

step "Servers must be up"
for port in "$LLM_PORT" "$EMBED_PORT"; do
  if curl -sf "http://127.0.0.1:$port/health" >/dev/null; then ok "port $port"
  else fail "nothing answers on port $port. Check: sudo systemctl status math-llm math-embed"; failures=$((failures+1)); fi
done

problems="results/offline-input.jsonl"
if [ "$count" -gt 0 ]; then head -n "$count" "$input" > "$problems"; else cp "$input" "$problems"; fi
shift $(( $# > 2 ? 2 : $# ))
extra=("$@")   # anything else goes to predict.py, e.g. --rag 1

step "Two runs of predict.py on $(wc -l < "$problems") problems ${extra[*]:-}"
python3 predict.py --input "$problems" --output results/offline-run1.csv "${extra[@]}"
python3 predict.py --input "$problems" --output results/offline-run2.csv "${extra[@]}"

step "Results"
python3 - <<'PY' || failures=$((failures+1))
import csv, sys
from copilot.config import CONFIG
limit = float(CONFIG["TIME_LIMIT_SECONDS"])
a = list(csv.DictReader(open("results/offline-run1.csv")))
b = list(csv.DictReader(open("results/offline-run2.csv")))
diff = [x["id"] for x, y in zip(a, b) if x["answer"] != y["answer"]]
bad = [x["id"] for x in a + b if x["answer"] not in list("ABCDE")]
slow = [x["id"] for x in a + b if float(x["seconds"]) > limit or x["status"] != "ok"]
worst = max(float(x["seconds"]) for x in a + b)
print(f"  answers identical in both runs: {len(a) - len(diff)}/{len(a)}")
print(f"  worst latency: {worst:.1f} s (limit {limit:.0f} s)")
for label, ids in (("different answers", diff), ("invalid answers", bad), ("timeouts or errors", slow)):
    if ids:
        print(f"  FAIL  {label}: {', '.join(sorted(set(ids)))}")
sys.exit(1 if diff or bad or slow else 0)
PY

echo
if [ "$failures" -eq 0 ]; then echo "${GREEN}${BOLD}Offline check passed. Your copilot is ready for the official run.${RESET}"
else echo "${RED}${BOLD}Offline check failed. Fix the problems above before the freeze.${RESET}"; exit 1; fi
