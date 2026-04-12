#!/bin/zsh
# setup.sh — first-time setup for SaveThisVideo

set -e
cd "$(dirname "$0")"

echo "→ Checking for Python 3.10+..."
if ! python3 -c "import sys; assert sys.version_info >= (3,10)" 2>/dev/null; then
  echo "  ERROR: Python 3.10 or newer is required."
  echo "  Install via: brew install python"
  exit 1
fi
echo "  OK ($(python3 --version))"

echo "→ Checking for ffmpeg..."
if ! command -v ffmpeg &>/dev/null; then
  echo "  ffmpeg not found. Installing via Homebrew..."
  if ! command -v brew &>/dev/null; then
    echo "  ERROR: Homebrew is required to install ffmpeg."
    echo "  Install Homebrew first: https://brew.sh"
    exit 1
  fi
  brew install ffmpeg
else
  echo "  OK ($(ffmpeg -version 2>&1 | head -1))"
fi

echo "→ Creating virtual environment..."
python3 -m venv .venv
echo "  OK"

echo "→ Installing Python dependencies..."
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -r requirements.txt
echo "  OK"

echo ""
echo "✓ Setup complete. Run the app with:"
echo "    ./run.sh"
