#!/usr/bin/env bash
# Seal-first launch: seed_manifest.sealed.json + campaign_plan.json were
# written by a --dry-run and COMMITTED before this script runs (see README §5).
# The live run therefore starts through --resume from zero completed games —
# the pre-committed seal is never re-rolled (unit-tested flow:
# test_fresh_identities_seal_first_launch_flow).
set -uo pipefail
cd /home/david/foedus/.worktrees/feature/M-foedus-attribution-study
OUT=docs/research/2026-07-11-attribution-study/run
echo $$ > "$OUT/launch.pid"
touch "$OUT/sweep.jsonl" "$OUT/telemetry.jsonl"
echo "CAMPAIGN START: $(date -Is)" | tee -a "$OUT/timing.log"
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
echo "CAMPAIGN END: $(date -Is) rc=$RC elapsed=$((E-S))s ($(( (E-S)/3600 ))h$(( ((E-S)%3600)/60 ))m)" | tee -a "$OUT/timing.log"
exit $RC
