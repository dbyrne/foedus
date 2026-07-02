"""Primitive A — harm-typed breaches (2026-07-02 reciprocity model).

A divergence (submitted != declared) counts as a breach ONLY when it harms a
COMMITTED party X — someone the breacher declared ALLY toward (for a public
Intent) or the co-signer of an accepted Pact. Harm is one of:

  H1 (aggression): the breacher's own unit, or a unit its actual Support
     backed, dislodged X's unit or captured X's supply/home center.
  H2 (abandoned defense): the breacher's DECLARED order was a Support of X's
     unit (or a Hold adjacent to X's center) that it abandoned, and X's unit
     was dislodged / center captured this turn.

Everything else — deviating from a Move-intent toward a NEUTRAL player,
redirecting a declared Move into a Support that helps the committed ally or a
third party — is pro-social/neutral and is NOT a breach: no score penalty, no
reputation increment.

These scenarios are the falsifiable core: they distinguish "I broke my word to
HELP" (Cooperator's Move->Support redirect) from "I broke my word to HARM"
(OpportunisticBetrayer's stab), which the old per-unit order-diff conflated.
"""

from __future__ import annotations

from dataclasses import replace

from foedus.core import (
    GameConfig,
    GameState,
    Hold,
    Intent,
    Map,
    Move,
    NodeType,
    Pact,
    PactStatus,
    PactTerm,
    Press,
    ReputationTally,
    Stance,
    Support,
    Unit,
)
from foedus.press import finalize_round, signal_done, submit_press_tokens


# --- controlled maps --------------------------------------------------------


def _triangle_supply_map() -> Map:
    """n0(HOME p0) - n1(SUPPLY) - n2(PLAIN), fully connected triangle, plus a
    detached HOME n3 for p1 so p1 is never eliminated when its n1 unit falls.

    n0-n1-n2 form a triangle; n3 is p1's safe home (adjacent to n1 only)."""
    coords = {0: (0, 0), 1: (1, 0), 2: (0, 1), 3: (2, 0)}
    edges = {
        0: frozenset({1, 2}),
        1: frozenset({0, 2, 3}),
        2: frozenset({0, 1}),
        3: frozenset({1}),
    }
    node_types = {
        0: NodeType.HOME,
        1: NodeType.SUPPLY,
        2: NodeType.PLAIN,
        3: NodeType.HOME,
    }
    home_assignments = {0: 0, 3: 1}
    return Map(coords=coords, edges=edges, node_types=node_types,
               home_assignments=home_assignments)


def _state(units, *, num_players=3, ownership_overrides=None,
           high_value_supply_fraction=0.0) -> GameState:
    m = _triangle_supply_map()
    ownership = {n: None for n in m.nodes}
    for node, player in m.home_assignments.items():
        ownership[node] = player
    for u in units:
        ownership[u.location] = u.owner
    if ownership_overrides:
        ownership.update(ownership_overrides)
    cfg = GameConfig(
        num_players=num_players, max_turns=50, build_period=999,
        detente_threshold=0,
        high_value_supply_fraction=high_value_supply_fraction,
    )
    return GameState(
        turn=0, map=m, units={u.id: u for u in units},
        ownership=ownership,
        scores={p: 0.0 for p in range(num_players)},
        eliminated=set(),
        next_unit_id=max((u.id for u in units), default=-1) + 1,
        config=cfg,
    )


def _finalize(state, press_by_player, orders):
    for p in range(state.config.num_players):
        if p in state.eliminated:
            continue
        press = press_by_player.get(p, Press(stance={}, intents=[]))
        state = submit_press_tokens(state, p, press)
        state = signal_done(state, p)
    return finalize_round(state, orders)


def _ally(*players):
    return {p: Stance.ALLY for p in players}


# --- deviation toward a NON-committed party is not a breach -----------------


def test_deviation_toward_neutral_player_is_not_a_breach() -> None:
    """p0 declares Move but Holds. p0's stance toward the intent audience is
    NEUTRAL (default), so nobody was pledged cooperation — the deviation is
    information, not betrayal. No penalty, no reputation."""
    # p0 unit at n0; declares public Move(n1) intent, actually Holds.
    s = _state([Unit(0, 0, 0), Unit(1, 1, 3)], num_players=2)
    intent = Intent(unit_id=0, declared_order=Move(dest=1), visible_to=None)
    s2 = _finalize(s, {0: Press(stance={}, intents=[intent])},
                   {0: {0: Hold()}, 1: {1: Hold()}})
    assert s2.reputation == {}


def test_redirect_move_to_support_committed_ally_is_not_a_breach() -> None:
    """The Cooperator case: p0 declares ALLY->p1 and a Move intent, then
    redirects that unit to SUPPORT p1's own move. It helped the committed
    ally; it harmed nobody it was committed to. NOT a breach."""
    # p1 has u1 at n1 moving n1->n2 (into empty PLAIN). p0's u0 at n0 is
    # adjacent to n2 and declared Move(n0-adjacent) but redirects to Support(u1).
    s = _state([Unit(0, 0, 0), Unit(1, 1, 1)], num_players=2)
    intent = Intent(unit_id=0, declared_order=Move(dest=1), visible_to=None)
    s2 = _finalize(
        s,
        {0: Press(stance=_ally(1), intents=[intent])},
        {0: {0: Support(target=1)}, 1: {1: Move(dest=2)}},
    )
    assert s2.reputation == {}


