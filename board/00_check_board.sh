#!/usr/bin/env bash
# Check that the board is healthy before you install anything. Safe to run any time.
# It changes nothing: it only reads, and tells you how to fix what it finds.
source "$(dirname "$0")/common.sh"
set +e +o pipefail
problems=0

step "Board"
model="$(tr -d '\0' </proc/device-tree/model 2>/dev/null)"
echo "  $model, $(nproc) cores, $(. /etc/os-release; echo "$PRETTY_NAME"), kernel $(uname -r)"
mem_mb=$(awk '/MemTotal/ {printf "%d", $2/1024}' /proc/meminfo)
if [ "$mem_mb" -ge 3000 ]; then ok "RAM: ${mem_mb} MB"
else fail "RAM: ${mem_mb} MB. This kit needs the UNO Q 4 GB."; problems=$((problems+1)); fi

step "Disk"
gb=$(free_gb "$HOME")
if awk "BEGIN {exit !($gb >= 3)}"; then ok "${gb} GB free in $HOME"
else fail "Only ${gb} GB free in $HOME. You need about 3 GB (llama.cpp, models, data)."
     echo "        Free space: sudo apt clean; docker system prune (if you use App Lab apps you don't need)"
     problems=$((problems+1)); fi

step "Clock"
if [ "$(timedatectl show -p NTPSynchronized --value 2>/dev/null)" = "yes" ]; then ok "time is synchronized: $(date)"
else warn "time is not synchronized ($(date)). HTTPS downloads fail if the clock is wrong."
     echo "        Fix: connect to Wi-Fi and wait a minute, or: sudo timedatectl set-ntp true"; fi

step "SSH"
empty_keys=$(find /etc/ssh -name 'ssh_host_*' -size 0 2>/dev/null | wc -l)
if [ "$empty_keys" -gt 0 ]; then
  fail "$empty_keys SSH host key files are empty, so the SSH server can't start."
  echo "        Fix: sudo rm -f /etc/ssh/ssh_host_* && sudo ssh-keygen -A && sudo systemctl restart ssh"
  problems=$((problems+1))
elif systemctl is-active --quiet ssh; then ok "SSH server is running"
else warn "SSH server is not running. Fix: sudo systemctl enable --now ssh"; fi

step "Package index"
# If the apt lists were cut short (for example by a power cut), packages that
# exist in Debian show "Candidate: (none)". These three are good canaries.
missing=""
for pkg in cmake librhash1 rpcsvc-proto; do
  has_candidate "$pkg" || missing="$missing $pkg"
done
if [ -z "$missing" ]; then ok "apt can see the Debian packages this kit needs"
else fail "apt can't find:$missing. The package index is probably incomplete."
     echo "        Fix: sudo rm -rf /var/lib/apt/lists/* && sudo apt clean && sudo apt update"
     problems=$((problems+1)); fi

step "Network (needed for setup only)"
if curl -sI --max-time 8 https://huggingface.co >/dev/null; then ok "huggingface.co is reachable"
else warn "can't reach huggingface.co. You need internet for scripts 01 to 03."; fi

step "What's installed"
if [ -x "$LLAMA_SERVER" ]; then ok "llama-server: $("$LLAMA_SERVER" --version 2>&1 | grep -m1 version)"
else echo "  -     llama.cpp is not built yet (run ./board/02_build_llama_cpp.sh)"; fi
for f in "$LLM_PATH" "$EMBED_PATH"; do
  if [ -f "$f" ]; then ok "model: $(basename "$f") ($(du -h "$f" | cut -f1))"
  else echo "  -     model not downloaded yet: $(basename "$f") (run ./board/03_download_models.sh)"; fi
done
for unit in math-llm math-embed; do
  if systemctl is-active --quiet "$unit" 2>/dev/null; then ok "service $unit is running"
  else echo "  -     service $unit is not running (run ./board/04_install_services.sh)"; fi
done

echo
if [ "$problems" -eq 0 ]; then echo "${GREEN}${BOLD}The board looks healthy.${RESET}"
else echo "${RED}${BOLD}$problems problem(s) to fix first. Run this script again afterwards.${RESET}"; exit 1; fi
