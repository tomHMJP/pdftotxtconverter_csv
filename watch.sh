#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [[ ! -x "$SCRIPT_DIR/.venv/bin/python" ]]; then
  echo "Missing virtualenv. Run: ./bootstrap.sh" >&2
  exit 1
fi

INPUT_PATH="input_pdfs"
if [[ ${1-} != "" && "${1-}" != "-"* ]]; then
  if [[ -d "$1" ]]; then
    INPUT_PATH="$1"
    shift
  elif [[ -f "$1" ]]; then
    echo "--watch requires a directory input path." >&2
    exit 1
  fi
fi

exec "$SCRIPT_DIR/.venv/bin/python" case_report_pipeline.py \
  --watch \
  --interval 10 \
  --input "$INPUT_PATH" \
  --txt-out output/txt \
  --csv-out output/case_reports.csv \
  --sync \
  ${1+"$@"}