def test_redirect_to_support_third_party_not_harming_ally_is_not_a_breach() -> None:
    """p0 declares ALLY->p1, Move intent, redirects to Support p2's move that
    dislodges a NEUTRAL/uncommitted player — harms nobody p0 was committed to.
    NOT a breach (this is the common Cooperator redirect that the old model
    wrongly fined)."""
    # p2 at n2 moves onto n1; p0's u0 at n0 supports p2. p1's unit u1 sits at
    # n3 (its home), uninvolved. The dislodged party (if any) is not p1.
    # Here n1 is unoccupied so p2 just walks in — no dislodge at all, purely
    # cooperative capture assistance toward p2 (NEUTRAL to p0).
    s = _state([Unit(0, 0, 0), Unit(1, 1, 3), Unit(2, 2, 2)], num_players=3)
    intent = Intent(unit_id=0, declared_order=Move(dest=1), visible_to=None)
    s2 = _finalize(
        s,
        {0: Press(stance=_ally(1), intents=[intent])},
        {0: {0: Support(target=2)}, 1: {1: Hold()}, 2: {2: Move(dest=1)}},
    )
    assert s2.reputation == {}


# --- H1: own move / backed support dislodging a committed ally --------------


def test_own_move_dislodging_committed_ally_is_harmful_breach() -> None:
    """Sycophant/OpportunisticBetrayer pattern: declare Hold (or anything),
    then dislodge a unit belonging to a player you declared ALLY toward. H1."""
    # p0: u0 at n0, u2 at n2 (both adjacent to n1). p1: u1 at n1 (owns n1).
    # p0 declares public intent u0->Hold; actually Moves u0->n1 with u2 support
    # -> dislodges p1's u1. p0 declared ALLY toward p1 -> committed party.
    s = _state(
        [Unit(0, 0, 0), Unit(2, 0, 2), Unit(1, 1, 1)],
        num_players=2,
        ownership_overrides={1: 1},
    )
    intent = Intent(unit_id=0, declared_order=Hold(), visible_to=None)
    s2 = _finalize(
        s,
        {0: Press(stance=_ally(1), intents=[intent])},
        {0: {0: Move(dest=1), 2: Support(target=0)}, 1: {1: Hold()}},
    )
    # p1's unit was dislodged and n1 captured -> harmful breach recorded.
    assert 1 not in [u.owner for u in s2.units.values()] or s2.ownership[1] == 0
    assert s2.reputation.get(0, ReputationTally()).intent_breaches == 1


def test_backed_support_dislodging_committed_ally_is_harmful_breach() -> None:
    """p0's DECLARED plan was a Move; it redirects that unit to SUPPORT a
    third party's attack that dislodges the committed ally p1. Backing the
    kill is H1 just as swinging it is."""
    # p2 at n2 attacks n1 (p1's u1); p0's u0 at n0 supports p2's attack.
    # p0 declared ALLY->p1 and a Move intent for u0; redirecting u0 to back
    # p2's dislodge of p1 is harmful.
    s = _state(
        [Unit(0, 0, 0), Unit(2, 2, 2), Unit(1, 1, 1)],
        num_players=3,
        ownership_overrides={1: 1},
    )
    intent = Intent(unit_id=0, declared_order=Move(dest=1), visible_to=None)
    s2 = _finalize(
        s,
        {0: Press(stance=_ally(1), intents=[intent])},
        {0: {0: Support(target=2)}, 2: {2: Move(dest=1)}, 1: {1: Hold()}},
    )
    assert s2.ownership[1] == 2  # p2 captured the dislodged ally's center
    assert s2.reputation.get(0, ReputationTally()).intent_breaches == 1


# --- H2: abandoned declared defense of an ally ------------------------------


def test_abandoned_declared_support_of_dislodged_ally_is_harmful_breach() -> None:
    """p0 DECLARED Support(p1's unit), then did something else, and p1's unit
    was dislodged this turn. Abandoning a pledged defense that then fails is
    H2 — even though p0 didn't swing the killing blow."""
    # p1's u1 at n1 attacked by p2 (u2 at n2 + u3 at n3 supporting). p0's u0 at
    # n0 DECLARED Support(u1) but Holds instead; u1 falls 2-strength vs 1.
    s = _state(
        [Unit(0, 0, 0), Unit(1, 1, 1), Unit(2, 2, 2), Unit(3, 3, 3)],
        num_players=4,
        ownership_overrides={1: 1},
    )
    intent = Intent(unit_id=0, declared_order=Support(target=1), visible_to=None)
    s2 = _finalize(
        s,
        {0: Press(stance=_ally(1), intents=[intent])},
        {
            0: {0: Hold()},           # abandoned the pledged support
            1: {1: Hold()},
            2: {2: Move(dest=1)},     # p2 attacks
            3: {3: Support(target=2)},  # p3 backs p2 -> strength 2 vs 1
        },
    )
    assert s2.ownership[1] == 2  # ally's center fell
    assert s2.reputation.get(0, ReputationTally()).intent_breaches == 1


