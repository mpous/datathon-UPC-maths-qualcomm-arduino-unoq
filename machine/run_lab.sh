#!/usr/bin/env bash
# Laptop experiment batch: starts 3 LLM servers + 1 embedding server (same flags as the board
# services) and runs every lab.py variant. Usage: run_lab.sh <model.gguf> <tag> [ports]
set -euo pipefail
PRE=~/projects/datathon/board-prefetch
STARTER=~/projects/datathon/qualcomm-starter
HERE="$(cd "$(dirname "$0")" && pwd)"
MODEL=${1:-$PRE/models/Qwen_Qwen3.5-0.8B-Q8_0.gguf}
TAG=${2:-base}
PORTS=${3:-18081,18084,18085}
SRV=$PRE/llama.cpp/build-laptop/bin/llama-server
LOGS=~/projects/datathon/qualcomm-data/lab/logs; mkdir -p "$LOGS"

until [ -s $STARTER/data/val.jsonl ]; do sleep 10; done

for port in ${PORTS//,/ }; do
  curl -sf localhost:$port/health >/dev/null 2>&1 || setsid $SRV -m "$MODEL" --host 127.0.0.1 --port $port \
    --threads 4 --ctx-size 4096 --parallel 1 --cache-ram 0 --ctx-checkpoints 2 --jinja --reasoning off \
    --reasoning-budget 0 --alias qwen > "$LOGS/llm-$TAG-$port.log" 2>&1 < /dev/null &
done
curl -sf localhost:18090/health >/dev/null 2>&1 || setsid $SRV -m $PRE/models/bge-small-en-v1.5-q8_0.gguf \
  --embedding --host 127.0.0.1 --port 18090 --threads 4 --ctx-size 512 --parallel 1 --cache-ram 0 \
  --batch-size 512 --ubatch-size 512 > "$LOGS/embed.log" 2>&1 < /dev/null &
for port in ${PORTS//,/ } 18090; do
  until curl -sf localhost:$port/health >/dev/null 2>&1; do sleep 1; done
done

export EMBED_PORT=18090
if [ ! -s $STARTER/data/index.db ]; then
  (cd $STARTER && python3 build_index.py --languages eng | tail -1); echo
fi
run() { python3 -I "$HERE/lab.py" --ports "$PORTS" "$@"; }
run --variant letter --input val   --name $TAG-letter
run --variant letter --input train --limit 450 --name $TAG-letter-train
run --variant rag --k 1 --input val --name $TAG-rag1
run --variant rag --k 2 --input val --name $TAG-rag2
run --variant cot --input val --name $TAG-cot
run --variant pot --input val --name $TAG-pot
echo "ALL DONE $TAG $(date +%H:%M)"
