#!/usr/bin/env bash
# Install the system packages needed to build llama.cpp. Needs sudo and internet.
source "$(dirname "$0")/common.sh"

PACKAGES=(build-essential cmake git pkg-config libssl-dev curl ca-certificates python3 sqlite3)

step "Updating the package index"
sudo apt-get update

# A package index cut short by a power cut hides packages that do exist.
# If that happens, download the whole index again once.
if ! has_candidate librhash1 || ! has_candidate rpcsvc-proto; then
  warn "the package index looks incomplete. Downloading it again from scratch."
  sudo rm -rf /var/lib/apt/lists/*
  sudo apt-get clean
  sudo apt-get update
fi

step "Installing: ${PACKAGES[*]}"
sudo apt-get install -y "${PACKAGES[@]}"

step "Checking"
cmake --version | head -1
gcc --version | head -1
python3 --version
ok "packages installed. Next: ./board/02_build_llama_cpp.sh"
