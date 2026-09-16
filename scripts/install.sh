#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
command -v python3 >/dev/null
command -v codex >/dev/null
command -v git >/dev/null
codex plugin marketplace add "$ROOT"
codex plugin add astra-autopilot@astra-autopilot-marketplace
echo 'Plugin installed. Start a new Codex session. For standalone CLI: pipx install .'
