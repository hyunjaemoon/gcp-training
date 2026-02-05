#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 1. Create Python virtual env if it doesn't exist
if [ ! -d "venv" ]; then
  python3 -m venv venv
fi

# 2. Activate venv and install requirements
source venv/bin/activate
pip install -r requirements.txt

# 3. Build the React app (install deps if needed, then build)
if [ -d "ui" ]; then
  (cd ui && npm install && npm run build)
fi

# 4. Run the server
python server.py
