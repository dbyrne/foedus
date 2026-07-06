#!/usr/bin/env bash
set -uo pipefail
cd /home/david/foedus/.worktrees/feature/M-foedus-canonical-campaign-v1
OUT=docs/research/2026-07-04-canonical-campaign-v1/preflight
echo "PREFLIGHT START: $(date -Is)" | tee "$OUT/timing.log"
START=$(date +%s)
FOEDUS_LLM_CLI_TIMEOUT=300 uv run --extra dev python scripts/foedus_llm_diplomat_run.py \
  --num-games 1 --max-turns 12 --map-radius 2 --archetype continental_sweep \
  --num-players 4 --llm-seats 0,1,2 --heuristics DishonestCooperator \
  --campaign --recip-ledger --backend claude-cli --model sonnet \
  --transcripts 1 --out-dir "$OUT" > "$OUT/run.stdout.log" 2> "$OUT/run.stderr.log"
RC=$?
END=$(date +%s)
echo "PREFLIGHT END: $(date -Is)  rc=$RC  elapsed=$((END-START))s ($(( (END-START)/60 ))m)" | tee -a "$OUT/timing.log"
exit $RC
