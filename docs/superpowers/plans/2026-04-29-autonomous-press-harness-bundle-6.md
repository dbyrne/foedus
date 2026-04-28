# Bundle 6 Autonomous Press Harness — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend `foedus.game_server` with press-aware HTTP endpoints (chat, commit, prompt rendering, long-poll wait) plus a blocking subagent client, so that two LLM subagents can play a press game autonomously without controller mediation.

**Architecture:** Add `chat_done` field to GameState + 2 helpers in `foedus/press.py`. Extract prompt rendering to a new shared module. Extend `GameSession` with press-flow tracking. Add 5 new HTTP routes. Build a thin Python client (`scripts/foedus_press_client.py`) using only stdlib `urllib`.

**Tech Stack:** Python 3.10+, FastAPI (existing), pytest, `uvicorn` (already a dependency for game_server tests). No new third-party deps.

**Spec:** `docs/superpowers/specs/2026-04-29-autonomous-press-harness-design.md` (committed at `d366383`).

**Branch:** `bundle6-autonomous-press-harness` (already created off main; commit `d366383` holds the design doc).

---

## File Structure

| File | Status | Responsibility |
|---|---|---|
| `foedus/core.py` | Modify | Add `chat_done: set[PlayerId]` field to `GameState` |
| `foedus/press.py` | Modify | Add `signal_chat_done`, `is_chat_phase_complete`; reset `chat_done` in `finalize_round` |
| `foedus/remote/wire.py` | Modify | Serialize/deserialize `chat_done` |
| `foedus/game_server/render.py` | Create | Render chat-prompt and commit-prompt as plain-text strings (extracted from `scripts/foedus_press_play.py`) |
| `foedus/game_server/session.py` | Modify | Press-flow tracking: pre-compute agent press+orders at round start, accept LLM press+orders+signal_done at commit, auto-finalize on `is_round_complete` |
| `foedus/game_server/server.py` | Modify | 5 new endpoints (chat, commit, two prompt GETs, wait long-poll) |
| `scripts/foedus_press_client.py` | Create | Blocking subagent client (one player, runs full game) |
| `scripts/foedus_press_server.py` | Create | Convenience wrapper that runs `uvicorn` with sane defaults |
| `tests/test_press_session.py` | Create | Unit tests for new session methods |
| `tests/test_press_server.py` | Create | Integration tests for 5 new endpoints |
| `tests/test_press.py` (existing) | Modify | Add tests for `signal_chat_done`, `is_chat_phase_complete`, `finalize_round` reset of `chat_done` |
| `tests/test_remote_wire.py` (existing) | Modify | Add wire roundtrip tests for `chat_done` |

---

## Task 1: Engine — `chat_done` field + helpers

**Files:**
- Modify: `foedus/core.py`
- Modify: `foedus/press.py`
- Modify: `tests/test_press.py`

- [ ] **Step 1: Add `chat_done` field to `GameState`**

In `foedus/core.py`, find the `GameState` dataclass (around lines 188-211 — search for `class GameState`). Find the existing `round_done: set[PlayerId] = field(default_factory=set)` line. Add a new line directly after it:

```python
    chat_done: set[PlayerId] = field(default_factory=set)
```

This field tracks which surviving players have explicitly closed their chat phase for the current round (Bundle 6).

- [ ] **Step 2: Add `signal_chat_done` and `is_chat_phase_complete` to `foedus/press.py`**

In `foedus/press.py`, find the existing `def signal_done(state: GameState, player: PlayerId)` function. Directly after it, add:

```python
def signal_chat_done(state: GameState, player: PlayerId) -> GameState:
    """Mark a player as done with the chat phase. Idempotent.

    Bundle 6: gates the commit-phase opening. Cannot be undone within a
    round. Returns state unchanged if phase is not NEGOTIATION or player
    is eliminated.
    """
    if state.phase != Phase.NEGOTIATION:
        return state
    if player in state.eliminated:
        return state
    new_chat_done = set(state.chat_done)
    new_chat_done.add(player)
    return replace(state, chat_done=new_chat_done)


def is_chat_phase_complete(state: GameState) -> bool:
    """True iff every surviving player has signaled chat-done.

    Bundle 6: when this returns True, the chat phase is closed and
    /commit submissions become valid.
    """
    survivors = {
        p for p in range(state.config.num_players) if p not in state.eliminated
    }
    return survivors.issubset(state.chat_done)
```

- [ ] **Step 3: Reset `chat_done` in `finalize_round`**

Still in `foedus/press.py`, find `def finalize_round` (around line 232). At its very end, find the `replace(s_after, ...)` call. The existing kwargs include `round_chat=[], round_press_pending={}, round_done=set()`. Add a new kwarg:

```python
        chat_done=set(),
```

Place it directly after `round_done=set()` for visual grouping. The full reset block should now look like:

```python
        # Reset round scratch fields for next turn.
        phase=Phase.NEGOTIATION,
        round_chat=[],
        round_press_pending={},
        round_done=set(),
        chat_done=set(),
    )
```

- [ ] **Step 4: Write the engine tests**

