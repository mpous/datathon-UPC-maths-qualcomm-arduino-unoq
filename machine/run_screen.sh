#!/usr/bin/env bash
# Quick 100-problem screens (same fixed subset): weight-edited model cot/pot, then thinking mode for both models.
set -euo pipefail
PRE=~/projects/datathon/board-prefetch; SRV=$PRE/llama.cpp/build-laptop/bin/llama-server
HERE="$(cd "$(dirname "$0")" && pwd)"; LOGS=~/projects/datathon/qualcomm-data/lab/logs
run() { python3 -I "$HERE/lab.py" --input val --sample 100 "$@" | grep -v '^  '; }
run --variant cot --ports 18091,18092,18093 --name wsp-cot-s100
run --variant pot --ports 18091,18092,18093 --name wsp-pot-s100
pkill -f 'llama-server.*--port 1808[145]' || true; pkill -f 'llama-server.*--port 1809[123]' || true
think() {  # model tag ports
  for port in ${3//,/ }; do
    setsid $SRV -m "$1" --host 127.0.0.1 --port $port --threads 4 --ctx-size 4096 --parallel 1 --cache-ram 0 \
      --ctx-checkpoints 2 --jinja --reasoning on --reasoning-budget 170 --alias qwen > "$LOGS/think-$2-$port.log" 2>&1 < /dev/null &
  done
  for port in ${3//,/ }; do until curl -sf localhost:$port/health >/dev/null 2>&1; do sleep 1; done; done
  run --variant think --max-tokens 200 --ports "$3" --name $2-think-s100
  pkill -f "llama-server.*--port ${3%%,*}" || true; for port in ${3//,/ }; do pkill -f "llama-server.*--port $port" || true; done
}
think $PRE/models/Qwen3.5-0.8B-WSP-Q8_0.gguf wsp 18094,18095,18096
think $PRE/models/Qwen_Qwen3.5-0.8B-Q8_0.gguf base 18097,18098,18099
echo "SCREEN DONE $(date +%H:%M)"
