#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
export HWF_DATA_DIR="${HWF_DATA_DIR:-$HOME/.handwritefont}"
python3 -m uvicorn hwf.api:app --app-dir backend --host 127.0.0.1 --port 8765
