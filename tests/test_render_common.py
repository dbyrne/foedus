"""Tests for foedus.render_common — shared prompt-rendering helpers used by
both foedus/game_server/render.py and scripts/foedus_press_play.py (Phase 0a,
F1/F2: economy transparency + support/board legibility).
"""

from __future__ import annotations

from dataclasses import replace

from foedus.core import (
    BetrayalObservation,
    Hold,
    Intent,
    Move,
    NodeType,
    Support,
    Unit,
)
from foedus.press import finalize_round, signal_done, submit_press_tokens
from foedus.core import Press
from foedus.render_common import (
    CAPTURE_RULE_TEXT,
    build_turns,
    income_ledger,
    node_label,
    order_to_str,
    render_adjacency_table,
    render_betrayal_ledger,
    render_income_ledger,
    render_map,
    render_turn_calendar,
)

from tests.helpers import line_map, make_state, triangle_map


# --- node_label --------------------------------------------------------


def test_node_label_supply_shows_value() -> None:
    m = line_map(3)  # node 1 is SUPPLY, default value 1
    assert node_label(m, 1) == "1$1"


def test_node_label_supply_shows_high_value() -> None:
    m = line_map(3)
    m = replace(m, supply_values={1: 2})
    assert node_label(m, 1) == "1$2"


def test_node_label_home_has_no_value_suffix() -> None:
    m = line_map(3)  # node 0 is HOME
    assert node_label(m, 0) == "0H"


def test_node_label_plain_is_bare_id() -> None:
    m = triangle_map()
    m = replace(m, node_types={**m.node_types, 1: NodeType.PLAIN})
    assert node_label(m, 1) == "1"


def test_node_label_mountain_and_water_marks() -> None:
    m = triangle_map()
    m = replace(m, node_types={**m.node_types, 1: NodeType.MOUNTAIN,
                                2: NodeType.WATER})
    assert node_label(m, 1) == "1^"
    assert node_label(m, 2) == "2~"


# --- order_to_str --------------------------------------------------------


def test_order_to_str_hold() -> None:
    assert order_to_str(Hold()) == "Hold"


def test_order_to_str_move_without_state_uses_bare_id() -> None:
    assert order_to_str(Move(dest=5)) == "Move(dest=5)"


def test_order_to_str_move_with_state_shows_node_label() -> None:
    m = line_map(3)
    m = replace(m, supply_values={1: 2})
    s = make_state(m, [Unit(0, 0, 0), Unit(1, 1, 2)], num_players=2)
    assert order_to_str(Move(dest=1), s) == "Move(dest=1$2)"


def test_order_to_str_support_without_state_is_bare() -> None:
    assert order_to_str(Support(target=3)) == "Support(target=u3)"


def test_order_to_str_support_with_state_shows_owner_and_location() -> None:
    m = triangle_map()
    s = make_state(m, [Unit(0, 0, 0), Unit(1, 1, 1), Unit(2, 2, 2)],
                   num_players=3)
    # u0's supporter formats a Support(target=u1) referencing p1's unit @ n1.
    assert order_to_str(Support(target=1), s) == "Support(target=u1 [P1 @ n1])"


def test_order_to_str_support_with_require_dest_and_state() -> None:
    m = triangle_map()
    s = make_state(m, [Unit(0, 0, 0), Unit(1, 1, 1), Unit(2, 2, 2)],
                   num_players=3)
    out = order_to_str(Support(target=1, require_dest=2), s)
    assert out == "Support(target=u1 [P1 @ n1], require_dest=2)"


def test_order_to_str_support_target_gone_falls_back_gracefully() -> None:
    m = triangle_map()
    s = make_state(m, [Unit(0, 0, 0)], num_players=3)
    assert order_to_str(Support(target=99), s) == "Support(target=u99)"


def test_order_to_str_move_bare_ignores_state() -> None:
    """bare=True is for machine-facing text an LLM must copy into JSON --
    7$1 is not a valid JSON token, so even with state available the value
    annotation must be suppressed."""
    m = line_map(3)
    m = replace(m, supply_values={1: 2})
    s = make_state(m, [Unit(0, 0, 0), Unit(1, 1, 2)], num_players=2)
    assert order_to_str(Move(dest=1), s, bare=True) == "Move(dest=1)"


def test_order_to_str_support_bare_ignores_state() -> None:
    """Same rationale as the Move case -- bare=True must also drop the "u"
    prefix (u3 is not a valid bare JSON int either) and the owner/location
    annotation."""
    m = triangle_map()
    s = make_state(m, [Unit(0, 0, 0), Unit(1, 1, 1), Unit(2, 2, 2)],
                   num_players=3)
    assert order_to_str(Support(target=1), s, bare=True) == "Support(target=1)"


def test_order_to_str_support_bare_with_require_dest() -> None:
    m = triangle_map()
    s = make_state(m, [Unit(0, 0, 0), Unit(1, 1, 1), Unit(2, 2, 2)],
                   num_players=3)
    out = order_to_str(Support(target=1, require_dest=2), s, bare=True)
    assert out == "Support(target=1, require_dest=2)"


# --- render_map ------------------------------------------------------------


def test_render_map_embeds_supply_value() -> None:
    m = line_map(3)
    m = replace(m, supply_values={1: 2})
    s = make_state(m, [Unit(0, 0, 0), Unit(1, 1, 2)], num_players=2)
    out = render_map(s)
    assert "1$2" in out


