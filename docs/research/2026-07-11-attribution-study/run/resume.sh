#!/usr/bin/env bash
# Crash-resume leg: continues the sealed match from the completed (banked)
# sweep.jsonl rows on the SAME sealed seeds. Identical env + args to
# launch.sh; safe to run repeatedly (refuses on any seal mismatch).
set -uo pipefail
cd /home/david/foedus/.worktrees/feature/M-foedus-attribution-study
OUT=docs/research/2026-07-11-attribution-study/run
echo $$ > "$OUT/launch.pid"
touch "$OUT/sweep.jsonl" "$OUT/telemetry.jsonl"
echo "CAMPAIGN RESUME: $(date -Is)" | tee -a "$OUT/timing.log"
S=$(date +%s)
# WORKERS=3 (all 3 LLM seats concurrent) is PRE-REGISTERED — README §2.
# Belt-and-suspenders auth strip (ClaudeCLIClient already strips
# ANTHROPIC_API_KEY/ANTHROPIC_AUTH_TOKEN per-call in _subprocess_env).
env -u ANTHROPIC_API_KEY -u ANTHROPIC_AUTH_TOKEN \
  PYTHONUNBUFFERED=1 FOEDUS_LLM_CLI_TIMEOUT=300 \
  FOEDUS_PARALLEL_SEATS=1 FOEDUS_PARALLEL_SEATS_WORKERS=3 \
  uv run --extra dev python -u \
  scripts/foedus_canonical_campaign.py \
  --match-id attribution-study-2026-07-11 --num-games 8 \
  --backend claude-cli --model sonnet \
  --fresh-identities \
  --out-dir "$OUT" --resume >> "$OUT/run.stdout.log" 2>> "$OUT/run.stderr.log"
RC=$?
E=$(date +%s)
echo "CAMPAIGN RESUME LEG END: $(date -Is) rc=$RC elapsed=$((E-S))s ($(( (E-S)/3600 ))h$(( ((E-S)%3600)/60 ))m)" | tee -a "$OUT/timing.log"
exit $RC
