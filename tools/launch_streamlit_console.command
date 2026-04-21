#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "$REPO_ROOT"

echo "Starting Amazon Listing Streamlit console..."
.venv/bin/python tools/streamlit_launcher.py start

echo
echo "Opening browser..."
open "http://127.0.0.1:8501"

echo
echo "Console URL: http://127.0.0.1:8501"
echo "Log file: ${REPO_ROOT}/output/debug/streamlit_console.log"
echo
echo "You can close this Terminal window after the page opens."
