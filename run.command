#!/usr/bin/env bash
# Double-click this on macOS (or run `./run.command` / `bash run.command`) to
# start the app locally. It sets up a virtual environment on first run,
# installs dependencies, then launches the server and opens your browser.
set -e

# Work from the script's own directory, wherever it's launched from.
cd "$(dirname "$0")"

PORT="${FLASK_PORT:-5050}"
URL="http://127.0.0.1:${PORT}"

# Pick a Python 3 interpreter.
PY="$(command -v python3 || command -v python || true)"
if [ -z "$PY" ]; then
  echo "Python 3 is not installed. Install it from https://www.python.org and re-run."
  exit 1
fi

# Check ffmpeg (required for MP3 conversion).
if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "⚠  ffmpeg is not installed. Install it first:"
  echo "     macOS:  brew install ffmpeg"
  echo "     Ubuntu: sudo apt install ffmpeg"
  exit 1
fi

# Create the virtual environment on first run.
if [ ! -d .venv ]; then
  echo "Setting up (first run only)…"
  "$PY" -m venv .venv
fi

# Install / update dependencies (quiet unless something goes wrong).
./.venv/bin/python -m pip install --quiet --upgrade pip
./.venv/bin/python -m pip install --quiet -r requirements.txt

# First run needs Spotify credentials in .env.
if [ ! -f .env ]; then
  cp .env.example .env
  echo
  echo "Created .env — open it and fill in SPOTIFY_CLIENT_ID and"
  echo "SPOTIFY_CLIENT_SECRET, then run this again."
  exit 1
fi

echo
echo "Starting Spotify → MP3 at ${URL}"
echo "Leave this window open while you use the app. Press Ctrl+C to stop."
echo

# Open the browser shortly after the server starts.
( sleep 2; (open "$URL" 2>/dev/null || xdg-open "$URL" 2>/dev/null || true) ) &

exec ./.venv/bin/python app.py
