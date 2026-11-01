#!/usr/bin/env bash
set -euo pipefail
# Called only by the serialized simulation workflow, before/after a paid attempt.
# Persist market data first; a failed upload must prevent the paid attempt.
python3 scripts/database_s3.py push
git config user.name 'github-actions[bot]'
git config user.email '41898282+github-actions[bot]@users.noreply.github.com'
git add data/simulation frontend/public/data data/stocks/benchmarks
if ! git diff --cached --quiet; then
  git commit -m 'Checkpoint paper portfolio simulation'
  git pull --rebase origin main
  git push origin HEAD:main
fi
