#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Kill all background jobs on exit
trap 'kill 0' EXIT

# Activate venv (create if needed)
if [ ! -d "venv" ]; then
  python3 -m venv venv
fi
source venv/bin/activate
pip install -q -r requirements.txt

# Install UI dependencies if needed
(cd ui && npm install --silent)

echo ""
echo "  Flask backend:  http://localhost:8080"
echo "  Vite dev (HMR): http://localhost:5173  ← open this"
echo ""

# Start Flask in background
python server.py &

# Start Vite dev server in foreground
cd ui && npm run dev
