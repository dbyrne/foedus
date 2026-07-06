# Preflight — 1-game wall-clock projection (2026-07-04)

Mandatory smoke before the 8-game run: one full `ruleset_v1` game (4 seats /
12 turns / r2 / `continental_sweep`), 3 Sonnet seats + `DishonestCooperator`,
`claude-cli`, campaign + reciprocation-ledger, 300 s timeout. Confirmed the full
stack composes; used only to project the match wall-clock (not committed as a
full artifact — it was stopped once the projection was in hand).

## Measured per-call latency (`claude -p --model sonnet`, subscription auth)

12 completed calls sampled by watching the live subprocess:

```
174, 31, 13, 139, 99, 130, 21, 211, 91, 110, 37, 46  (seconds)
```

- mean ≈ **92 s/call**, median ≈ **95 s**, range **13–211 s** (high variance).
- The box was idle (load ≈ 0.2); the slow spikes (139–211 s) coincided with
  ~6 other `claude` fleet processes running concurrently, i.e. **subscription
  contention**, not local CPU — an arena-hosting insight worth recording.

## Projection

~72 decision calls/game + 3 self-notes ≈ **75 calls/game**. At ~92 s sequential:
**~1.7–1.9 h/game → ~14 h for 8 games** under that contention. Flagged to Nova;
David accepted overnight (Plan 1: B + 8 games), with a guardrail to pause + flag
if the *actual* post-game-2 average projects > 18 h, and an expectation the
per-call latency falls as the parallel coders finish. The real run's per-game
wall-clock is recorded in `../run/run_summary.json` + `../run/sweep.jsonl`.
