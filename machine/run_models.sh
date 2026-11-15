#!/usr/bin/env bash
# Screen other GGUF models with the plain-letter prompt (full val) and short reasoning (100 problems).
# usage: run_models.sh tag:file.gguf [tag:file.gguf ...]   (files in board-prefetch/models)
set -uo pipefail
PRE=~/projects/datathon/board-prefetch; SRV=$PRE/llama.cpp/build-laptop/bin/llama-server
HERE="$(cd "$(dirname "$0")" && pwd)"; LOGS=~/projects/datathon/qualcomm-data/lab/logs
PORTS=18101,18102,18103
for spec in "$@"; do
  tag=${spec%%:*}; file=${spec#*:}
  for port in ${PORTS//,/ }; do
    setsid $SRV -m $PRE/models/$file --host 127.0.0.1 --port $port --threads 4 --ctx-size 4096 --parallel 1 \
      --cache-ram 0 --ctx-checkpoints 2 --jinja --reasoning off --reasoning-budget 0 > $LOGS/llm-$tag-$port.log 2>&1 < /dev/null &
  done
  for port in ${PORTS//,/ }; do
    for i in $(seq 120); do curl -sf localhost:$port/health >/dev/null 2>&1 && break; sleep 1; done
  done
  python3 -I "$HERE/lab.py" --variant letter --input val --ports $PORTS --name $tag-letter | grep -v '^  '
  python3 -I "$HERE/lab.py" --variant cot --input val --sample 100 --ports $PORTS --name $tag-cot-s100 | grep -v '^  '
  for port in ${PORTS//,/ }; do pkill -f "llama-server.*--port $port" || true; done
  sleep 2
done
echo "MODELS DONE $(date +%H:%M)"
