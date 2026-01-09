#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

REPO_NAME="${1:-$(basename "$SCRIPT_DIR")}"
VISIBILITY="${2:-private}" # private|public|internal

if ! command -v gh >/dev/null 2>&1; then
  echo "Missing GitHub CLI (gh). Install it first: https://cli.github.com/" >&2
  exit 1
fi

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "Not a git repository. Run: git init -b main && git add . && git commit -m \"Initial commit\"" >&2
  exit 1
fi

if ! gh auth status -h github.com >/dev/null 2>&1; then
  cat >&2 <<'EOF'
Not logged into GitHub CLI.

Run:
  gh auth login -h github.com -p https

Then re-run:
  ./publish_github.sh
EOF
  exit 1
fi

if git remote get-url origin >/dev/null 2>&1; then
  git push -u origin main
  exit 0
fi

case "$VISIBILITY" in
  private) VIS_FLAG="--private" ;;
  public) VIS_FLAG="--public" ;;
  internal) VIS_FLAG="--internal" ;;
  *)
    echo "Invalid visibility: $VISIBILITY (use: private|public|internal)" >&2
    exit 1
    ;;
esac

gh repo create "$REPO_NAME" \
  "$VIS_FLAG" \
  --description "Case report PDF -> UTF-8 txt + metadata CSV pipeline" \
  --source . \
  --remote origin \
  --push
