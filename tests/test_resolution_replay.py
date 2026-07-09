"""Tests for foedus.eval.resolution_replay -- the S1.5 confound-check replay
harness (M-foedus-s1-5-confound-check).

Zero sealed-corpus files are touched here: every scenario is a synthetic
fixture (small hand-built maps/states or a live StubLLMClient-driven game),
matching the S1 corpus autopsy's own "no test touches the sealed run"
discipline (see docs/research/2026-07-04-canonical-campaign-v1/autopsy-s1.md
Reproducibility section).

The central correctness claim under test: replaying a game from LOGGED
decisions through the REAL engine (foedus.loop.play_game +
foedus.resolve._resolve_orders_detailed) reproduces the exact GameState
sequence a live game produced -- see
test_replay_game_matches_live_play_game_exactly, which drives one game twice
(once live via StubLLMClient, once via replay from the captured decision log)
and asserts an identical final turn/scores/units/ownership/eliminated --
the outcome-bearing fields, not the entire GameState struct (history,
press/chat logs, and pacts are not compared).
"""

from __future__ import annotations

import json

import pytest

from foedus.agents.heuristics import ROSTER
from foedus.agents.llm.diplomat import LLMDiplomat
from foedus.agents.llm.render import NEGOTIATION_SYSTEM_PROMPT
from foedus.core import Archetype, GameConfig, Hold, Move, Stance, Support, Unit
from foedus.eval.resolution_replay import (
    MissingDecisionError,
    ReplayAgent,
    TurnResolution,
    counterfactual_reinstate_order,
    geometric_legality,
    replay_game,
    verify_replay_fidelity,
)
from foedus.loop import play_game
from foedus.mapgen import generate_map
from foedus.resolve import ResolutionDetail, _resolve_orders_detailed, initial_state

from tests.helpers import build_state_with_units, make_state, triangle_map


def _negotiate_rec(turn, raw):
    return {"turn": turn, "phase": "negotiate", "player": 0,
            "prompt": {"system": "", "user": ""}, "raw_response": raw,
            "parsed": None, "fell_back": False, "n_coerced": 0}


def _orders_rec(turn, raw, parsed=None):
    return {"turn": turn, "phase": "orders", "player": 0,
            "prompt": {"system": "", "user": ""}, "raw_response": raw,
            "parsed": parsed or {}, "fell_back": False, "n_coerced": 0}


def _negotiate_json(**overrides) -> str:
    body = {"press": {"stance": {}, "intents": []},
            "pacts": {"propose": [], "accept": []}}
    body.update(overrides)
    return json.dumps(body)


def _orders_json(orders: dict) -> str:
    return json.dumps({"orders": orders})


# --- ReplayAgent: direct unit tests --------------------------------------


def test_replay_agent_reproduces_press_from_logged_decision():
    m = triangle_map()
    st = make_state(m, [Unit(id=0, owner=0, location=0), Unit(id=1, owner=1, location=1)],
                    num_players=2)
    raw = _negotiate_json(press={"stance": {"1": "ally"}, "intents": []})
    agent = ReplayAgent([_negotiate_rec(0, raw)])
    press = agent.choose_press(st, 0)
    assert press.stance == {1: Stance.ALLY}


def test_replay_agent_reproduces_the_same_legality_gate_as_the_live_run():
    """A Support declared with require_dest is coerced to Hold by
    parse_orders_response's legality gate (foedus.legal never enumerates
    require_dest variants -- see geometric_legality/autopsy-s1-5-confounds.md).
    ReplayAgent must reproduce that exact coercion, not "fix" it, since it is
    replaying what the ORIGINAL run actually submitted to the engine."""
    # 0 attacks 2 (adjacent), 1 sits at home node adjacent to 2 as well so a
    # pin-support geometrically COULD apply -- but require_dest is never a
    # legal-orders candidate, so it must still coerce to Hold.
    edges = {0: {2}, 1: {2}, 2: {0, 1}}
    st = build_state_with_units(
        layout={0: 0, 1: 1, 2: 2}, ownership={0: 0, 1: 0, 2: 1}, edges=edges,
        home_assignments={0: 0, 1: 0}, num_players=2,
    )
    raw = _orders_json({
        "0": {"type": "Move", "dest": 2},
        "1": {"type": "Support", "target": 0, "require_dest": 2},
    })
    agent = ReplayAgent([_orders_rec(0, raw)])
    orders = agent.choose_orders(st, 0)
    assert orders[0] == Move(dest=2)
    assert orders[1] == Hold()  # coerced -- matches the real parse-time gate


