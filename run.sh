#!/bin/zsh
# run.sh — launch SaveThisVideo
cd "$(dirname "$0")"

if [[ ! -d .venv ]]; then
  echo "Run ./setup.sh first."
  exit 1
fi

.venv/bin/python app.py