def test_abandoned_support_but_ally_survives_is_not_a_breach() -> None:
    """Same abandoned-Support declaration, but the ally is NOT dislodged
    (attack bounces). No harm materialized -> not a breach (H2 requires the
    protected unit to actually fall)."""
    s = _state(
        [Unit(0, 0, 0), Unit(1, 1, 1), Unit(2, 2, 2)],
        num_players=3,
        ownership_overrides={1: 1},
    )
    intent = Intent(unit_id=0, declared_order=Support(target=1), visible_to=None)
    s2 = _finalize(
        s,
        {0: Press(stance=_ally(1), intents=[intent])},
        {
            0: {0: Hold()},
            1: {1: Hold()},
            2: {2: Move(dest=1)},  # 1 vs 1 -> bounce, u1 survives
        },
    )
    assert s2.ownership[1] == 1  # ally held
    assert s2.reputation == {}


# --- public intent counted once; observer-eliminated still counts -----------


def test_harmful_public_breach_counted_once_not_per_observer() -> None:
    s = _state(
        [Unit(0, 0, 0), Unit(2, 0, 2), Unit(1, 1, 1)],
        num_players=3,
        ownership_overrides={1: 1},
    )
    intent = Intent(unit_id=0, declared_order=Hold(), visible_to=None)
    s2 = _finalize(
        s,
        {0: Press(stance=_ally(1, 2), intents=[intent])},
        {0: {0: Move(dest=1), 2: Support(target=0)}, 1: {1: Hold()},
         2: {}},
    )
    # Two allies declared (p1, p2) but only p1 was harmed; still ONE breach.
    assert s2.reputation.get(0, ReputationTally()).intent_breaches == 1


# --- pacts are harm-typed too -----------------------------------------------


def test_harmful_pact_breach_records_and_fines() -> None:
    """p0 breaks a pact term with co-signer p1 by dislodging p1 -> harmful
    pact breach: reputation.pact_breaches + the pact fine."""
    s = _state(
        [Unit(0, 0, 0), Unit(2, 0, 2), Unit(1, 1, 1)],
        num_players=2,
        ownership_overrides={1: 1},
    )
    pact = Pact(
        pact_id=0, proposer=0, counterparty=1,
        terms=(PactTerm(player=0, unit_id=0, declared_order=Hold()),
               PactTerm(player=1, unit_id=1, declared_order=Hold())),
        status=PactStatus.ACCEPTED, proposed_turn=0,
    )
    s = replace(s, pacts=[pact])
    s2 = _finalize(
        s, {},
        {0: {0: Move(dest=1), 2: Support(target=0)}, 1: {1: Hold()}},
    )
    assert s2.reputation.get(0, ReputationTally()).pact_breaches == 1


def test_prosocial_pact_divergence_is_not_a_breach() -> None:
    """p0 committed a Move under a pact with p1, but redirects to SUPPORT p1.
    Helping the co-signer harms nobody committed -> not a breach."""
    s = _state([Unit(0, 0, 0), Unit(1, 1, 1)], num_players=2)
    pact = Pact(
        pact_id=0, proposer=0, counterparty=1,
        terms=(PactTerm(player=0, unit_id=0, declared_order=Move(dest=2)),
               PactTerm(player=1, unit_id=1, declared_order=Move(dest=2))),
        status=PactStatus.ACCEPTED, proposed_turn=0,
    )
    s = replace(s, pacts=[pact])
    s2 = _finalize(
        s, {},
        {0: {0: Support(target=1)}, 1: {1: Move(dest=2)}},
    )
    assert s2.reputation == {}


# --- the penalty is score-legible: on-vs-off diff equals the fine -----------


def test_harmful_intent_penalty_isolated_via_on_off_diff() -> None:
    """Score-legibility for the sweep: turning the harm-typed intent penalty
    off recovers exactly `intent_breach_penalty` for the harmful breacher,
    and NOTHING for a pro-social redirect (which isn't a breach)."""
    def run(penalty, orders, stance):
        s = _state(
            [Unit(0, 0, 0), Unit(2, 0, 2), Unit(1, 1, 1)],
            num_players=2, ownership_overrides={1: 1},
        )
        s = replace(s, config=replace(s.config, intent_breach_penalty=penalty))
        intent = Intent(unit_id=0, declared_order=Hold(), visible_to=None)
        s2 = _finalize(s, {0: Press(stance=stance, intents=[intent])}, orders)
        return s2.scores[0]

    harmful = {0: {0: Move(dest=1), 2: Support(target=0)}, 1: {1: Hold()}}
    on = run(1.0, harmful, _ally(1))
    off = run(0.0, harmful, _ally(1))
    assert off - on == 1.0  # the harmful breach paid exactly the fine


def test_intent_penalty_default_positive() -> None:
    assert GameConfig().intent_breach_penalty > 0
    assert GameConfig().pact_breach_penalty > 0