def test_replay_agent_missing_decision_raises():
    m = triangle_map()
    st = make_state(m, [Unit(id=0, owner=0, location=0)], num_players=2)
    agent = ReplayAgent([])
    with pytest.raises(MissingDecisionError):
        agent.choose_orders(st, 0)


# --- replay_game: full-loop equivalence to a live play_game ---------------


def test_replay_game_matches_live_play_game_exactly():
    seed = 4242
    num_players = 3
    max_turns = 2
    archetype = Archetype.CONTINENTAL_SWEEP
    map_radius = 2
    llm_seats = [0, 1]
    freerider_seat = 2

    cfg = GameConfig(num_players=num_players, max_turns=max_turns, seed=seed,
                     archetype=archetype, map_radius=map_radius)
    m = generate_map(num_players, seed=seed, archetype=archetype, map_radius=map_radius)
    live_state = initial_state(cfg, m)

    # Seat 0 always tries to move its first unit to its first neighbor
    # (exercising real state mutation across turns); seat 1 always Holds.
    # Content doesn't need to be strategically interesting, only deterministic
    # and state-dependent so replay must actually track state, not just repeat
    # a canned reply. Phase is distinguished by the SYSTEM prompt (stable
    # constants), not by sniffing the user text.

    class ScriptedClient:
        """A live-state-aware stand-in for an LLM: replies deterministically
        from the CURRENT game state (read via the shared `live_state_box`),
        so the resulting decision log is realistic (varies turn to turn) —
        this is what gets captured and handed to replay_game below."""

        def __init__(self, player, state_box):
            self.player = player
            self._state_box = state_box

        def complete(self, system, user):
            if system == NEGOTIATION_SYSTEM_PROMPT:
                return _negotiate_json()
            state = self._state_box["state"]
            own = sorted(u.id for u in state.units.values() if u.owner == self.player)
            if not own:
                return json.dumps({"orders": {}})
            first = own[0]
            nbrs = sorted(state.map.neighbors(state.units[first].location))
            body = {"orders": {str(first): {"type": "Move", "dest": nbrs[0]}}} \
                if nbrs else {"orders": {}}
            return json.dumps(body)

    live_state_box = {"state": live_state}

    live_agents = {
        0: LLMDiplomat(client=ScriptedClient(0, live_state_box)),
        1: LLMDiplomat(client=ScriptedClient(1, live_state_box)),
        freerider_seat: ROSTER["DishonestCooperator"](),
    }

    def on_turn(prev_state, orders_by_player, new_state):
        live_state_box["state"] = new_state

    final_live = play_game(live_agents, state=live_state, on_turn_resolved=on_turn)

    # Round-trip through JSON exactly as the real harness persists decision
    # logs (json.dumps(record, default=str) -> decisions_game{g}_seat{s}.jsonl)
    # so `parsed` entries are strings, matching the real corpus's on-disk
    # shape rather than the in-memory Order objects decision_log holds.
    decisions_by_seat = {
        s: [json.loads(json.dumps(rec, default=str)) for rec in live_agents[s].decision_log]
        for s in llm_seats
    }

    final_replay, resolutions = replay_game(
        seed=seed, num_players=num_players, max_turns=max_turns,
        archetype=archetype, map_radius=map_radius,
        llm_seats=llm_seats, freerider_seats={freerider_seat: "DishonestCooperator"},
        decisions_by_seat=decisions_by_seat,
    )

    assert final_replay.turn == final_live.turn
    assert final_replay.scores == final_live.scores
    assert final_replay.units == final_live.units
    assert final_replay.ownership == final_live.ownership
    assert final_replay.eliminated == final_live.eliminated
    assert len(resolutions) == final_live.turn

    mismatches = verify_replay_fidelity(decisions_by_seat, resolutions)
    assert mismatches == []


