# Phase 0b / F5 — evidence packet (reviewer audit)

**Milestone:** `M-foedus-joint-intents-0b`  •  **Branch:** `feature/M-foedus-joint-intents-0b` (off merged `origin/main`, incl. 0a)
**Coder session:** `e31e2f35` (opus, TDD)  •  **Reviewer:** Opus 4.8 (this session)
**Date:** 2026-07-01  •  **Verdict: PASS at the code level.** Branch not yet pushed/PR'd; behavioral
test deferred to after F6.

## Scope delivered (the minimal ratified two-party Pact primitive)
- **Types** (`core.py`): `PactStatus` (PROPOSED/ACCEPTED), `PactTerm`, `Pact` (proposer,
  counterparty, terms spanning BOTH parties, status, proposed_turn), `PactProposal`, `PactBreach`.
- **Lifecycle** (`press.py`): `propose_pact` (filters third-party/unowned-unit terms; no-ops on
  self-pact, eliminated counterparty, wrong phase, done-gated), `accept_pact` (counterparty-only,
  idempotent).
- **Breach detection** (`press.py::_verify_pacts`): for each ACCEPTED pact term vs the RAW submitted
  order — VOID if unit gone/disowned; honored if equal; else a `PactBreach` delivered to the OTHER
  party (the one who relied on it). ACCEPTED pacts consumed; PROPOSED-this-round survive one round,
  stale proposals expire. Wired into `finalize_round` and `loop.play_game`.
- **Surfacing**: pacts + breaches in the seat prompt (`render_common.py`), fog exposure to the two
  parties only (`fog.py`), wire codec leaves pacts off the HTTP path safely (`wire.py`), and the
  CLI/agent press schema + parser (`foedus_press_play.py`) can propose/accept.
- **Deferred correctly:** conditional orders (stretch) not attempted; betrayal *penalty* left to F6
  (F5 only emits the `PactBreach` signal). Coder wrote its own design doc
  (`docs/superpowers/2026-07-01-foedus-phase0b-f5-joint-intents-design.md`).

## Gate: test suite
`uv run pytest` on the branch: **717 passed, 1 skipped, 1 failed.** The failure is again the
pre-existing `test_detente_uses_tied_top_ranks` (fails identically on main — stale test, unrelated).
~50 new pact tests all pass. Clean TDD: failing tests committed first (`c1522c9`), then impl (`c4a8fae`).

## Correctness verification (the critical claim: breach = divergence)
Verified by reading `_verify_pacts` (matches the spec exactly) and by the test suite pinning every case:
- **Breach ⇔ actual ≠ declared, delivered to the observer (non-breacher):**
  `test_honored_pact_emits_no_breach`, `test_breach_by_counterparty_observed_by_proposer`,
  `test_breach_by_proposer_observed_by_counterparty`, `test_both_parties_breach_each_observes_the_other`.
- **VOID on lost/disowned unit:** `test_void_term_when_unit_lost_is_not_breach`.
- **Lifecycle/expiry:** proposed-not-checked, accepted-consumed, unaccepted-survives-one-round-then-expires,
  accepted-next-round-binds.
- **Equivalence (a pact is a commitment RECORD, not a combat rule):**
  `test_honored_pact_resolves_identically_to_no_pact` — the exact property required by the brief. ✓
- **Fog + wire + loop integration:** pact/breach fog visibility scoped to parties/observer; wire
  round-trips clean; `play_game` records breaches via hooks.

## Housekeeping
- `.gitignore` untouched; `.nexus-mcp.json` untouched (secret safe); branch off merged `origin/main`.
- No unexpected file touches; changes additive.

## Outstanding
1. **Not pushed / no PR** (unlike 0a, whose process pushed + opened PR #26). Push + PR is an outward
   action — awaiting David.
2. **Two-reviewer rigor:** Opus audit done (this packet); a second (Sonnet) review is optional given
   the airtight correctness coverage, but available if desired.
3. **Behavioral test deferred:** F5 enables binding coordination + observable breach, but the *payoff*
   (agents actually running 2-on-1 dislodges and paying for betrayal) needs **F6 (betrayal teeth)**.
   Recommend the next 4-agent behavioral game after F6 lands, testing F5+F6 together.
4. Stale `test_detente_uses_tied_top_ranks` still wants a separate fix.
