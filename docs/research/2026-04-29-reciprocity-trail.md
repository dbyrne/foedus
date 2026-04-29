# Reciprocity trail — what we tried, what we learned

**Status:** Trail explored, no clean fix landed. Reached a real design problem (trust bootstrapping) that needs proper brainstorming, not Q&D iteration.

## Goal

Close the freerider exploit surfaced in the alliance-bonus experiment: `1 DC vs 3 Coop` showed DC winning by +10.7 even at bonus=0, structurally (free combat assistance + time arbitrage), not just from scoring.

## What we tried

### Attempt 1 — engine-side reciprocity rule

`FOEDUS_ALLIANCE_RECIPROCITY=1`: alliance bonus only fires when both attacker and supporter issued at least one cross-player SupportMove this turn.

**Result:**

| bonus | recip | DC | Coop avg | DC−Coop |
|---|---|---|---|---|
| 0 | 0 | 64.3 | 53.4 | +10.9 |
| 0 | 1 | 64.3 | 53.4 | +10.9 |
| 3 | 0 | 73.5 | 61.2 | +12.4 |
| 3 | 1 | 64.3 | 53.9 | +10.5 |
| 10 | 0 | 95.0 | 79.3 | +15.7 |
| 10 | 1 | 64.3 | 54.9 | +9.4 |

Reciprocity contains the bonus-driven part of the exploit (DC's lead at bonus=10 drops from +15.7 to +9.4) but the **structural exploit at bonus=0 is unchanged** (+10.9). The combat-help advantage of being supported isn't bonus-driven — Cooperators support DC's attacks, those attacks succeed where they'd otherwise bounce, DC captures more supplies.

### Attempt 2 — agent-side trust memory (`ReciprocalCooperator`)

RC: same as Cooperator, but only cross-supports a player who has cross-supported any of its units in past turns. Implemented via scraping the resolution log for `alliance bonus +N to pX (mover) and pY (supporter)` events; engine modified to emit those log lines unconditionally (regardless of bonus value) so trust signals exist at bonus=0.

**Result:**

| Setup | SupportMove% | Notes |
|---|---|---|
| 4 RCs | **0.00%** | Trust never bootstraps; nobody supports anyone |
| 1 DC vs 3 RC | **0.00%** | Same — RCs never support each other or DC |

The exploit is "closed" (DC scores below RCs by -1.2) but only because **no cooperation happens at all**. The cure killed the patient.

## Why trust bootstrap fails

In a 4-player continental_sweep r3 game, homes are spread around the perimeter and are 3+ hops apart. At turn 0, no player's home is adjacent to another's planned destination. So no initial cross-support can fire, no trust forms, and the gate `if state.turn > 0 and other_pid not in self._trusted: continue` blocks all future supports.

This is a **trust-bootstrapping problem**: how do honest cooperators recognize each other in turn 0 when they have no shared history?

## Design surface this exposes

For Bundle 4 to close the freerider exploit, it needs to answer:

1. **What's the bootstrap signal?** Options:
   a. Free first contact (first N turns or first M cross-supports per pair).
   b. Stance.ALLY as the trust signal (but DC also declares ALLY).
   c. Published cross-support Intents — agents commit publicly to supporting before doing it. Requires extending the press protocol to make support-pledges visible.
   d. Chat-based negotiation — agents read chat for cooperation pledges. Requires NLP / structured chat.
   
2. **Is reciprocity per-pair or per-game?** If A supports B but B doesn't support A back, does A also stop supporting C? (Tit-for-tat per pair vs global trust pool.)

3. **What's the cost of being wrong?** A cooperator who incorrectly trusts a freerider gets exploited; a cooperator who incorrectly distrusts a real ally misses bonus opportunities. The right balance depends on the population mix.

4. **How does the press system extend?** Currently `Intent` carries a single declared `Order` for one of the publisher's own units. Cross-support pledges would need either:
   a. Intents whose declared_order is a SupportMove (already representable; no current heuristic uses it).
   b. A new structure like `SupportPledge(target_player, support_target_unit)` that's distinct from Intent.

## Recommendation for next session

Don't iterate further on Q&D heuristics. The next move is a real Bundle 4 brainstorm answering at least:

- **Bootstrap mechanism** (likely option 1c — published cross-support intents).
- **Trust state representation** (per-pair memory in agent state).
- **Engine support** for the chosen bootstrap (probably no engine change needed if intents-of-SupportMoves are used; existing Intent type accepts any Order).
- **Test gates**:
  - DC ≤ Coop in `1 DC vs 3 Coop` (closes freerider).
  - Coop ≥ GH in random 13-pool (preserves current Tier-1 strategy).
  - Coop ≥ GH at bonus=0 in 4-Coop sanity (preserves mutual cooperation without bonus).
  - SupportMove% > 5% in 4-Coop game (cooperation actually happens).

## Other findings not yet pursued

- **Sycophant ≡ OB in the random pool** — the `--alliance-bonus` mechanic doesn't differentiate them because neither issues cross-supports. Intent-break consequences are still needed independently.
- **Détente-by-lying** — surfaced in the détente baseline; a 4-Sycophant table closes a peaceful collective victory in 8 turns despite secretly playing aggressive expansion. Same root cause — declared-stance is taken at face value.
- **`--workers` default is now 0** (= cpu_count). Trivial but worth noting future sweep commands can drop the explicit flag.

## Code state

Branch: `reciprocity-trail` (on top of merged main).
- `foedus/agents/heuristics/reciprocal_cooperator.py` — RC with trust memory.
- `FOEDUS_ALLIANCE_RECIPROCITY=1` env-var gate on the engine-side reciprocity rule.
- Engine always emits alliance-event log lines (regardless of bonus value) so future agents can read trust signals at bonus=0.

This branch is **not ready to merge** — RC doesn't actually cooperate. Treat as exploration record only.
