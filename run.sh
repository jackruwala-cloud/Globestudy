#!/usr/bin/env bash
# Convenience launcher. Usage: ./run.sh [web|admin|build|freshness]
set -euo pipefail
cd "$(dirname "$0")"

# Prefer the local venv if present.
if [ -x ".venv/bin/python" ]; then
  PY=".venv/bin/python"
else
  PY="python3"
fi

cmd="${1:-web}"
case "$cmd" in
  build)     exec "$PY" -m ingestion.build_index ;;
  freshness) shift || true; exec "$PY" -m sources.check_freshness "$@" ;;
  web)       exec "$PY" -m streamlit run web_ui/app.py ;;
  admin)     exec "$PY" -m streamlit run admin/app.py --server.port 8502 ;;
  api)       exec "$PY" -m uvicorn api.main:app --port 8000 --reload ;;
  *) echo "Usage: ./run.sh [web|admin|api|build|freshness]"; exit 1 ;;
esac