Append to `tests/test_press.py` (the existing file; don't create a new one):

```python
# --- Bundle 6: chat-done tracking --------------------------------------


def test_signal_chat_done_marks_player() -> None:
    from foedus.press import signal_chat_done
    cfg = GameConfig(num_players=3)
    m = generate_map(3, seed=42)
    s = initial_state(cfg, m)
    assert 0 not in s.chat_done
    s2 = signal_chat_done(s, 0)
    assert 0 in s2.chat_done
    assert 1 not in s2.chat_done


def test_signal_chat_done_idempotent() -> None:
    from foedus.press import signal_chat_done
    cfg = GameConfig(num_players=3)
    m = generate_map(3, seed=42)
    s = initial_state(cfg, m)
    s2 = signal_chat_done(s, 0)
    s3 = signal_chat_done(s2, 0)
    assert s3.chat_done == {0}


def test_signal_chat_done_skips_eliminated() -> None:
    from foedus.press import signal_chat_done
    cfg = GameConfig(num_players=3)
    m = generate_map(3, seed=42)
    s = initial_state(cfg, m)
    s.eliminated.add(1)
    s2 = signal_chat_done(s, 1)
    assert s2.chat_done == set(), \
        "eliminated player should not be added to chat_done"


def test_is_chat_phase_complete_false_when_some_pending() -> None:
    from foedus.press import is_chat_phase_complete, signal_chat_done
    cfg = GameConfig(num_players=3)
    m = generate_map(3, seed=42)
    s = initial_state(cfg, m)
    assert is_chat_phase_complete(s) is False
    s = signal_chat_done(s, 0)
    s = signal_chat_done(s, 1)
    assert is_chat_phase_complete(s) is False, "p2 still pending"


def test_is_chat_phase_complete_true_when_all_signaled() -> None:
    from foedus.press import is_chat_phase_complete, signal_chat_done
    cfg = GameConfig(num_players=3)
    m = generate_map(3, seed=42)
    s = initial_state(cfg, m)
    for p in range(3):
        s = signal_chat_done(s, p)
    assert is_chat_phase_complete(s) is True


def test_is_chat_phase_complete_skips_eliminated() -> None:
    """Eliminated players are not required to signal."""
    from foedus.press import is_chat_phase_complete, signal_chat_done
    cfg = GameConfig(num_players=3)
    m = generate_map(3, seed=42)
    s = initial_state(cfg, m)
    s.eliminated.add(2)
    s = signal_chat_done(s, 0)
    s = signal_chat_done(s, 1)
    assert is_chat_phase_complete(s) is True


def test_finalize_round_resets_chat_done() -> None:
    """finalize_round must clear chat_done for the next round."""
    from foedus.press import (
        finalize_round, signal_chat_done, signal_done,
        submit_press_tokens,
    )
    cfg = GameConfig(num_players=2, max_turns=10)
    m = generate_map(2, seed=42)
    s = initial_state(cfg, m)
    for p in range(2):
        s = submit_press_tokens(s, p, Press(stance={}, intents=[]))
        s = signal_chat_done(s, p)
        s = signal_done(s, p)
    s = finalize_round(s, {})
    assert s.chat_done == set(), "chat_done not reset"
```

(The existing test file already imports `GameConfig`, `Press`, `generate_map`, `initial_state` etc. — add the new tests at the bottom of the file.)

- [ ] **Step 5: Run tests**

Run: `python3 -m pytest tests/test_press.py -v -k "chat_done or chat_phase_complete or finalize_round_resets_chat_done"`

Expected: 7 passed.

- [ ] **Step 6: Run full suite**

Run: `python3 -m pytest -q`

Expected: 338 baseline + 7 new = 345 passed (or thereabouts), 1 skipped, 0 failed.

- [ ] **Step 7: Commit**

```bash
git add foedus/core.py foedus/press.py tests/test_press.py
git commit -m "$(cat <<'EOF'
Bundle 6: engine — chat_done tracking for chat-phase sync

Adds GameState.chat_done (set[PlayerId]) and two helpers in
foedus/press.py:
  signal_chat_done(state, player) — mark player as chat-phase done
  is_chat_phase_complete(state) — True iff all survivors signaled

finalize_round now resets chat_done alongside the other round-scratch
fields. 7 new unit tests cover the standard paths plus the elimination
edge case and the reset.

Spec: docs/superpowers/specs/2026-04-29-autonomous-press-harness-design.md

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Wire serialization for `chat_done`

**Files:**
- Modify: `foedus/remote/wire.py`
- Modify: `tests/test_remote_wire.py`

The wire module serializes/deserializes `GameState` to/from JSON for HTTP transport. It must roundtrip the new `chat_done` field.

- [ ] **Step 1: Add `chat_done` to serialization**

In `foedus/remote/wire.py`, find `serialize_state` (search for `def serialize_state`). It returns a dict with keys like `"turn"`, `"map"`, `"units"`, `"ownership"`, etc. There's a section that serializes round-scratch fields including `"round_done"`. Find the line:

```python
        "round_done": sorted(state.round_done),
```

Add a new line directly after it:

```python
        "chat_done": sorted(state.chat_done),
```

Then find `deserialize_state` further down. There's a corresponding section that reconstructs `round_done` from the dict. Find the line:

```python
        round_done=set(data.get("round_done", [])),
```

(Or however it's spelled — match the existing style.) Add a new line directly after it:

```python
        chat_done=set(data.get("chat_done", [])),
```

The `data.get(..., [])` default ensures backward-compat: a serialized blob from a pre-Bundle-6 client (no `chat_done` key) deserializes as an empty set.

- [ ] **Step 2: Write the wire roundtrip test**

Append to `tests/test_remote_wire.py`:

```python
def test_chat_done_roundtrips() -> None:
    """Bundle 6: chat_done is preserved across (de)serialize."""
    from foedus.press import signal_chat_done
    cfg = GameConfig(num_players=3)
    m = generate_map(3, seed=42)
    s = initial_state(cfg, m)
    s = signal_chat_done(s, 0)
    s = signal_chat_done(s, 2)

    blob = serialize_state(s)
    assert sorted(blob["chat_done"]) == [0, 2]

    s2 = deserialize_state(blob)
    assert s2.chat_done == {0, 2}


def test_deserialize_state_without_chat_done_defaults_empty() -> None:
    """Backward-compat: blobs from older clients (no chat_done key)
    deserialize cleanly with an empty chat_done."""
    cfg = GameConfig(num_players=3)
    m = generate_map(3, seed=42)
    s = initial_state(cfg, m)
    blob = serialize_state(s)
    # Simulate a pre-Bundle-6 blob by removing the new key.
    blob.pop("chat_done", None)
    s2 = deserialize_state(blob)
    assert s2.chat_done == set()
```

(The existing test file imports `GameConfig`, `serialize_state`, `deserialize_state`, `generate_map`, `initial_state` — confirm and add at bottom.)

- [ ] **Step 3: Run tests**

Run: `python3 -m pytest tests/test_remote_wire.py -v -k "chat_done"`

Expected: 2 passed.

- [ ] **Step 4: Run full suite**

Run: `python3 -m pytest -q`

Expected: 347 passed (345 + 2 new), 1 skipped.

- [ ] **Step 5: Commit**

```bash
git add foedus/remote/wire.py tests/test_remote_wire.py
git commit -m "$(cat <<'EOF'
Bundle 6: wire — (de)serialize chat_done

Bidirectional support for the new GameState.chat_done field. Backward
compat: deserializing a pre-Bundle-6 blob (no chat_done key) yields an
empty set, not an error.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Render module — chat-prompt + commit-prompt

**Files:**
- Create: `foedus/game_server/render.py`
- Create: `tests/test_press_render.py`

This task extracts the prompt-rendering logic from `scripts/foedus_press_play.py` (lines for `cmd_prompt_chat` and `cmd_prompt_commit`) into a server-shared module that returns plain-text strings. The orchestrator script can later be migrated to use this same module.

- [ ] **Step 1: Create `foedus/game_server/render.py`**

```python
"""Press-aware prompt rendering for the game server.

Functions here build the plain-text prompts shown to LLM-seat players in
chat phase and commit phase. Logic ported from scripts/foedus_press_play.py
so the server can serve the same prompts that the orchestrator script
prints to stdout.

Spec: docs/superpowers/specs/2026-04-29-autonomous-press-harness-design.md
"""

from __future__ import annotations

from io import StringIO

from foedus.core import (
    GameState,
    Hold,
    Move,
    NodeType,
    Order,
    PlayerId,
    SupportHold,
    SupportMove,
)
from foedus.fog import visible_state_for
from foedus.legal import legal_orders_for_unit


def _order_to_str(o: Order) -> str:
    if isinstance(o, Hold):
        return "Hold"
    if isinstance(o, Move):
        return f"Move(dest={o.dest})"
    if isinstance(o, SupportHold):
        return f"SupportHold(target=u{o.target})"
    if isinstance(o, SupportMove):
        return (f"SupportMove(target=u{o.target}, "
                f"target_dest={o.target_dest})")
    return str(o)


def _render_map(state: GameState) -> str:
    """ASCII hex map with owner + node-type marks."""
    coords = state.map.coords
    qs = [c[0] for c in coords.values()]
    rs = [c[1] for c in coords.values()]
    qmin, qmax = min(qs), max(qs)
    rmin, rmax = min(rs), max(rs)
    by_qr = {coords[n]: n for n in coords}
    occupant = {u.location: u for u in state.units.values()}
    lines = []
    for r in range(rmin, rmax + 1):
        indent = " " * (3 * (r - rmin))
        row = indent
        for q in range(qmin, qmax + 1):
            n = by_qr.get((q, r))
            if n is None:
                row += "      "
                continue
            t = state.map.node_types[n]
            if t == NodeType.HOME:
                mark = "H"
            elif t == NodeType.SUPPLY:
                mark = "$"
            elif t == NodeType.MOUNTAIN:
                mark = "^"
            elif t == NodeType.WATER:
                mark = "~"
            else:
                mark = "."
            owner = state.ownership.get(n)
            owner_s = str(owner) if owner is not None else "-"
            row += f"[{n:>2}{mark}{owner_s}]"
        lines.append(row)
    return "\n".join(lines)


def render_chat_prompt(state: GameState, player: PlayerId) -> str:
    """Build the chat-phase prompt for `player`. Returns a plain-text
    string suitable for printing to stdout or returning over HTTP."""
    out = StringIO()
    view = visible_state_for(state, player)
    out.write(
        f"=== TURN {state.turn + 1}/{state.config.max_turns}, "
        f"PHASE: NEGOTIATION (chat round), YOU ARE PLAYER {player} ===\n\n"
    )

    active = sorted(
        p for p in range(state.config.num_players)
        if p != player and p not in state.eliminated
    )
    out.write(f"Active opponents: {active}\n")
    out.write(f"Your supply count: {view['supply_count_you']}\n")
    out.write(f"Scores: {view['scores']}\n")
    out.write(
        f"Mutual-ally streak: {state.mutual_ally_streak}/"
        f"{state.config.detente_threshold} (détente fires at threshold)\n\n"
    )

    if view["public_stance_matrix"]:
        out.write("PUBLIC STANCE MATRIX (last round):\n")
        for sender, stances in view["public_stance_matrix"].items():
            entries = ", ".join(
                f"p{tgt}={st}" for tgt, st in sorted(stances.items())
            )
            out.write(f"  p{sender}: {entries or '(none declared)'}\n")
        out.write("\n")

    if view["your_inbound_intents"]:
        out.write("INBOUND INTENTS YOU RECEIVED (last round):\n")
        for sender, intents in view["your_inbound_intents"].items():
            for it in intents:
                vt = ('public' if it.visible_to is None
                      else sorted(it.visible_to))
                out.write(
                    f"  p{sender} declared u{it.unit_id} -> "
                    f"{_order_to_str(it.declared_order)} "
                    f"(visible_to={vt})\n"
                )
        out.write("\n")

    if view["your_betrayals"]:
        out.write(
            f"BETRAYALS observed (cumulative, "
            f"{len(view['your_betrayals'])}):\n"
        )
        for b in view["your_betrayals"][-5:]:
            out.write(
                f"  turn {b.turn}: p{b.betrayer} declared "
                f"u{b.intent.unit_id} -> "
                f"{_order_to_str(b.intent.declared_order)}, "
                f"actually issued {_order_to_str(b.actual_order)}\n"
            )
        out.write("\n")

    if view["round_chat_so_far"]:
        out.write(
            f"CHAT THIS ROUND SO FAR ({len(view['round_chat_so_far'])} msgs):\n"
        )
        for m in view["round_chat_so_far"]:
            recip = ("public" if m.recipients is None
                     else f"to {sorted(m.recipients)}")
            out.write(f"  [p{m.sender} -> {recip}]: {m.body}\n")
        out.write("\n")
    else:
        out.write("No chat yet this round.\n\n")

    out.write("=== INSTRUCTIONS ===\n")
    out.write(
        f"You may send ONE chat message this round (max "
        f"{state.config.chat_char_cap} chars), or skip.\n\n"
    )
    out.write("RESPOND with a single JSON object — one of:\n")
    out.write('  {"recipients": null, "body": "..."}            // public broadcast\n')
    out.write('  {"recipients": [0, 2], "body": "..."}          // private\n')
    out.write('  {}                                              // skip\n\n')
    out.write(
        "Strategic context: this game has Press v0. Stance + intents are\n"
        "submitted in the COMMIT phase later. Use chat NOW to coordinate\n"
        "alliances, share plans, threaten, deceive. Betrayal observations\n"
        "are recorded if you declare an intent and don't follow through.\n"
    )
    return out.getvalue()


def render_commit_prompt(state: GameState, player: PlayerId) -> str:
    """Build the commit-phase prompt for `player`."""
    out = StringIO()
    view = visible_state_for(state, player)
    out.write(
        f"=== TURN {state.turn + 1}/{state.config.max_turns}, "
        f"PHASE: COMMIT (orders + press), YOU ARE PLAYER {player} ===\n\n"
    )

    if view["round_chat_so_far"]:
        out.write(
            f"CHAT THIS ROUND ({len(view['round_chat_so_far'])} msgs):\n"
        )
        for m in view["round_chat_so_far"]:
            recip = ("public" if m.recipients is None
                     else f"to {sorted(m.recipients)}")
            out.write(f"  [p{m.sender} -> {recip}]: {m.body}\n")
        out.write("\n")
    else:
        out.write("(no chat this round)\n\n")

    out.write(
        "MAP (^ = mountain, ~ = water, $ = supply, H = home, "
        "[node-type-owner], u<id>p<player> = unit):\n"
    )
    out.write(_render_map(state) + "\n\n")
    out.write(f"Your visible nodes: {view['visible_nodes']}\n")
    out.write(f"Your supply count: {view['supply_count_you']}\n")
    out.write(f"Scores: {view['scores']}\n")
    out.write(
        f"Mutual-ally streak: {state.mutual_ally_streak}/"
        f"{state.config.detente_threshold}\n\n"
    )

    out.write("VISIBLE UNITS:\n")
    for u in view["visible_units"]:
        marker = "(YOURS)" if u["owner"] == player else f"(player {u['owner']})"
        out.write(f"  unit u{u['id']} at node {u['location']} {marker}\n")
    out.write("\n")

    out.write("YOUR UNITS — choose ONE order per unit:\n")
    for u in state.units.values():
        if u.owner != player:
            continue
        legal = legal_orders_for_unit(state, u.id)
        out.write(
            f"  u{u.id} at node {u.location} (adj: "
            f"{sorted(state.map.neighbors(u.location))})\n"
        )
        for i, o in enumerate(legal):
            out.write(f"    [{i}] {_order_to_str(o)}\n")
    out.write("\n")

    out.write("=== RESPONSE FORMAT ===\n")
    out.write(
        "Reply with ONE JSON object combining press tokens and orders:\n"
    )
    out.write('{\n')
    out.write('  "press": {\n')
    out.write('    "stance": {"<other_pid>": "ally|neutral|hostile", ...},\n')
    out.write('    "intents": [\n')
    out.write('      {"unit_id": <int>,\n')
    out.write('       "declared_order": <order>,\n')
    out.write('       "visible_to": null | [<pid>, ...]}\n')
    out.write('    ]\n')
    out.write('  },\n')
    out.write('  "orders": {"<unit_id>": <order>, ...}\n')
    out.write('}\n\n')
    out.write('Order objects:\n')
    out.write('  {"type": "Hold"}\n')
    out.write('  {"type": "Move", "dest": <node_id>}\n')
    out.write('  {"type": "SupportHold", "target": <unit_id>}\n')
    out.write('  {"type": "SupportMove", "target": <unit_id>, '
              '"target_dest": <node_id>}\n\n')
    out.write("Notes:\n")
    out.write(
        "- press.stance / press.intents are optional; default empty.\n"
        "- visible_to=null means public broadcast; list = private group.\n"
        "- intents about units you don't own are silently dropped.\n"
        "- if your declared_order doesn't match your actual order at finalize,\n"
        "  recipients see a BetrayalObservation. Plan accordingly.\n"
        "- orders is required; default-Hold any owned unit you omit.\n"
    )
    return out.getvalue()
```

- [ ] **Step 2: Write tests**

Create `tests/test_press_render.py`:

```python
"""Bundle 6 — prompt rendering tests."""

from __future__ import annotations

from foedus.core import GameConfig
from foedus.game_server.render import render_chat_prompt, render_commit_prompt
from foedus.mapgen import generate_map
from foedus.resolve import initial_state


def test_chat_prompt_includes_turn_and_player_header() -> None:
    cfg = GameConfig(num_players=4, max_turns=7)
    m = generate_map(4, seed=42)
    s = initial_state(cfg, m)
    out = render_chat_prompt(s, 0)
    assert "TURN 1/7" in out
    assert "YOU ARE PLAYER 0" in out
    assert "PHASE: NEGOTIATION (chat round)" in out


def test_chat_prompt_lists_active_opponents() -> None:
    cfg = GameConfig(num_players=4, max_turns=7)
    m = generate_map(4, seed=42)
    s = initial_state(cfg, m)
    out = render_chat_prompt(s, 0)
    assert "Active opponents: [1, 2, 3]" in out


def test_chat_prompt_shows_supply_count_and_streak() -> None:
    cfg = GameConfig(num_players=4, max_turns=7)
    m = generate_map(4, seed=42)
    s = initial_state(cfg, m)
    out = render_chat_prompt(s, 0)
    assert "Your supply count: 1" in out
    assert "Mutual-ally streak: 0/" in out


def test_chat_prompt_includes_response_schema() -> None:
    cfg = GameConfig(num_players=4, max_turns=7)
    m = generate_map(4, seed=42)
    s = initial_state(cfg, m)
    out = render_chat_prompt(s, 0)
    assert '"recipients"' in out and '"body"' in out


def test_commit_prompt_includes_map_and_units() -> None:
    cfg = GameConfig(num_players=4, max_turns=7)
    m = generate_map(4, seed=42)
    s = initial_state(cfg, m)
    out = render_commit_prompt(s, 0)
    assert "MAP" in out
    assert "VISIBLE UNITS:" in out
    assert "YOUR UNITS" in out


def test_commit_prompt_lists_legal_orders() -> None:
    cfg = GameConfig(num_players=4, max_turns=7)
    m = generate_map(4, seed=42)
    s = initial_state(cfg, m)
    out = render_commit_prompt(s, 0)
    # P0's home unit is u0; it should be listed with at least one Hold option.
    assert "u0 at node" in out
    assert "[0] Hold" in out


def test_commit_prompt_includes_combined_schema() -> None:
    cfg = GameConfig(num_players=4, max_turns=7)
    m = generate_map(4, seed=42)
    s = initial_state(cfg, m)
    out = render_commit_prompt(s, 0)
    assert '"press"' in out and '"orders"' in out
    assert '"stance"' in out and '"intents"' in out
```

- [ ] **Step 3: Run tests**

Run: `python3 -m pytest tests/test_press_render.py -v`

Expected: 7 passed.

- [ ] **Step 4: Run full suite**

Run: `python3 -m pytest -q`

Expected: 354 passed (347 + 7 new), 1 skipped.

- [ ] **Step 5: Commit**

```bash
git add foedus/game_server/render.py tests/test_press_render.py
git commit -m "$(cat <<'EOF'
Bundle 6: render module — chat-prompt + commit-prompt

Extracts prompt-rendering logic from scripts/foedus_press_play.py into
foedus/game_server/render.py so the new HTTP endpoints can serve the
same plain-text prompts that the orchestrator script prints to stdout.
The orchestrator script is unchanged in this commit (it still has its
own copy of the rendering code); it can be migrated to use this module
in a follow-up.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Session — press flow integration

**Files:**
- Modify: `foedus/game_server/session.py`
- Create: `tests/test_press_session.py`

Extend `GameSession` with press-flow tracking. New session methods to add:

- `submit_press_chat(player, draft)` — record chat-or-skip, set `chat_done`
- `submit_press_commit(player, press, orders)` — submit press tokens, store orders, signal_done. If round complete, run finalize_round.
- `_init_round()` — at session creation AND after each finalize_round, pre-compute agent press + orders, mark them in `chat_done` and `round_done`.

The session uses the existing `agents` dict to find heuristic seats; the new code mirrors how `auto_advance` already calls `agent.choose_orders`.

- [ ] **Step 1: Add the new session methods**

In `foedus/game_server/session.py`, find the `GameSession` class (around line 84). After the existing `submit_human_orders` method, add the following block. Also import the new helpers at the top of the file.

Top-of-file imports — find the existing `from foedus.resolve import resolve_turn` line and add directly after:

```python
from foedus.press import (
    finalize_round,
    is_chat_phase_complete,
    is_round_complete,
    record_chat_message,
    signal_chat_done,
    signal_done,
    submit_press_tokens,
)
```

Inside the `GameSession` class, after `submit_human_orders` (around line 134), add:

```python
    # --- press flow (Bundle 6) ---------------------------------------------

    def init_round(self) -> None:
        """Pre-compute press + orders for agent seats and mark them as
        chat_done / round_done so they don't block sync points.

        Called once at session creation (after __post_init__ snapshots
        the initial state) AND after each finalize_round in
        submit_press_commit.
        """
        from foedus.core import Press
        for player, agent in self.agents.items():
            if not self.is_active(player):
                continue
            # Press: choose, submit, mark chat_done.
            press = (agent.choose_press(self.state, player)
                     if hasattr(agent, "choose_press")
                     else Press(stance={}, intents=[]))
            self.state = submit_press_tokens(self.state, player, press)
            self.state = signal_chat_done(self.state, player)
            # Orders: pre-compute and buffer for finalize.
            self.pending_orders[player] = agent.choose_orders(
                self.state, player
            )
            self.state = signal_done(self.state, player)

    def submit_press_chat(self, player: PlayerId,
                          draft: dict | None) -> dict:
        """Record a chat draft (or skip) for `player` and mark them
        chat_done. Returns engine drop info if the message was rejected.

        `draft` is None or `{}` to skip. Otherwise must have `body` and
        optional `recipients`.
        """
        from foedus.core import ChatDraft
        if not self.is_human(player):
            raise ValueError(f"seat {player} is not human (LLM seat)")
        if not self.is_active(player):
            raise ValueError(f"player {player} is eliminated")
        if player in self.state.chat_done:
            raise ValueError(
                f"player {player} already chat_done this round"
            )
        message_dropped = False
        drop_reason = None
        if draft:
            recipients_raw = draft.get("recipients")
            if recipients_raw is None:
                recipients = None
            else:
                recipients = frozenset(int(r) for r in recipients_raw)
            chat_draft = ChatDraft(
                recipients=recipients,
                body=str(draft.get("body", "")),
            )
            new_state = record_chat_message(
                self.state, player, chat_draft
            )
            if (new_state is self.state
                    or len(new_state.round_chat) ==
                        len(self.state.round_chat)):
                message_dropped = True
                drop_reason = (
                    f"engine dropped (len={len(chat_draft.body)}, "
                    f"cap={self.state.config.chat_char_cap})"
                )
            else:
                self.state = new_state
        self.state = signal_chat_done(self.state, player)
        return {
            "ok": True,
            "chat_phase_complete": is_chat_phase_complete(self.state),
            "message_dropped": message_dropped,
            "drop_reason": drop_reason,
        }

    def submit_press_commit(self, player: PlayerId,
                            press: "Press",
                            orders: dict[UnitId, Order]) -> dict:
        """Submit press tokens + orders + implicit signal_done for
        `player`. If this commit completes the round, runs
        finalize_round and re-initializes for the next round.

        Returns whether the round was advanced and the resulting turn.
        """
        if not self.is_human(player):
            raise ValueError(f"seat {player} is not human (LLM seat)")
        if not self.is_active(player):
            raise ValueError(f"player {player} is eliminated")
        if not is_chat_phase_complete(self.state):
            raise ValueError(
                "chat phase not complete; cannot commit yet"
            )
        if player in self.state.round_done:
            raise ValueError(
                f"player {player} already committed this round"
            )
        self.state = submit_press_tokens(self.state, player, press)
        self.pending_orders[player] = dict(orders)
        self.state = signal_done(self.state, player)
        round_advanced = False
        if is_round_complete(self.state):
            self.state = finalize_round(
                self.state, dict(self.pending_orders)
            )
            self.history.append(self.state)
            self.pending_orders.clear()
            round_advanced = True
            if not self.state.is_terminal():
                self.init_round()
        return {
            "ok": True,
            "round_advanced": round_advanced,
            "is_terminal": self.state.is_terminal(),
            "new_turn": self.state.turn,
        }
```

- [ ] **Step 2: Call `init_round` at session creation**

Find `def __post_init__` in `GameSession` (around line 99). Add a call to `init_round` at the end:

```python
    def __post_init__(self) -> None:
        if not self.history:
            self.history.append(self.state)
        # Bundle 6: pre-compute agent press+orders for round 0.
        if self.agents:
            self.init_round()
```

- [ ] **Step 3: Write session unit tests**

Create `tests/test_press_session.py`:

```python
"""Bundle 6 — GameSession press-flow integration tests."""

from __future__ import annotations

import pytest

from foedus.agents.heuristic import HeuristicAgent
from foedus.core import GameConfig, Press
from foedus.game_server.session import GameSession, SeatSpec
from foedus.mapgen import generate_map
from foedus.resolve import initial_state


def _build_session(num_llm: int = 2, num_agents: int = 2,
                   seed: int = 42, max_turns: int = 7) -> GameSession:
    """Build a session with `num_llm` human (LLM) seats and `num_agents`
    HeuristicAgent seats."""
    n = num_llm + num_agents
    cfg = GameConfig(num_players=n, max_turns=max_turns, seed=seed)
    m = generate_map(n, seed=seed)
    state = initial_state(cfg, m)
    seats = {}
    agents = {}
    for p in range(num_llm):
        seats[p] = SeatSpec(type="human", name=f"llm{p}")
    for p in range(num_llm, n):
        seats[p] = SeatSpec(type="agent", name=f"h{p}",
                            kind="foedus.agents.heuristic.HeuristicAgent")
        agents[p] = HeuristicAgent()
    return GameSession(game_id="g1", state=state, seats=seats,
                        agents=agents)


def test_init_round_marks_agent_seats_chat_and_round_done() -> None:
    """Agent seats should be in chat_done and round_done after
    init_round; LLM seats should not."""
    s = _build_session()
    assert s.state.chat_done == {2, 3}, \
        f"expected {{2,3}}, got {s.state.chat_done}"
    assert s.state.round_done == {2, 3}, \
        f"expected {{2,3}}, got {s.state.round_done}"


def test_submit_press_chat_marks_player_chat_done() -> None:
    s = _build_session()
    result = s.submit_press_chat(0, None)
    assert 0 in s.state.chat_done
    assert result["chat_phase_complete"] is False  # P1 still pending


def test_submit_press_chat_with_draft_records_message() -> None:
    s = _build_session()
    result = s.submit_press_chat(
        0, {"recipients": None, "body": "Hello all"}
    )
    assert 0 in s.state.chat_done
    assert any(m.body == "Hello all" for m in s.state.round_chat)
    assert result["message_dropped"] is False


def test_submit_press_chat_double_signal_raises() -> None:
    s = _build_session()
    s.submit_press_chat(0, None)
    with pytest.raises(ValueError):
        s.submit_press_chat(0, None)


def test_submit_press_chat_complete_when_all_llm_signaled() -> None:
    s = _build_session()
    s.submit_press_chat(0, None)
    result = s.submit_press_chat(1, None)
    assert result["chat_phase_complete"] is True


def test_submit_press_commit_blocked_until_chat_phase_complete() -> None:
    s = _build_session()
    s.submit_press_chat(0, None)
    # P1 hasn't signaled chat-done. Commit must reject.
    with pytest.raises(ValueError, match="chat phase not complete"):
        s.submit_press_commit(0, Press(stance={}, intents=[]), {})


def test_submit_press_commit_advances_round_when_all_committed() -> None:
    s = _build_session()
    s.submit_press_chat(0, None)
    s.submit_press_chat(1, None)
    # Now both LLMs commit.
    s.submit_press_commit(0, Press(stance={}, intents=[]), {})
    result = s.submit_press_commit(1, Press(stance={}, intents=[]), {})
    assert result["round_advanced"] is True
    # Turn should have advanced from 0 to 1.
    assert s.state.turn == 1


def test_full_round_resets_chat_done_for_next_round() -> None:
    s = _build_session()
    for p in (0, 1):
        s.submit_press_chat(p, None)
    s.submit_press_commit(0, Press(stance={}, intents=[]), {})
    s.submit_press_commit(1, Press(stance={}, intents=[]), {})
    # After advance, chat_done should be reset to just the agent seats
    # (init_round re-marked them).
    assert s.state.chat_done == {2, 3}
    assert s.state.round_done == {2, 3}
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_press_session.py -v`

Expected: 8 passed.

- [ ] **Step 5: Run full suite**

Run: `python3 -m pytest -q`

Expected: 362 passed (354 + 8 new), 1 skipped.

- [ ] **Step 6: Commit**

```bash
git add foedus/game_server/session.py tests/test_press_session.py
git commit -m "$(cat <<'EOF'
Bundle 6: session — press flow + agent-seat auto-fill

GameSession gains three press-flow methods:
  init_round() — at session creation and after each finalize_round,
    pre-compute agent press + orders, mark agent seats in chat_done
    AND round_done so they never block LLM-driven sync points.
  submit_press_chat(player, draft) — record chat-or-skip, set
    chat_done. Errors on double-signal or eliminated player.
  submit_press_commit(player, press, orders) — submit press, buffer
    orders, signal_done. If is_round_complete, finalize_round + reset
    + init_round for next round (unless terminal).

8 unit tests cover the standard paths plus errors (double-signal,
commit-before-chat-complete, full-round-reset).

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: HTTP endpoints

**Files:**
- Modify: `foedus/game_server/server.py`
- Create: `tests/test_press_server.py`

Add the 5 new endpoints. Long-poll uses an `async` handler with `asyncio.sleep(0.5)` poll loop.

- [ ] **Step 1: Add request/response models + endpoints**

In `foedus/game_server/server.py`, find the existing Pydantic models (search for `class CreateGameResponse` or `class SubmitOrdersRequest`). After the existing models, add:

```python
class PressChatRequest(BaseModel):
    player: int
    draft: dict | None = None  # null/empty = skip


class PressCommitRequest(BaseModel):
    player: int
    press: dict = Field(default_factory=dict)
    orders: dict[str, dict] = Field(default_factory=dict)
```

(`BaseModel` and `Field` should already be imported. If not, add `from pydantic import BaseModel, Field`.)

Now find the function `make_app()` and find an existing `@app.get("/games/{game_id}/view/{player}")` — that's a good anchor. After all the existing endpoints (after `delete_game` near line 217 OR after the history endpoints around 226), add:

```python
    # --- Press v0 flow endpoints (Bundle 6) ----------------------------------

    @app.post("/games/{game_id}/chat")
    def press_chat(game_id: str,
                    req: PressChatRequest) -> dict[str, Any]:
        sess = _session(game_id)
        try:
            return sess.submit_press_chat(req.player, req.draft)
        except ValueError as e:
            msg = str(e)
            if "already chat_done" in msg:
                raise HTTPException(status_code=409, detail=msg)
            raise HTTPException(status_code=400, detail=msg)

    @app.post("/games/{game_id}/commit")
    def press_commit(game_id: str,
                      req: PressCommitRequest) -> dict[str, Any]:
        from foedus.remote.wire import deserialize_orders
        from foedus.core import Hold, Intent, Move, Press, Stance, SupportHold, SupportMove
        sess = _session(game_id)
        # Parse press.
        stance: dict[int, Stance] = {}
        for k, v in (req.press.get("stance") or {}).items():
            try:
                stance[int(k)] = Stance(v)
            except (ValueError, TypeError) as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"bad stance entry {k}={v!r}: {e}",
                )
        intents = []
        for it_raw in (req.press.get("intents") or []):
            try:
                t = it_raw["declared_order"]["type"]
                if t == "Hold":
                    declared = Hold()
                elif t == "Move":
                    declared = Move(dest=int(it_raw["declared_order"]["dest"]))
                elif t == "SupportHold":
                    declared = SupportHold(
                        target=int(it_raw["declared_order"]["target"]),
                    )
                elif t == "SupportMove":
                    declared = SupportMove(
                        target=int(it_raw["declared_order"]["target"]),
                        target_dest=int(
                            it_raw["declared_order"]["target_dest"]
                        ),
                    )
                else:
                    raise ValueError(f"unknown order type: {t}")
                vt_raw = it_raw.get("visible_to")
                vt = (None if vt_raw is None
                      else frozenset(int(x) for x in vt_raw))
                intents.append(Intent(
                    unit_id=int(it_raw["unit_id"]),
                    declared_order=declared,
                    visible_to=vt,
                ))
            except (KeyError, TypeError, ValueError) as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"bad intent {it_raw!r}: {e}",
                )
        press = Press(stance=stance, intents=intents)
        # Parse orders.
        try:
            orders = deserialize_orders(req.orders)
        except (KeyError, ValueError) as e:
            raise HTTPException(
                status_code=400, detail=f"invalid orders: {e}",
            )
        # Submit.
        try:
            return sess.submit_press_commit(req.player, press, orders)
        except ValueError as e:
            msg = str(e)
            if "chat phase not complete" in msg:
                raise HTTPException(status_code=425, detail=msg)
            if "already committed" in msg:
                raise HTTPException(status_code=409, detail=msg)
            raise HTTPException(status_code=400, detail=msg)

    @app.get("/games/{game_id}/chat-prompt/{player}",
             response_class=PlainTextResponse)
    def chat_prompt(game_id: str, player: int) -> str:
        from foedus.game_server.render import render_chat_prompt
        sess = _session(game_id)
        if player not in sess.seats:
            raise HTTPException(status_code=404,
                                detail=f"unknown player {player}")
        if not sess.is_human(player):
            raise HTTPException(status_code=400,
                                detail=f"player {player} is not LLM seat")
        return render_chat_prompt(sess.state, player)

    @app.get("/games/{game_id}/commit-prompt/{player}",
             response_class=PlainTextResponse)
    def commit_prompt(game_id: str, player: int) -> str:
        from foedus.game_server.render import render_commit_prompt
        from foedus.press import is_chat_phase_complete
        sess = _session(game_id)
        if player not in sess.seats:
            raise HTTPException(status_code=404,
                                detail=f"unknown player {player}")
        if not sess.is_human(player):
            raise HTTPException(status_code=400,
                                detail=f"player {player} is not LLM seat")
        if not is_chat_phase_complete(sess.state):
            raise HTTPException(
                status_code=425,
                detail="chat phase not complete; call /wait/{p}/commit",
            )
        return render_commit_prompt(sess.state, player)

    @app.get("/games/{game_id}/wait/{player}/{phase}")
    async def wait_for_phase(game_id: str, player: int,
                              phase: str) -> dict[str, Any]:
        import asyncio
        from foedus.press import is_chat_phase_complete
        if phase not in ("chat", "commit"):
            raise HTTPException(
                status_code=400,
                detail=f"phase must be 'chat' or 'commit'",
            )
        max_wait_seconds = 30.0
        poll_interval = 0.5
        elapsed = 0.0
        while elapsed < max_wait_seconds:
            sess = _session(game_id)
            if sess.state.is_terminal():
                return {
                    "ready": False, "current_phase": None,
                    "turn": sess.state.turn, "is_terminal": True,
                }
            chat_complete = is_chat_phase_complete(sess.state)
            if phase == "chat":
                # Ready iff chat phase still open AND player not done.
                if (not chat_complete
                        and player not in sess.state.chat_done):
                    return {
                        "ready": True, "current_phase": "chat",
                        "turn": sess.state.turn, "is_terminal": False,
                    }
            else:  # commit
                # Ready iff chat complete AND player not yet committed.
                if (chat_complete
                        and player not in sess.state.round_done):
                    return {
                        "ready": True, "current_phase": "commit",
                        "turn": sess.state.turn, "is_terminal": False,
                    }
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
        # Timeout — return current snapshot for client to retry.
        sess = _session(game_id)
        return {
            "ready": False, "current_phase": phase,
            "turn": sess.state.turn,
            "is_terminal": sess.state.is_terminal(),
        }
```

Top-of-file: ensure `from fastapi.responses import PlainTextResponse` is imported. If not, add it next to the existing FastAPI imports.

- [ ] **Step 2: Write integration tests**

Create `tests/test_press_server.py`:

```python
"""Bundle 6 — press server endpoint integration tests."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from foedus.game_server.server import make_app  # noqa: E402


@pytest.fixture
def client() -> TestClient:
    return TestClient(make_app())


def _create_press_game(client: TestClient, num_llm: int = 2,
                       num_agents: int = 2) -> str:
    """Create a game with `num_llm` human (LLM) seats and the rest
    HeuristicAgent. Returns the game_id."""
    n = num_llm + num_agents
    seats = []
    for p in range(num_llm):
        seats.append({"type": "human", "name": f"llm{p}"})
    for p in range(num_agents):
        seats.append({"type": "agent", "name": f"h{p}",
                      "kind": "foedus.agents.heuristic.HeuristicAgent"})
    r = client.post("/games", json={
        "config": {"num_players": n, "max_turns": 7, "seed": 42},
        "seats": seats,
    })
    assert r.status_code == 200, r.text
    return r.json()["game_id"]


def test_chat_endpoint_records_message(client: TestClient) -> None:
    gid = _create_press_game(client)
    r = client.post(f"/games/{gid}/chat", json={
        "player": 0,
        "draft": {"recipients": None, "body": "hello"},
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["chat_phase_complete"] is False  # p1 still pending


def test_chat_endpoint_skip_with_null_draft(client: TestClient) -> None:
    gid = _create_press_game(client)
    r = client.post(f"/games/{gid}/chat",
                    json={"player": 0, "draft": None})
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_chat_endpoint_double_signal_returns_409(client: TestClient) -> None:
    gid = _create_press_game(client)
    client.post(f"/games/{gid}/chat", json={"player": 0, "draft": None})
    r = client.post(f"/games/{gid}/chat",
                    json={"player": 0, "draft": None})
    assert r.status_code == 409


def test_commit_blocked_with_425_until_chat_phase_complete(client: TestClient) -> None:
    gid = _create_press_game(client)
    client.post(f"/games/{gid}/chat", json={"player": 0, "draft": None})
    # P1 hasn't signaled chat-done. Commit must 425.
    r = client.post(f"/games/{gid}/commit", json={
        "player": 0, "press": {}, "orders": {},
    })
    assert r.status_code == 425


def test_commit_advances_round_when_both_llm_committed(client: TestClient) -> None:
    gid = _create_press_game(client)
    for p in (0, 1):
        client.post(f"/games/{gid}/chat",
                    json={"player": p, "draft": None})
    client.post(f"/games/{gid}/commit", json={
        "player": 0, "press": {}, "orders": {},
    })
    r = client.post(f"/games/{gid}/commit", json={
        "player": 1, "press": {}, "orders": {},
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["round_advanced"] is True
    assert body["new_turn"] == 1


def test_chat_prompt_endpoint_returns_text(client: TestClient) -> None:
    gid = _create_press_game(client)
    r = client.get(f"/games/{gid}/chat-prompt/0")
    assert r.status_code == 200
    assert "TURN 1" in r.text
    assert "YOU ARE PLAYER 0" in r.text


def test_commit_prompt_returns_425_before_chat_done(client: TestClient) -> None:
    gid = _create_press_game(client)
    r = client.get(f"/games/{gid}/commit-prompt/0")
    assert r.status_code == 425


def test_commit_prompt_returns_text_when_chat_complete(client: TestClient) -> None:
    gid = _create_press_game(client)
    for p in (0, 1):
        client.post(f"/games/{gid}/chat",
                    json={"player": p, "draft": None})
    r = client.get(f"/games/{gid}/commit-prompt/0")
    assert r.status_code == 200
    assert "PHASE: COMMIT" in r.text


def test_wait_returns_ready_immediately_when_chat_open(client: TestClient) -> None:
    gid = _create_press_game(client)
    r = client.get(f"/games/{gid}/wait/0/chat")
    assert r.status_code == 200
    body = r.json()
    assert body["ready"] is True
    assert body["current_phase"] == "chat"


def test_wait_chat_returns_not_ready_when_player_already_done(client: TestClient) -> None:
    """If P0 already chat_done, /wait/0/chat should not return ready
    immediately — there's no chat phase left for P0 this round."""
    gid = _create_press_game(client)
    client.post(f"/games/{gid}/chat",
                json={"player": 0, "draft": None})
    # Should time out (~30s) since p0 already chatted; we use a short
    # client read. Just check it's NOT ready.
    r = client.get(f"/games/{gid}/wait/0/chat",
                    timeout=1.0 if False else None)
    # Server-side max_wait_seconds is 30 — TestClient awaits the full
    # thing. We just verify ready=false; allow this test to be slow.
    # (See note below: in practice, the test runner will block 30s.)
    assert r.status_code == 200
    body = r.json()
    assert body["ready"] is False


def test_full_press_round_via_http(client: TestClient) -> None:
    """End-to-end: 2 LLM seats + 2 agent seats. Walk through one round
    via HTTP. Both LLMs send empty chat + empty commit. Round advances."""
    gid = _create_press_game(client)
    # Chat phase: skip for both LLMs.
    for p in (0, 1):
        r = client.post(f"/games/{gid}/chat",
                        json={"player": p, "draft": None})
        assert r.status_code == 200
    # Commit phase: empty press + empty orders for both LLMs.
    r0 = client.post(f"/games/{gid}/commit", json={
        "player": 0, "press": {}, "orders": {},
    })
    assert r0.status_code == 200
    r1 = client.post(f"/games/{gid}/commit", json={
        "player": 1, "press": {}, "orders": {},
    })
    assert r1.status_code == 200
    body = r1.json()
    assert body["round_advanced"] is True
    assert body["new_turn"] == 1
    # Verify state via existing /games/{gid}/view/0 endpoint.
    view = client.get(f"/games/{gid}/view/0").json()
    assert view["turn"] == 1
```

Note about `test_wait_chat_returns_not_ready_when_player_already_done`: the long-poll holds for up to 30s. To avoid making the test suite slow, you can either (a) accept the 30s blocking duration, (b) make `max_wait_seconds` configurable via app state and override it in tests, or (c) skip this test via a `@pytest.mark.slow` marker. **For this plan, choose (b)**: add a module-level constant `MAX_WAIT_SECONDS = float(os.environ.get("FOEDUS_PRESS_WAIT_TIMEOUT", "30"))` near the top of `server.py` and use that in the long-poll handler. Then the test sets `os.environ["FOEDUS_PRESS_WAIT_TIMEOUT"] = "1"` before creating the client. Update the test:

```python
def test_wait_chat_returns_not_ready_when_player_already_done(monkeypatch: pytest.MonkeyPatch) -> None:
    import os
    monkeypatch.setenv("FOEDUS_PRESS_WAIT_TIMEOUT", "1")
    from foedus.game_server.server import make_app
    client = TestClient(make_app())
    gid = _create_press_game(client)
    client.post(f"/games/{gid}/chat",
                json={"player": 0, "draft": None})
    r = client.get(f"/games/{gid}/wait/0/chat")
    assert r.status_code == 200
    assert r.json()["ready"] is False
```

(Adjust the `MAX_WAIT_SECONDS` constant in `server.py` accordingly.)

- [ ] **Step 3: Run tests**

Run: `python3 -m pytest tests/test_press_server.py -v`

Expected: 11 passed. The "wait timeout" test may take up to 1s due to the long-poll.

- [ ] **Step 4: Run full suite**

Run: `python3 -m pytest -q`

Expected: 373 passed (362 + 11 new), 1 skipped.

- [ ] **Step 5: Commit**

```bash
git add foedus/game_server/server.py tests/test_press_server.py
git commit -m "$(cat <<'EOF'
Bundle 6: HTTP endpoints — chat, commit, prompts, long-poll wait

Five new endpoints under /games/{gid}/:
  POST /chat              — record chat draft (or null=skip), set chat_done
  POST /commit            — submit press + orders + signal_done; auto
                            advance round if all surviving LLMs done
  GET  /chat-prompt/{p}   — text/plain chat-phase prompt
  GET  /commit-prompt/{p} — text/plain commit-phase prompt; 425 if chat
                            phase still open
  GET  /wait/{p}/{phase}  — long-poll, returns ready when player's
                            requested phase is open. 30s timeout
                            (FOEDUS_PRESS_WAIT_TIMEOUT env var override
                            for tests).

Error codes: 400 invalid input, 404 unknown game/player, 409 already
signaled, 425 chat-phase still open. 500s only for genuine bugs.

11 integration tests via FastAPI TestClient cover all five endpoints
including a full single-round walkthrough.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Subagent client + server wrapper scripts

**Files:**
- Create: `scripts/foedus_press_client.py`
- Create: `scripts/foedus_press_server.py`

The server wrapper is trivial; the client is the meatier piece. Both stdlib-only.

- [ ] **Step 1: Create `scripts/foedus_press_server.py`**

```python
"""Run the foedus press game server on port 8090 (default).

Usage:
    PYTHONPATH=. python3 scripts/foedus_press_server.py
    PYTHONPATH=. python3 scripts/foedus_press_server.py --port 9000
"""

from __future__ import annotations

import argparse
import os
import sys

import uvicorn  # type: ignore[import-not-found]

from foedus.game_server.server import make_app


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8090)
    parser.add_argument("--wait-timeout", type=float, default=30.0,
                        help="Long-poll max-wait seconds")
    args = parser.parse_args()
    os.environ["FOEDUS_PRESS_WAIT_TIMEOUT"] = str(args.wait_timeout)
    print(f"foedus press server starting on http://{args.host}:{args.port}")
    uvicorn.run(make_app(), host=args.host, port=args.port,
                log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Create `scripts/foedus_press_client.py`**

```python
"""Blocking subagent client for foedus press games.

Usage:
    PYTHONPATH=. python3 scripts/foedus_press_client.py \
        --server http://localhost:8090 \
        --game $GID \
        --player 0

The client loops until the game terminates. Per round:
    1. Long-poll /wait/{p}/chat
    2. GET /chat-prompt/{p} → print to stdout, on a "----CHAT----" header
    3. Read a line of JSON from stdin
    4. POST /chat with that JSON
    5. Long-poll /wait/{p}/commit
    6. GET /commit-prompt/{p} → print to stdout, on a "----COMMIT----" header
    7. Read a line of JSON from stdin
    8. POST /commit with that JSON
    9. If terminal, print final summary and exit 0

The subagent dispatching this client is expected to alternate
between reading stdout (prompts) and writing stdin (JSON responses),
one line at a time.

Spec: docs/superpowers/specs/2026-04-29-autonomous-press-harness-design.md
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request


def _http(method: str, url: str,
          body: dict | None = None) -> tuple[int, dict | str]:
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method,
                                  headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            payload = resp.read().decode("utf-8")
            ctype = resp.headers.get("Content-Type", "")
            if "application/json" in ctype:
                return resp.status, json.loads(payload)
            return resp.status, payload
    except urllib.error.HTTPError as e:
        payload = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(payload)
        except json.JSONDecodeError:
            return e.code, payload


def _retry(fn, attempts: int = 3, backoff: float = 1.0):
    for i in range(attempts):
        try:
            return fn()
        except (urllib.error.URLError, ConnectionError) as e:
            if i == attempts - 1:
                raise
            time.sleep(backoff * (2 ** i))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", required=True)
    parser.add_argument("--game", required=True)
    parser.add_argument("--player", type=int, required=True)
    parser.add_argument("--max-rounds", type=int, default=100)
    args = parser.parse_args()
    base = args.server.rstrip("/")
    gid = args.game
    pid = args.player

    rounds = 0
    while rounds < args.max_rounds:
        # 1. Wait for chat phase open.
        while True:
            code, body = _retry(lambda: _http(
                "GET", f"{base}/games/{gid}/wait/{pid}/chat"))
            if code != 200:
                print(f"ERR /wait/{pid}/chat: {code} {body}",
                      file=sys.stderr)
                return 1
            if body.get("is_terminal"):
                print("=== GAME TERMINAL ===", flush=True)
                view = _http(
                    "GET", f"{base}/games/{gid}/view/{pid}")[1]
                print(json.dumps({
                    "scores": view.get("scores"),
                    "winners": view.get("winners"),
                    "turn": view.get("turn"),
                }), flush=True)
                return 0
            if body.get("ready"):
                break
            # not ready and not terminal — retry the long-poll
            continue
        # 2. Get chat prompt and emit.
        code, prompt = _http(
            "GET", f"{base}/games/{gid}/chat-prompt/{pid}")
        if code != 200:
            print(f"ERR /chat-prompt/{pid}: {code} {prompt}",
                  file=sys.stderr)
            return 1
        print("----CHAT----", flush=True)
        print(prompt, flush=True)
        print("----END-PROMPT----", flush=True)
        # 3. Read a single JSON line from stdin (or {} for skip).
        line = sys.stdin.readline()
        if not line:
            print("ERR: stdin closed during chat phase", file=sys.stderr)
            return 1
        try:
            chat_payload = json.loads(line.strip() or "{}")
        except json.JSONDecodeError as e:
            print(f"ERR: invalid chat JSON: {e}", file=sys.stderr)
            return 2
        # 4. POST /chat.
        code, body = _http("POST", f"{base}/games/{gid}/chat", body={
            "player": pid,
            "draft": chat_payload if chat_payload else None,
        })
        if code not in (200, 409):
            print(f"ERR /chat: {code} {body}", file=sys.stderr)
            return 1

        # 5. Wait for commit phase open.
        while True:
            code, body = _retry(lambda: _http(
                "GET", f"{base}/games/{gid}/wait/{pid}/commit"))
            if code != 200:
                print(f"ERR /wait/{pid}/commit: {code} {body}",
                      file=sys.stderr)
                return 1
            if body.get("is_terminal"):
                print("=== GAME TERMINAL ===", flush=True)
                return 0
            if body.get("ready"):
                break
            continue
        # 6. Get commit prompt and emit.
        code, prompt = _http(
            "GET", f"{base}/games/{gid}/commit-prompt/{pid}")
        if code != 200:
            print(f"ERR /commit-prompt/{pid}: {code} {prompt}",
                  file=sys.stderr)
            return 1
        print("----COMMIT----", flush=True)
        print(prompt, flush=True)
        print("----END-PROMPT----", flush=True)
        # 7. Read JSON from stdin.
        line = sys.stdin.readline()
        if not line:
            print("ERR: stdin closed during commit phase",
                  file=sys.stderr)
            return 1
        try:
            commit_payload = json.loads(line.strip())
        except json.JSONDecodeError as e:
            print(f"ERR: invalid commit JSON: {e}", file=sys.stderr)
            return 2
        # 8. POST /commit.
        code, body = _http(
            "POST", f"{base}/games/{gid}/commit", body={
                "player": pid,
                "press": commit_payload.get("press", {}),
                "orders": commit_payload.get("orders", {}),
            })
        if code != 200:
            print(f"ERR /commit: {code} {body}", file=sys.stderr)
            return 1
        # 9. If round advanced and game terminal, exit.
        if body.get("is_terminal"):
            print("=== GAME TERMINAL ===", flush=True)
            return 0
        rounds += 1
    print(f"ERR: max-rounds ({args.max_rounds}) hit; aborting",
          file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Manual smoke — run server, hit endpoints with curl**

Run the server in a background shell:
```bash
PYTHONPATH=/home/david/foedus python3 scripts/foedus_press_server.py --port 8090 &
SERVER_PID=$!
sleep 1
```

Create a game:
```bash
GID=$(curl -s -X POST http://localhost:8090/games -H "Content-Type: application/json" -d '{
  "config": {"num_players": 4, "max_turns": 7, "seed": 42},
  "seats": [
    {"type": "human", "name": "llm0"},
    {"type": "human", "name": "llm1"},
    {"type": "agent", "name": "h2", "kind": "foedus.agents.heuristic.HeuristicAgent"},
    {"type": "agent", "name": "h3", "kind": "foedus.agents.heuristic.HeuristicAgent"}
  ]
}' | python3 -c "import sys, json; print(json.load(sys.stdin)['game_id'])")
echo "GID=$GID"
```

Walk through one round:
```bash
# Chat phase
curl -s -X POST "http://localhost:8090/games/$GID/chat" \
  -H "Content-Type: application/json" \
  -d '{"player": 0, "draft": null}'
# Expected: {"ok":true,"chat_phase_complete":false,"message_dropped":false,"drop_reason":null}

curl -s -X POST "http://localhost:8090/games/$GID/chat" \
  -H "Content-Type: application/json" \
  -d '{"player": 1, "draft": null}'
# Expected: {"ok":true,"chat_phase_complete":true,...}

# Commit phase
curl -s -X POST "http://localhost:8090/games/$GID/commit" \
  -H "Content-Type: application/json" \
  -d '{"player": 0, "press": {}, "orders": {}}'

curl -s -X POST "http://localhost:8090/games/$GID/commit" \
  -H "Content-Type: application/json" \
  -d '{"player": 1, "press": {}, "orders": {}}'
# Expected: {"ok":true,"round_advanced":true,"is_terminal":false,"new_turn":1}

# Verify
curl -s http://localhost:8090/games/$GID/view/0 | python3 -m json.tool | head -10
# Expected: turn: 1

# Cleanup
kill $SERVER_PID
```

If all the curl outputs look right, the server is wired correctly.

- [ ] **Step 4: Run full suite once more**

Run: `python3 -m pytest -q`

Expected: 373 passed, 1 skipped.

- [ ] **Step 5: Commit**

```bash
git add scripts/foedus_press_client.py scripts/foedus_press_server.py
git commit -m "$(cat <<'EOF'
Bundle 6: subagent client + server wrapper scripts

scripts/foedus_press_server.py: thin uvicorn wrapper, defaults to
host=127.0.0.1 port=8090. --wait-timeout flag for long-poll.

scripts/foedus_press_client.py: blocking subagent client. One player,
runs full game. Long-polls phase-wait, prints prompt to stdout, reads
JSON from stdin, POSTs /chat or /commit, loops until terminal. Exits
cleanly with final summary on game-over. stdlib-only (urllib + json).

Manual smoke verified: full round walked through via curl with
2 LLM seats + 2 agent seats; round advances correctly.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Push, open PR, dispatch Sonnet reviewer

- [ ] **Step 1: Run full suite + smoke tests**

```bash
python3 -m pytest -q
```
Expected: 373 passed, 1 skipped.

- [ ] **Step 2: Push branch**

```bash
git push -u origin bundle6-autonomous-press-harness
```

- [ ] **Step 3: Open PR**

```bash
gh pr create --title "Bundle 6: Autonomous press playtest harness" --body "$(cat <<'EOF'
## Summary

Replaces the controller-mediated press playtest workflow with an
autonomous game server + blocking subagent client. Subagents run a
single bash command per LLM seat and play the entire game without the
controller intervening between rounds.

Spec: \`docs/superpowers/specs/2026-04-29-autonomous-press-harness-design.md\`
Plan: \`docs/superpowers/plans/2026-04-29-autonomous-press-harness-bundle-6.md\`

## What changes

| | What |
|---|---|
| **Engine** | Adds \`GameState.chat_done: set[PlayerId]\`. Two new helpers in \`foedus/press.py\`: \`signal_chat_done\`, \`is_chat_phase_complete\`. \`finalize_round\` resets the new field. |
| **Wire** | (De)serializes \`chat_done\`. Backward-compat: missing key → empty set. |
| **Render** | New \`foedus/game_server/render.py\` ports chat/commit prompt rendering from the orchestrator script. |
| **Session** | New \`init_round\`, \`submit_press_chat\`, \`submit_press_commit\` methods. Agent seats are pre-marked \`chat_done\` AND \`round_done\` at round start so they never block LLM-driven sync points. |
| **Server** | Five new endpoints: \`POST /chat\`, \`POST /commit\`, \`GET /chat-prompt/{p}\`, \`GET /commit-prompt/{p}\`, \`GET /wait/{p}/{phase}\` (long-poll). |
| **Scripts** | New \`scripts/foedus_press_server.py\` (uvicorn wrapper) and \`scripts/foedus_press_client.py\` (stdlib-only blocking client). |

## Out of scope
- Bundle 5 (heuristic strategy revision)
- Bundle 4 (alliance multipliers)
- Persistent server state (games are in-memory; matches existing semantics)
- Authentication / multi-tenancy

## Test plan
- [x] \`pytest -q\` → 373 passed, 1 skipped (was 338 + 1 skipped on main; +35 net new tests)
- [x] Manual server smoke via curl: full round walked through with 2 LLM seats + 2 agent seats
- [ ] End-to-end Haiku-vs-heuristic playtest run after merge — subagents run client autonomously, controller only watches

## Implementation notes

Built via subagent-driven-development. 7 task commits on top of spec + plan. Each task had spec compliance + code quality reviews before proceeding.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 4: Dispatch Sonnet code reviewer**

After PR is open, dispatch a `superpowers:code-reviewer` subagent with model `sonnet` to give an independent second opinion. Pass:
- PR URL
- Branch base/head SHAs (\`main\` and the Bundle 6 head SHA)
- Spec + plan paths
- Summary of "what was implemented" and what to watch for, especially:
  - The long-poll handler's correctness under client-disconnect / timeout
  - Race conditions in session state mutation (FastAPI's default is async; if state mutation isn't thread-safe, multiple concurrent POSTs to the same session could interleave)
  - Whether the new server-side parsing of press intents matches existing wire helpers (ideally we should reuse \`wire.deserialize_*\` if possible — flag if the new code duplicates logic)
  - Backward compat: existing \`/orders\` and \`/advance\` endpoints still work for non-press games

- [ ] **Step 5: Address review findings**

For BLOCKING / SHOULD-FIX items, dispatch an implementer subagent to fix them in a follow-up commit. Re-run \`pytest -q\` after fixes. Push the fix commit. NITs can be deferred per author judgment.

---

## Self-Review Checklist

**Spec coverage:**
- [x] `GameState.chat_done` field → Task 1 Step 1
- [x] `signal_chat_done` and `is_chat_phase_complete` → Task 1 Step 2
- [x] `finalize_round` resets `chat_done` → Task 1 Step 3
- [x] Wire (de)serialization → Task 2
- [x] Prompt rendering extracted → Task 3
- [x] Session press flow (init_round, submit_press_chat, submit_press_commit) → Task 4
- [x] Agent seats pre-marked chat_done AND round_done → Task 4 (init_round)
- [x] All 5 HTTP endpoints (chat, commit, two prompts, wait long-poll) → Task 5
- [x] Subagent client + server wrapper → Task 6
- [x] Long-poll timeout configurable for tests → Task 5 Step 2
- [x] HTTP error codes per spec (400/404/409/425) → Task 5 Step 1
- [x] Backward compat: existing endpoints unchanged → preserved (no edits to existing routes)

**Placeholder scan:** No "TBD"/"TODO"/vague items. Test code is complete with assertions. Implementation code is complete and includes exact replacement blocks. The "Note about test_wait_chat_returns_not_ready_..." paragraph is concrete (option (b) chosen with implementation details).

**Type consistency:**
- `GameState.chat_done: set[PlayerId]` consistent across core.py, press.py, wire.py, session.py, server.py.
- `signal_chat_done` / `is_chat_phase_complete` signatures consistent across press.py (Task 1) and session.py (Task 4).
- `submit_press_chat` returns `dict` with keys `ok`, `chat_phase_complete`, `message_dropped`, `drop_reason` — consistent across session.py (Task 4) and server.py (Task 5).
- `submit_press_commit` returns `dict` with keys `ok`, `round_advanced`, `is_terminal`, `new_turn` — consistent across session.py (Task 4) and server.py (Task 5).
- `Press`, `Stance`, `Intent` types match `foedus/core.py` definitions throughout.
