#!/usr/bin/env bash
# Download and build llama.cpp at the pinned commit. Takes a while on the board.
source "$(dirname "$0")/common.sh"

short="${LLAMA_CPP_REF:0:7}"

if [ -x "$LLAMA_SERVER" ] && "$LLAMA_SERVER" --version 2>&1 | grep -q "$short"; then
  ok "llama-server is already built at commit $short. Nothing to do."
  exit 0
fi

step "Getting llama.cpp at commit $short"
if [ ! -d "$LLAMA_CPP_DIR/.git" ]; then
  # Fetch only this one commit: much smaller than a full clone
  git init -q "$LLAMA_CPP_DIR"
  git -C "$LLAMA_CPP_DIR" remote add origin "$LLAMA_CPP_REPO"
fi
git -C "$LLAMA_CPP_DIR" fetch --depth 1 origin "$LLAMA_CPP_REF"
git -C "$LLAMA_CPP_DIR" checkout -q --detach FETCH_HEAD
ok "source at $(git -C "$LLAMA_CPP_DIR" rev-parse --short HEAD)"

step "Configuring (GGML_NATIVE uses the NEON instructions of the Cortex-A53)"
cmake -S "$LLAMA_CPP_DIR" -B "$LLAMA_CPP_DIR/build" -DGGML_NATIVE=ON -DCMAKE_BUILD_TYPE=Release

step "Building llama-server and llama-cli with 4 cores (go get a coffee)"
start=$(date +%s)
cmake --build "$LLAMA_CPP_DIR/build" --config Release -j4 --target llama-server llama-cli
ok "built in $(( ($(date +%s) - start) / 60 )) minutes"

"$LLAMA_SERVER" --version 2>&1 | grep -m1 version
ok "Next: ./board/03_download_models.sh"
