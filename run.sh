#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [[ ! -x "$SCRIPT_DIR/.venv/bin/python" ]]; then
  echo "Missing virtualenv. Run: ./bootstrap.sh" >&2
  exit 1
fi

exec "$SCRIPT_DIR/.venv/bin/python" case_report_pipeline.py \
  --input input_pdfs \
  --txt-out output/txt \
  --csv-out output/case_reports.csv \
  "$@"