def test_replay_game_builds_agents_in_strict_seat_order_not_llm_seats_order():
    """`replay_game` must build its `agents` dict in strict seat order
    (0..num_players-1) regardless of the order `llm_seats` lists them in --
    matching the original campaign harness's own `enumerate(agent_names)`
    construction (`scripts/foedus_llm_diplomat_run.py::run_one_llm_game`).

    This matters because `play_game` (foedus/loop.py) iterates
    `agents.items()` in insertion order for the same-turn pact-proposal pass,
    and `propose_pact` (foedus/press.py) assigns `pact_id` sequentially by
    proposal call order (`state.next_pact_id`) -- so a wrong insertion order
    silently reassigns which same-turn proposer gets pact_id 0 vs 1.
    Regression for a bug an earlier revision of `replay_game` had (building
    `agents` as `for seat in llm_seats: ...` then `for seat in
    freerider_seats: ...`, so an out-of-numeric-order `llm_seats` list --
    exactly the shape `scripts/foedus_s1_5_confound_check.py` passes,
    `list(sweep_row["llm_seats"])` straight from the sealed corpus --
    desynced insertion order from the original run's strict seat order).
    Empirically inert on the sealed 8-game corpus (checked by re-running the
    confound-check script against the pre-fix code and diffing output), but
    a real fidelity risk in general.
    """
    seed = 777
    num_players = 3
    max_turns = 1
    archetype = Archetype.CONTINENTAL_SWEEP
    map_radius = 2

    cfg = GameConfig(num_players=num_players, max_turns=max_turns, seed=seed,
                     archetype=archetype, map_radius=map_radius)
    m = generate_map(num_players, seed=seed, archetype=archetype, map_radius=map_radius)
    probe_state = initial_state(cfg, m)
    unit_of = {
        p: next(u.id for u in probe_state.units.values() if u.owner == p)
        for p in range(num_players)
    }

    def _propose_json(proposer, counterparty):
        return _negotiate_json(pacts={"propose": [{
            "counterparty": counterparty,
            "terms": [
                {"player": proposer, "unit_id": unit_of[proposer],
                 "declared_order": {"type": "Hold"}},
                {"player": counterparty, "unit_id": unit_of[counterparty],
                 "declared_order": {"type": "Hold"}},
            ],
        }], "accept": []})

    # Seats 0 and 2 each propose a (self-consistent, two-sided) pact to seat 1
    # on the same turn; seat 1 proposes nothing. llm_seats is deliberately
    # listed out of numeric order -- exactly what would have desynced the
    # pre-fix insertion order.
    decisions_by_seat = {
        0: [_negotiate_rec(0, _propose_json(0, 1)), _orders_rec(0, _orders_json({}))],
        1: [_negotiate_rec(0, _negotiate_json()), _orders_rec(0, _orders_json({}))],
        2: [_negotiate_rec(0, _propose_json(2, 1)), _orders_rec(0, _orders_json({}))],
    }

    _final_state, resolutions = replay_game(
        seed=seed, num_players=num_players, max_turns=max_turns,
        archetype=archetype, map_radius=map_radius,
        llm_seats=[2, 0, 1], freerider_seats={},
        decisions_by_seat=decisions_by_seat,
    )

    pacts = resolutions[0].prev_state.pacts
    assert len(pacts) == 2
    by_proposer = {p.proposer: p.pact_id for p in pacts}
    # Strict seat order (0 before 1 before 2) means seat 0's proposal is
    # called first in the pact-proposal pass and gets the lower pact_id.
    assert by_proposer[0] < by_proposer[2]


# --- verify_replay_fidelity: tamper detection ------------------------------


def test_verify_replay_fidelity_detects_a_tampered_decision_log():
    # A single synthetic turn where the replay actually submitted Move(dest=2)
    # for unit 0, but the (tampered) logged decision claims it submitted Hold.
    decisions_by_seat = {
        0: [_orders_rec(0, _orders_json({"0": {"type": "Move", "dest": 2}}),
                        parsed={"0": "Hold()"})],
    }
    resolutions = [
        TurnResolution(
            turn=0, prev_state=None,
            orders_by_player={0: {0: Move(dest=2)}},
            new_state=None, detail=ResolutionDetail(),
        )
    ]
    mismatches = verify_replay_fidelity(decisions_by_seat, resolutions)
    assert len(mismatches) == 1
    assert mismatches[0].seat == 0
    assert mismatches[0].turn == 0
    assert mismatches[0].unit_id == 0


# --- geometric_legality -----------------------------------------------------


