#!/usr/bin/env bash
set -uo pipefail
cd /home/david/foedus/.worktrees/feature/M-foedus-canonical-campaign-v1
OUT=docs/research/2026-07-04-canonical-campaign-v1/run
echo "CAMPAIGN START: $(date -Is)" | tee "$OUT/timing.log"
S=$(date +%s)
PYTHONUNBUFFERED=1 FOEDUS_LLM_CLI_TIMEOUT=300 uv run --extra dev python -u \
  scripts/foedus_canonical_campaign.py \
  --match-id canonical-v1-2026-07-04 --num-games 8 \
  --backend claude-cli --model sonnet \
  --out-dir "$OUT" > "$OUT/run.stdout.log" 2> "$OUT/run.stderr.log"
RC=$?
E=$(date +%s)
echo "CAMPAIGN END: $(date -Is) rc=$RC elapsed=$((E-S))s ($(( (E-S)/3600 ))h$(( ((E-S)%3600)/60 ))m)" | tee -a "$OUT/timing.log"
exit $RC
