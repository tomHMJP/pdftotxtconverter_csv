#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

python3 -m venv .venv

"$SCRIPT_DIR/.venv/bin/python" -m pip install --upgrade pip
"$SCRIPT_DIR/.venv/bin/python" -m pip install -r requirements.txt

mkdir -p input_pdfs output/txt

cat <<'EOF'
Setup complete.

Next:
  Put PDFs into: input_pdfs/
  Run:
    .venv/bin/python case_report_pipeline.py --input input_pdfs --txt-out output/txt --csv-out output/case_reports.csv
EOF
