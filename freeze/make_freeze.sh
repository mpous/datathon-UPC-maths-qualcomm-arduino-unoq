#!/usr/bin/env bash
# Freeze your submission before the test set is released.
#
#   ./freeze/make_freeze.sh my-team-name
#
# It packs your code and indexes into one archive, records the SHA256 of every
# model you use, and prints one hash. Send that hash to the organizers before
# the deadline. At the official run, they check the board against it.
source "$(dirname "$0")/../board/common.sh"
cd "$REPO_DIR"

team="${1:-}"
[ -n "$team" ] || die "give your team name: ./freeze/make_freeze.sh my-team-name"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
archive="freeze/$team-$stamp.tar.gz"
manifest="freeze/manifest.txt"

step "Checking the code"
if [ -n "$(git status --porcelain --untracked-files=no 2>/dev/null)" ]; then
  warn "you have uncommitted changes. They're included, but commit them so you can find this version later."
fi

step "Hashing the models in $MODELS_DIR"
{
  echo "team: $team"
  echo "frozen_at_utc: $stamp"
  echo "board: $(hostname)"
  echo "repo_commit: $(git rev-parse HEAD 2>/dev/null || echo none)"
  echo "repo_dirty: $([ -n "$(git status --porcelain 2>/dev/null)" ] && echo yes || echo no)"
  echo "llama_server: $("$LLAMA_SERVER" --version 2>&1 | grep -m1 version)"
  echo "python: $(python3 --version)"
  echo "models:"
  for f in "$MODELS_DIR"/*.gguf; do
    echo "  $(sha256sum "$f" | cut -d' ' -f1)  $(basename "$f")"
  done
  echo "services:"
  for unit in math-llm math-embed; do
    echo "  $unit: $(systemctl show -p ExecStart --value "$unit" 2>/dev/null | sed -n 's/.*argv\[\]=\([^;]*\);.*/\1/p')"
  done
} > "$manifest"
cat "$manifest"

step "Packing code, indexes and the manifest (models are recorded by hash, not copied)"
# Everything tracked or new in the repo, plus data/*.db, minus M3Kang text and old freezes
files=$( (git ls-files --cached --others --exclude-standard; ls data/*.db 2>/dev/null; echo "$manifest") \
  | grep -v -E '^data/(train|val)\.jsonl$|^freeze/.*\.tar\.gz$' | sort -u)
# shellcheck disable=SC2086
tar -czf "$archive" $files
hash="$(sha256sum "$archive" | cut -d' ' -f1)"
echo "$hash  $(basename "$archive")" > "$archive.sha256"

echo
ok "archive: $archive ($(du -h "$archive" | cut -f1))"
echo
echo "${BOLD}Send this to the organizers before the freeze deadline:${RESET}"
echo "  team:   $team"
echo "  sha256: $hash"
echo
echo "Then don't change anything on the board: no code, no models, no services."
