#!/usr/bin/env bash
set -uo pipefail
cd /home/david/foedus/.worktrees/feature/M-foedus-canonical-rerun-haiku
OUT=docs/research/2026-07-10-canonical-haiku-rerun/run
echo "CAMPAIGN START: $(date -Is)" | tee "$OUT/timing.log"
S=$(date +%s)
# WORKERS=3 (all 3 LLM seats concurrent) per David's pre-seal spec amendment
# 2026-07-10 -- see docs/research/2026-07-10-canonical-haiku-rerun/README.md.
# Belt-and-suspenders auth strip (the claude-cli client already strips
# ANTHROPIC_API_KEY/ANTHROPIC_AUTH_TOKEN per-call in _subprocess_env; this
# keeps a stray inherited env var from ever reaching the child either way).
env -u ANTHROPIC_API_KEY -u ANTHROPIC_AUTH_TOKEN \
  PYTHONUNBUFFERED=1 FOEDUS_LLM_CLI_TIMEOUT=300 \
  FOEDUS_PARALLEL_SEATS=1 FOEDUS_PARALLEL_SEATS_WORKERS=3 \
  uv run --extra dev python -u \
  scripts/foedus_canonical_campaign.py \
  --match-id canonical-haiku-2026-07-10 --num-games 8 \
  --backend claude-cli --model haiku \
  --out-dir "$OUT" > "$OUT/run.stdout.log" 2> "$OUT/run.stderr.log"
RC=$?
E=$(date +%s)
echo "CAMPAIGN END: $(date -Is) rc=$RC elapsed=$((E-S))s ($(( (E-S)/3600 ))h$(( ((E-S)%3600)/60 ))m)" | tee -a "$OUT/timing.log"
exit $RC
