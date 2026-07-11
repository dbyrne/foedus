#!/usr/bin/env bash
# G2 Phase B — initial detached launch leg (the seal was already published via
# --dry-run, so this is a --resume from 0 banked games). $0 API: the MODEL
# seats are LLMDiplomat + local OllamaClient (CONSTRAINED decoding: per-phase
# JSON schema on every negotiate/orders call, BOTH arms); no claude/anthropic
# backend is reachable from the runner. ANTHROPIC_* strip = defense-in-depth.
set -uo pipefail
cd /home/david/foedus/.worktrees/g2
OUT=docs/research/2026-07-11-gym-g2/phase-b/run
echo "G2 PHASE-B START: $(date -Is)" | tee "$OUT/timing.log"
S=$(date +%s)
env -u ANTHROPIC_API_KEY -u ANTHROPIC_AUTH_TOKEN \
  PYTHONUNBUFFERED=1 OLLAMA_HOST=http://localhost:11434 \
  PYTHONPATH=. python3 -u \
  scripts/foedus_phaseb_paired_eval.py \
  --match-id phaseb-gym-g2-2026-07-11 --num-seeds 20 --max-turns 12 \
  --trained-model foedus-entrant-v1:latest --base-model foedus-base-v1:latest \
  --freerider DishonestCooperator --anchors Cooperator,TitForTat \
  --constrained \
  --assert-disjoint-from docs/research/2026-07-04-canonical-campaign-v1/run/seed_manifest.revealed.json \
  --assert-disjoint-from docs/research/2026-07-10-canonical-sonnet-arm/run/seed_manifest.revealed.json \
  --assert-disjoint-from docs/research/2026-07-10-gym-g1/phase-b/run/seed_manifest.revealed.json \
  --out-dir "$OUT" --resume > "$OUT/run.stdout.log" 2> "$OUT/run.stderr.log"
RC=$?
E=$(date +%s)
echo "G2 PHASE-B END: $(date -Is) rc=$RC elapsed=$((E-S))s ($(( (E-S)/60 ))m)" | tee -a "$OUT/timing.log"
exit $RC