# --- build_turns -------------------------------------------------------


def test_build_turns_lists_multiples_of_build_period_up_to_max_turns() -> None:
    m = line_map(3)
    s = make_state(m, [Unit(0, 0, 0), Unit(1, 1, 2)], num_players=2,
                   build_period=3, max_turns=7)
    assert build_turns(s) == [3, 6]


# --- income ledger -----------------------------------------------------


def test_income_ledger_reflects_owned_centers_before_any_turn() -> None:
    m = line_map(3)
    s = make_state(m, [Unit(0, 0, 0), Unit(1, 1, 2)], num_players=2)
    data = income_ledger(s, 0)
    assert data["owned"] == [(0, 1)]  # home node 0, value 1
    assert data["per_turn"] == 1
    assert data["occupying"] == []
    assert data["last_turn_delta"] == 0.0


def test_income_ledger_shows_occupying_not_yet_converted() -> None:
    """A fresh walk-in onto an unowned supply shows in OCCUPYING, not OWN,
    until it's held through the next resolution (Mechanic A)."""
    m = line_map(3)
    s = make_state(m, [Unit(0, 0, 0), Unit(1, 1, 2)], num_players=2)
    s2 = finalize_round(
        _all_done(s), {0: {0: Move(dest=1)}, 1: {1: Hold()}}
    )
    data = income_ledger(s2, 0)
    assert data["owned"] == [(0, 1)]
    assert data["occupying"] == [(1, 1)]


def test_income_ledger_matches_actual_score_delta_after_resolution() -> None:
    m = line_map(3)
    s = make_state(m, [Unit(0, 0, 0), Unit(1, 1, 2)], num_players=2)
    s2 = finalize_round(_all_done(s), {0: {0: Hold()}, 1: {1: Hold()}})
    data = income_ledger(s2, 0)
    assert data["last_turn_delta"] == s2.last_turn_score_delta[0]
    assert data["last_turn_delta"] == 1.0


def test_render_income_ledger_text_contains_key_numbers() -> None:
    m = line_map(3)
    s = make_state(m, [Unit(0, 0, 0), Unit(1, 1, 2)], num_players=2)
    s2 = finalize_round(_all_done(s), {0: {0: Hold()}, 1: {1: Hold()}})
    out = render_income_ledger(s2, 0)
    assert "OWN" in out
    assert "0(v1)" in out
    assert "+1" in out
    assert "Last turn you scored +1" in out
    assert "Build turns:" in out


# --- adjacency table -----------------------------------------------------


def test_render_adjacency_table_lists_neighbors_for_given_nodes() -> None:
    m = line_map(3)
    m = replace(m, supply_values={1: 2})
    s = make_state(m, [Unit(0, 0, 0), Unit(1, 1, 2)], num_players=2)
    out = render_adjacency_table(s, [0, 1, 2])
    assert "0H: 1$2" in out
    assert "1$2: 0H, 2H" in out
    assert "2H: 1$2" in out


# --- turn calendar -----------------------------------------------------


def test_render_turn_calendar_shows_turn_and_build_turns() -> None:
    m = line_map(3)
    s = make_state(m, [Unit(0, 0, 0), Unit(1, 1, 2)], num_players=2,
                   build_period=3, max_turns=7)
    out = render_turn_calendar(s)
    assert "1/7" in out
    assert "[3, 6]" in out


# --- betrayal ledger -----------------------------------------------------


def test_render_betrayal_ledger_empty() -> None:
    m = triangle_map()
    s = make_state(m, [Unit(0, 0, 0)], num_players=3)
    out = render_betrayal_ledger(s, 0)
    assert "none observed" in out.lower()


def test_render_betrayal_ledger_shows_counts_by_betrayer() -> None:
    m = triangle_map()
    s = make_state(m, [Unit(0, 0, 0)], num_players=3)
    obs = [
        BetrayalObservation(
            turn=1, betrayer=1,
            intent=Intent(unit_id=5, declared_order=Hold(), visible_to=None),
            actual_order=Move(dest=2),
        ),
        BetrayalObservation(
            turn=2, betrayer=1,
            intent=Intent(unit_id=5, declared_order=Hold(), visible_to=None),
            actual_order=Move(dest=2),
        ),
    ]
    s = replace(s, betrayals={0: obs})
    out = render_betrayal_ledger(s, 0)
    assert "p1=2" in out
    assert "turn 2" in out


# --- capture rule text -----------------------------------------------------


def test_capture_rule_text_states_hold_and_persistence() -> None:
    assert "Hold" in CAPTURE_RULE_TEXT
    assert "passing through" in CAPTURE_RULE_TEXT.lower()
    assert "stays yours" in CAPTURE_RULE_TEXT.lower()


def test_capture_rule_text_states_instant_combat_capture() -> None:
    """Code review finding: the walk-then-Hold sentence alone undersells the
    combat path — dislodging an enemy unit on a supply/home flips ownership
    IMMEDIATELY that same turn (resolve.py rule (a)), no Hold required. The
    text must say so explicitly, not just imply it via the "how it's lost"
    framing, since surfacing real combat is this phase's whole point."""
    assert "dislodg" in CAPTURE_RULE_TEXT.lower()
    assert "instant" in CAPTURE_RULE_TEXT.lower()


def _all_done(s):
    for p in range(s.config.num_players):
        s = submit_press_tokens(s, p, Press(stance={}, intents=[]))
        s = signal_done(s, p)
    return s
