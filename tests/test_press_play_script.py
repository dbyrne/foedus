"""Tests for scripts/foedus_press_play.py — Phase 0a (F1/F2/F3): the
orchestrator's prompts must show the same arena-legibility sections as the
game server (foedus/game_server/render.py), via the shared
foedus.render_common helpers, plus a visible over-cap chat error instead of
a silent drop.

No test file previously covered this script; it manages its own state via
fixed /tmp paths (documented as acceptable for a one-off playtest tool), so
tests here monkeypatch those module-level path constants to a tmp_path.
"""

from __future__ import annotations

import json

from scripts import foedus_press_play as pp


def _init_state(monkeypatch, tmp_path, **cfg_kwargs):
    state_file = tmp_path / "state.pickle"
    monkeypatch.setattr(pp, "STATE_FILE", state_file)

    from foedus.core import Archetype, GameConfig
    from foedus.mapgen import generate_map
    from foedus.resolve import initial_state

    cfg = GameConfig(
        num_players=4, max_turns=7, seed=42,
        archetype=Archetype.CONTINENTAL_SWEEP,
        **cfg_kwargs,
    )
    m = generate_map(cfg.num_players, seed=cfg.seed,
                     archetype=cfg.archetype, map_radius=cfg.map_radius)
    state = initial_state(cfg, m)
    pp.save(state)
    return state


def test_prompt_commit_states_capture_rule_and_income_ledger(
    monkeypatch, tmp_path, capsys,
) -> None:
    _init_state(monkeypatch, tmp_path)
    pp.cmd_prompt_commit(0)
    out = capsys.readouterr().out
    assert "CAPTURE RULE" in out
    assert "INCOME:" in out
    assert "Build turns:" in out


def test_prompt_commit_shows_adjacency_table_and_turn_calendar(
    monkeypatch, tmp_path, capsys,
) -> None:
    _init_state(monkeypatch, tmp_path)
    pp.cmd_prompt_commit(0)
    out = capsys.readouterr().out
    assert "ADJACENCY" in out
    assert "TURN CALENDAR" in out


def test_prompt_commit_shows_betrayal_ledger(
    monkeypatch, tmp_path, capsys,
) -> None:
    _init_state(monkeypatch, tmp_path)
    pp.cmd_prompt_commit(0)
    out = capsys.readouterr().out
    assert "BETRAYAL LEDGER" in out


def test_prompt_commit_map_shows_supply_values(
    monkeypatch, tmp_path, capsys,
) -> None:
    state = _init_state(monkeypatch, tmp_path)
    pp.cmd_prompt_commit(0)
    out = capsys.readouterr().out
    # At least one SUPPLY node exists on a CONTINENTAL_SWEEP map; its
    # rendered label must include the exact $<value> suffix (not just a
    # bare "$" mark with the value elided).
    from foedus.core import NodeType
    supply_nodes = [n for n, t in state.map.node_types.items()
                    if t == NodeType.SUPPLY]
    assert supply_nodes
    assert any(f"{n}${state.map.supply_value(n)}" in out for n in supply_nodes)


def test_prompt_chat_states_capture_rule_and_turn_calendar(
    monkeypatch, tmp_path, capsys,
) -> None:
    _init_state(monkeypatch, tmp_path)
    pp.cmd_prompt_chat(0)
    out = capsys.readouterr().out
    assert "CAPTURE RULE" in out
    assert "TURN CALENDAR" in out


def test_apply_chat_over_cap_gives_visible_specific_error(
    monkeypatch, tmp_path, capsys,
) -> None:
    state = _init_state(monkeypatch, tmp_path)
    cap = state.config.chat_char_cap
    draft_path = tmp_path / "chat.json"
    long_body = "x" * (cap + 1)
    draft_path.write_text(json.dumps({"recipients": None, "body": long_body}))

    pp.cmd_apply_chat(0, str(draft_path))
    out = capsys.readouterr().out
    assert "ERROR" in out
    assert "exceeds" in out
    assert str(cap) in out
    assert str(len(long_body)) in out


def test_cmd_init_conflict_preset_uses_conflict_forcing_config(
    monkeypatch, tmp_path, capsys,
) -> None:
    """Phase 0a (F3): `init conflict` wires up the conflict-forcing preset
    (scripts/foedus_press_play.py::cmd_init) for the exit-gate re-test."""
    state_file = tmp_path / "state.pickle"
    monkeypatch.setattr(pp, "STATE_FILE", state_file)
    monkeypatch.setattr(pp, "CHAT_FILE", lambda p: tmp_path / f"chat_p{p}.json")
    monkeypatch.setattr(pp, "COMMIT_FILE", lambda p: tmp_path / f"commit_p{p}.json")
    monkeypatch.setattr(pp, "ORDERS_PICKLE", lambda p: tmp_path / f"orders_p{p}.pickle")

    pp.cmd_init("conflict")
    state = pp.load()
    assert state.config.max_turns == 15
    assert state.config.map_radius == 2


def test_cmd_init_default_preset_unchanged(
    monkeypatch, tmp_path, capsys,
) -> None:
    state_file = tmp_path / "state.pickle"
    monkeypatch.setattr(pp, "STATE_FILE", state_file)
    monkeypatch.setattr(pp, "CHAT_FILE", lambda p: tmp_path / f"chat_p{p}.json")
    monkeypatch.setattr(pp, "COMMIT_FILE", lambda p: tmp_path / f"commit_p{p}.json")
    monkeypatch.setattr(pp, "ORDERS_PICKLE", lambda p: tmp_path / f"orders_p{p}.pickle")

    pp.cmd_init()
    state = pp.load()
    assert state.config.max_turns == 7
    assert state.config.map_radius == 3


def test_apply_chat_within_cap_still_succeeds(
    monkeypatch, tmp_path, capsys,
) -> None:
    _init_state(monkeypatch, tmp_path)
    draft_path = tmp_path / "chat.json"
    draft_path.write_text(json.dumps({"recipients": None, "body": "hi"}))

    pp.cmd_apply_chat(0, str(draft_path))
    out = capsys.readouterr().out
    assert "player 0 chat" in out
    state = pp.load()
    assert any(m.body == "hi" for m in state.round_chat)
