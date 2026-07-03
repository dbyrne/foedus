# Strong-model coordination probe — sonnet seats vs the freerider (2026-07-03)

## Question (the earned rung)
Does a capable model (Claude Sonnet via the subscription `claude -p` backend), given the same
neutral reciprocation ledger, coordinate against the DishonestCooperator freerider that:
- beat a naive local qwen2.5-14b table **4/4 by ~2×**, and
- beat the same 14b **with** the memory ledger (PR #36: wins 3/6→3/6, subsidy 41=41, ledger ignored)?

## Protocol
4 games × 8 turns, seeds 0–3 (paired with PR #36 arms), `--llm-seats 0,1,2
--heuristics DishonestCooperator --map-radius 1 --recip-ledger --backend claude-cli --model sonnet`.
Sequential per-seed runs; no prompt iteration; scorecard via the merged metrics extractor.

## Results

| | 14b baseline (Arm A, seeds 0-3) | 14b + ledger (Arm B, seeds 0-3) | **sonnet + ledger** |
|---|---|---|---|
| Freerider wins | — | 2/4 | **1/4** |
| Mean margin over LLM avg | ~+7.9 (6-game arm) | +6.5 | **+3.58** (−45%) |
| Subsidy (LLM supports of freerider units) / game | ~6.8 | 6.83 | **1.5** (−78%) |
| True parse-fail (excl. timeouts) | ~10% | ~11% | **3.7%** |

Per game (freerider = seat 3): seed0 fr 2nd (+2.33, LLM wins 18); seed1 fr 2nd (+0.67, LLM wins 20);
seed2 fr 3rd (**−2.00**, LLM wins 20); seed3 fr WINS (+13.33, 23 vs 8–11).

**Timeout handicap:** 34/188 decisions (18%) were forced Holds from `claude -p` exceeding the 180s
client timeout (headline fell_back 21.8% → true parse-fail 3.7%). The sonnet table went 3–1 against
the freerider while playing ~18% handicapped. Seed3 (the loss) was NOT timeout-driven (6–12%/seat).

## Mechanism (what changed vs the 14b)
- **Real LLM↔LLM coordination appeared** — first time in the arc. Seeds 0–2 show mutual-support
  blocks between LLM seats (e.g. seed0 turns 4–6: p0's u4 and p1's u5 both Support(u1)) — the 14b
  never once supported another LLM seat; it only ever supported the freerider.
- **Subsidy collapsed −78%** (6.83 → 1.5/game): sonnet largely refuses to spend actions powering
  the freerider's expansion — the exact failure the 14b could not avoid even with the ledger.
- **Shunning is partial, not clean:** stances toward the freerider still skew ally (it never trips a
  breach, so its reputation stays clean); sonnet out-competes it more than it punishes it.
- **The loss mode is coordination-failure, not seduction:** in seed3 no seat declared a single
  Support all game (atomized play) and the freerider out-expanded three disorganized neighbors —
  zero subsidy, zero coalition, blowout. Lone suspicion also stays fatal (seed0's p2 held hostile
  alone and was eliminated).

## Verdict vs the falsifiable bar (declared before the run)
- Primary: freerider does NOT win the majority ✓ (1/4) AND margin ≤ +2 ✗ (+3.58, dragged by the
  single seed3 blowout). **Strictly: primary clause PARTIALLY met.**
- Mechanism: subsidy drops materially ✓ (−78%); sustained hostility ✗/partial; LLM-LLM coordination
  evidence ✓ (bonus clause).

**Honest call: DIRECTIONAL PASS, not a clean pass.** Unlike PR #36 (where a −32% margin move had a
flat mechanism and was correctly discarded as variance), here the margin halves WITH a −78%
mechanism shift and visible coalition behavior — the capability gradient is real: naive-14b loses
always; 14b+memory loses identically; sonnet+memory dethrones the freerider in 3 of 4 games. What
sonnet does NOT yet do is *reliably* coordinate (seed3) or explicitly shun.

## Implications
1. **The arena ladder has a working top rung** — capable seats produce coalition play the substrate
   was built to measure; the freerider remains beatable-but-dangerous (a good boss, not a broken one).
2. **Distillation target confirmed:** sonnet's play (refuse subsidy, form mutual-support blocks) is
   the behavior to distill into the trainable local entrant; the 14b-with-ledger failure shows the
   gap is policy, not perception.
3. **Follow-ups:** raise the claude-cli timeout (~300s) to kill the handicap; cross-game memory
   (does the table learn to coordinate from prior losses like seed3?); an explicit-shunning probe.