def test_geometric_legality_bare_support_is_legal():
    edges = {0: {2}, 1: {2}, 2: {0, 1}}
    st = build_state_with_units(
        layout={0: 0, 1: 1, 2: 2}, ownership={0: 0, 1: 0, 2: 1}, edges=edges,
        home_assignments={0: 0, 1: 0}, num_players=2,
    )
    flat = {0: Move(dest=2), 1: Support(target=0), 2: Hold()}
    assert geometric_legality(st, 1, Support(target=0), flat) == "legal"


def test_geometric_legality_require_dest_is_parser_gap_when_resolve_would_accept():
    """Mirrors the corpus's g5-turn-9 shape: unit 1 is adjacent to the
    contested node and its pin target matches the mover's actual order, so
    resolve.py's own normalization WOULD accept it -- the only reason it
    never reaches the engine is foedus.legal never enumerating require_dest
    candidates at all (see foedus/legal.py's docstring)."""
    edges = {0: {2}, 1: {2}, 2: {0, 1}}
    st = build_state_with_units(
        layout={0: 0, 1: 1, 2: 2}, ownership={0: 0, 1: 0, 2: 1}, edges=edges,
        home_assignments={0: 0, 1: 0}, num_players=2,
    )
    flat = {0: Move(dest=2), 1: Support(target=0, require_dest=2), 2: Hold()}
    result = geometric_legality(st, 1, Support(target=0, require_dest=2), flat)
    assert result == "illegal_parser_gap"


def test_geometric_legality_require_dest_genuinely_illegal_when_not_adjacent():
    """Same pin-support shape, but unit 1 is NOT adjacent to the contested
    node -- resolve.py's own normalization would ALSO reject it, so this is
    genuine geometric illegality, not the parser-gap artifact."""
    edges = {0: {2}, 1: {3}, 2: {0}, 3: {1}}
    st = build_state_with_units(
        layout={0: 0, 1: 1, 2: 2}, ownership={0: 0, 1: 0, 2: 1}, edges=edges,
        home_assignments={0: 0, 1: 0}, num_players=2,
    )
    flat = {0: Move(dest=2), 1: Support(target=0, require_dest=2), 2: Hold()}
    result = geometric_legality(st, 1, Support(target=0, require_dest=2), flat)
    assert result == "illegal_geometric"


def test_geometric_legality_illegal_move_is_illegal_geometric():
    edges = {0: {1}, 1: {0}}
    st = build_state_with_units(
        layout={0: 0}, ownership={0: 0}, edges=edges,
        home_assignments={0: 0}, num_players=2,
    )
    flat = {0: Move(dest=99)}
    assert geometric_legality(st, 0, Move(dest=99), flat) == "illegal_geometric"


# --- counterfactual_reinstate_order -----------------------------------------


def test_counterfactual_reinstate_order_flips_bounce_to_dislodge():
    """The exact mechanism behind the corpus's g5-turn-9 mystery (S1 autopsy
    section 1.4): an unsupported attacker at strength 1 bounces off a static
    defender's hold-strength 1; reinstating the (parser-gap-dropped)
    require_dest Support that would have made it a 2-vs-1 flips the outcome
    to a dislodge -- exactly what a fixed parser would have allowed."""
    edges = {0: {2}, 1: {2}, 2: {0, 1}}
    st = build_state_with_units(
        layout={0: 0, 1: 1, 2: 2}, ownership={0: 0, 1: 0, 2: 1}, edges=edges,
        home_assignments={0: 0, 1: 0}, num_players=2,
    )
    # As actually submitted to the engine: unit 1's Support was already
    # coerced to Hold by the parse-time gate (mirrors ReplayAgent's output).
    # Both units 0 and 1 belong to player 0 (the attacker+supporter side).
    actual_orders = {0: {0: Move(dest=2), 1: Hold()}}
    actual_state, actual_detail = _resolve_orders_detailed(st, actual_orders)
    assert actual_detail.outcome[0] == "fail"  # bounced: 1 vs static defender's 1
    assert 2 in actual_state.units  # golf's unit 2 survives

    counter_state, counter_detail = counterfactual_reinstate_order(
        st, actual_orders, player=0, unit_id=1,
        order=Support(target=0, require_dest=2),
    )
    assert counter_detail.outcome[0] == "success"
    assert counter_detail.outcome[2] == "dislodged"
    assert 2 not in counter_state.units  # golf's unit is gone (no retreats)
