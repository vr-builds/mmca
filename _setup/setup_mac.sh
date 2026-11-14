#!/usr/bin/env bash
# One-time setup for MMCA on macOS. Run from anywhere:  bash _setup/setup_mac.sh
set -euo pipefail
cd "$(dirname "$0")/.."

echo "→ Installing VS Code and GitHub Actions config"
mkdir -p .vscode .github/workflows
cp -n _setup/vscode/*.json .vscode/ || true
cp -n _setup/github/workflows/build.yml .github/workflows/ || true

echo "→ Creating virtual environment (.venv)"
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip -q
.venv/bin/pip install -r requirements-dev.txt -q

echo "→ Running tests"
.venv/bin/python -m pytest -q

echo
echo "✅ Done. Open the folder in VS Code:  code ."
echo "   Then Run and Debug → 'MMCA: Web app (Streamlit)'"
echo "   or in the terminal:  .venv/bin/streamlit run app/streamlit_app.py"
