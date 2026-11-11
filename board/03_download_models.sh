#!/usr/bin/env bash
# Download the pinned models and check their SHA256. Safe to run again: it
# resumes partial downloads and skips files that are already correct.
source "$(dirname "$0")/common.sh"

mkdir -p "$MODELS_DIR"

download() {
  local repo="$1" revision="$2" file="$3" sha="$4"
  local target="$MODELS_DIR/$file"
  step "$file"
  if [ -f "$target" ] && echo "$sha  $target" | sha256sum --check --status; then
    ok "already downloaded and verified"
    return
  fi
  local url="https://huggingface.co/$repo/resolve/$revision/$file"
  wget --quiet --show-progress --continue -O "$target.part" "$url"
  echo "  verifying SHA256..."
  if echo "$sha  $target.part" | sha256sum --check --status; then
    mv "$target.part" "$target"
    ok "verified: $(du -h "$target" | cut -f1)"
  else
    rm -f "$target.part"
    die "$file doesn't match its SHA256. Run this script again to download it from scratch."
  fi
}

gb=$(free_gb "$MODELS_DIR")
awk "BEGIN {exit !($gb >= 1.2)}" || die "only ${gb} GB free in $MODELS_DIR; the models need about 0.9 GB."

download "$LLM_REPO" "$LLM_REVISION" "$LLM_FILE" "$LLM_SHA256"
download "$EMBED_REPO" "$EMBED_REVISION" "$EMBED_FILE" "$EMBED_SHA256"

ok "Next: ./board/04_install_services.sh"
