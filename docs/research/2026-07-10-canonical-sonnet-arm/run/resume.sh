#!/usr/bin/env bash
set -uo pipefail
cd /home/david/foedus/.worktrees/feature/M-foedus-canonical-sonnet-arm
OUT=docs/research/2026-07-10-canonical-sonnet-arm/run
echo "CAMPAIGN RESUME: $(date -Is)" | tee -a "$OUT/timing.log"
S=$(date +%s)
env -u ANTHROPIC_API_KEY -u ANTHROPIC_AUTH_TOKEN \
  PYTHONUNBUFFERED=1 FOEDUS_LLM_CLI_TIMEOUT=300 \
  FOEDUS_PARALLEL_SEATS=1 FOEDUS_PARALLEL_SEATS_WORKERS=3 \
  uv run --extra dev python -u \
  scripts/foedus_canonical_campaign.py \
  --match-id canonical-sonnet-arm-2026-07-10 --num-games 4 \
  --backend claude-cli --model sonnet \
  --out-dir "$OUT" --resume >> "$OUT/run.stdout.log" 2>> "$OUT/run.stderr.log"
RC=$?
E=$(date +%s)
echo "CAMPAIGN RESUME LEG END: $(date -Is) rc=$RC elapsed=$((E-S))s" | tee -a "$OUT/timing.log"
exit $RC
