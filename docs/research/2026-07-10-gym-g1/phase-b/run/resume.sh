#!/usr/bin/env bash
# G1 Phase B — GUARDED crash/@reboot resume. Self-guards so a lingering @reboot
# crontab entry is a safe no-op:
#   * exits immediately if the match already revealed (complete), and
#   * exits if a runner process is already alive (no double-run).
# Otherwise it continues the sealed match banked-only (--resume). $0 API.
set -uo pipefail
cd /home/david/foedus/.worktrees/feature/M-foedus-gym-g1
OUT=docs/research/2026-07-10-gym-g1/phase-b/run

if [ -f "$OUT/seed_manifest.revealed.json" ]; then
  echo "PHASE-B RESUME skipped ($(date -Is)): already revealed/complete." \
    | tee -a "$OUT/timing.log"
  exit 0
fi
if pgrep -f "foedus_phaseb_paired_eval.py" >/dev/null 2>&1; then
  echo "PHASE-B RESUME skipped ($(date -Is)): a runner is already alive." \
    | tee -a "$OUT/timing.log"
  exit 0
fi

echo "PHASE-B RESUME: $(date -Is)" | tee -a "$OUT/timing.log"
S=$(date +%s)
env -u ANTHROPIC_API_KEY -u ANTHROPIC_AUTH_TOKEN \
  PYTHONUNBUFFERED=1 OLLAMA_HOST=http://localhost:11434 \
  PYTHONPATH=. python3 -u \
  scripts/foedus_phaseb_paired_eval.py \
  --match-id phaseb-gym-g1-2026-07-10 --num-seeds 20 --max-turns 12 \
  --trained-model foedus-entrant-v1:latest --base-model foedus-base-v1:latest \
  --freerider DishonestCooperator --anchors Cooperator,TitForTat \
  --out-dir "$OUT" --resume >> "$OUT/run.stdout.log" 2>> "$OUT/run.stderr.log"
RC=$?
E=$(date +%s)
echo "PHASE-B RESUME LEG END: $(date -Is) rc=$RC elapsed=$((E-S))s" \
  | tee -a "$OUT/timing.log"
exit $RC
