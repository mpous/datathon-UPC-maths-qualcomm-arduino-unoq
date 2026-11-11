# Shared helpers for the board scripts. Source it, don't run it.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=../config.env
source "$REPO_DIR/config.env"

LLAMA_CPP_DIR="${LLAMA_CPP_DIR/#\~/$HOME}"
MODELS_DIR="${MODELS_DIR/#\~/$HOME}"
LLAMA_SERVER="$LLAMA_CPP_DIR/build/bin/llama-server"
LLM_PATH="$MODELS_DIR/$LLM_FILE"
EMBED_PATH="$MODELS_DIR/$EMBED_FILE"

if [ -t 1 ]; then
  GREEN=$'\e[32m'; YELLOW=$'\e[33m'; RED=$'\e[31m'; BOLD=$'\e[1m'; RESET=$'\e[0m'
else
  GREEN=""; YELLOW=""; RED=""; BOLD=""; RESET=""
fi

step() { echo; echo "${BOLD}==> $*${RESET}"; }
ok()   { echo "  ${GREEN}OK${RESET}    $*"; }
warn() { echo "  ${YELLOW}WARN${RESET}  $*"; }
fail() { echo "  ${RED}FAIL${RESET}  $*"; }
die()  { echo; echo "${RED}Error:${RESET} $*" >&2; exit 1; }

# Free space in GB on the filesystem that holds a path
free_gb() { df -Pk "$1" | awk 'NR==2 {printf "%.1f", $4 / 1048576}'; }

# True if apt knows an installable version of a package. Avoids a pipe into
# grep -q, which fails under pipefail when grep exits early.
has_candidate() {
  local out
  out="$(apt-cache policy "$1" 2>/dev/null)"
  [[ "$out" == *"Candidate:"* && "$out" != *"Candidate: (none)"* ]]
}

# Wait until a llama-server answers /health, or give up
wait_for_health() {
  local port="$1" seconds="${2:-120}"
  for _ in $(seq "$seconds"); do
    if curl -sf "http://127.0.0.1:$port/health" >/dev/null 2>&1; then return 0; fi
    sleep 1
  done
  return 1
}
