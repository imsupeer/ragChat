#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

python -m pip install -r requirements-dev.txt
python -m pytest -v

(
  cd frontend
  npm ci
  NEXT_PUBLIC_API_URL=http://localhost:8000 npm run build
)

python scripts/eval.py --skip-generation --fake-embeddings

echo "All local validation checks passed."
