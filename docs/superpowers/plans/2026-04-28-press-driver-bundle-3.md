# Bundle 3 Press-v0 Driver Wiring — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire Press v0 (stance, intents, chat) into an LLM-facing driver so the next Haiku-vs-heuristic playtest empirically answers "does Press v0 actually shift gameplay?"

**Architecture:** New press-aware orchestrator at `scripts/foedus_press_play.py` (promoted from `/tmp/foedus_haiku_play.py`) drives a 2-phase round (chat → commit) per turn via Haiku subagent calls. Heuristics get a non-trivial press behavior (ALLY toward opponent with closest supply count). Engine APIs (`submit_press_tokens`, `record_chat_message`, `signal_done`, `finalize_round`) are unchanged — already shipped in PR #1.

**Tech Stack:** Python 3.10+, pytest, no new dependencies. Existing `foedus.press` / `foedus.core` / `foedus.agents.heuristic` modules.

**Spec:** `docs/superpowers/specs/2026-04-28-press-driver-design.md` (committed at `a9aa38e`).

**Branch:** `bundle3-press-driver` (already created off main; commit a9aa38e holds the design doc).

---

## File Structure

| File | Status | Responsibility |
|---|---|---|
| `foedus/agents/heuristic.py` | Modify (line 50–52) | Replace no-op `choose_press` with closest-supply-count rule; keep `chat_drafts` no-op |
| `tests/test_heuristic_press.py` | Create | 5 unit tests for new heuristic press behavior |
| `tests/smoke/__init__.py` | Create | Package marker (empty) |
| `tests/smoke/test_press_driver_smoke.py` | Create | Full heuristic-only game through press path; asserts non-empty press_history |
| `scripts/__init__.py` | Create | Package marker (empty) — keeps `scripts/` importable for tests |
| `scripts/foedus_press_play.py` | Create | Press-aware orchestrator (init / prompt_chat / apply_chat / prompt_commit / apply_commit / advance / status / log / feedback) |

The orchestrator is a CLI script, not a library — single ~400-line file is fine; splitting it across modules adds friction for a one-off playtest tool.

---

## Task 1: Heuristic press behavior (closest-supply-count rule)

**Files:**
- Modify: `foedus/agents/heuristic.py` (replace `choose_press` at lines 50–52)
- Create: `tests/test_heuristic_press.py`

- [ ] **Step 1: Write all five failing tests**

Create `tests/test_heuristic_press.py`:

```python
"""Heuristic press behavior — Bundle 3.

The heuristic baseline picks ALLY toward the active opponent with the
closest supply count (ties broken by lower pid), NEUTRAL toward all
others, no intents, no chat. See spec
docs/superpowers/specs/2026-04-28-press-driver-design.md.
"""

from __future__ import annotations

from foedus.agents.heuristic import HeuristicAgent
from foedus.core import (
    Archetype,
    GameConfig,
    GameState,
    Map,
    NodeType,
    Stance,
    Unit,
)
from foedus.mapgen import generate_map
from foedus.resolve import initial_state


def _state_with_supply_counts(supply_counts: dict[int, int]) -> GameState:
    """Build a GameState where each player owns exactly `supply_counts[p]`
    supply nodes. Uses a real generated map; ownership is overwritten
    directly to hit the target counts.
    """
    n_players = len(supply_counts)
    cfg = GameConfig(num_players=n_players, max_turns=5, seed=42,
                     archetype=Archetype.UNIFORM)
    m = generate_map(n_players, seed=42, archetype=Archetype.UNIFORM)
    s = initial_state(cfg, m)
    # Reset all ownership to None, then assign the first N supply nodes
    # of each player to that player.
    new_owner = dict.fromkeys(s.ownership.keys(), None)
    supply_nodes = sorted(
        n for n, t in m.node_types.items()
        if t in (NodeType.HOME, NodeType.SUPPLY)
    )
    cursor = 0
    for p, count in supply_counts.items():
        for _ in range(count):
            assert cursor < len(supply_nodes), (
                f"Not enough supplies for required counts: "
                f"need {sum(supply_counts.values())}, "
                f"have {len(supply_nodes)}"
            )
            new_owner[supply_nodes[cursor]] = p
            cursor += 1
    return GameState(
        turn=s.turn, map=s.map, units=s.units, ownership=new_owner,
        scores=s.scores, eliminated=s.eliminated,
        next_unit_id=s.next_unit_id, config=s.config, log=s.log,
    )


def test_choose_press_allies_closest_supply_count() -> None:
    """ALLY toward the opponent whose supply count is nearest mine."""
    # Supplies: p0=3, p1=2, p2=5, p3=8. p0 (me) is closest to p1.
    s = _state_with_supply_counts({0: 3, 1: 2, 2: 5, 3: 8})
    press = HeuristicAgent().choose_press(s, 0)
    assert press.stance == {1: Stance.ALLY}
    assert press.intents == []


def test_choose_press_tiebreaks_by_lower_pid() -> None:
    """Tie on |distance|: lower pid wins."""
    # Supplies: p0=4, p1=2, p2=6, p3=10. From p0's view both p1 and p2
    # are exactly 2 away; tie-break picks p1 (lower pid).
    s = _state_with_supply_counts({0: 4, 1: 2, 2: 6, 3: 10})
    press = HeuristicAgent().choose_press(s, 0)
    assert press.stance == {1: Stance.ALLY}


def test_choose_press_empty_when_no_active_opponents() -> None:
    """If the player has no surviving opponents, return empty press."""
    s = _state_with_supply_counts({0: 4, 1: 2})
    s = GameState(
        turn=s.turn, map=s.map, units=s.units, ownership=s.ownership,
        scores=s.scores, eliminated={1},  # only p0 active
        next_unit_id=s.next_unit_id, config=s.config, log=s.log,
    )
    press = HeuristicAgent().choose_press(s, 0)
    assert press.stance == {}
    assert press.intents == []


def test_choose_press_skips_eliminated_opponents() -> None:
    """Eliminated opponents are not eligible for ALLY targeting even if
    their supply count would be closest."""
    s = _state_with_supply_counts({0: 5, 1: 5, 2: 1, 3: 1})
    s = GameState(
        turn=s.turn, map=s.map, units=s.units, ownership=s.ownership,
        scores=s.scores, eliminated={1},  # p1 closest but eliminated
        next_unit_id=s.next_unit_id, config=s.config, log=s.log,
    )
    press = HeuristicAgent().choose_press(s, 0)
    # p1 eliminated; closest active opponent is now p2 or p3 (tie); pid 2 wins.
    assert press.stance == {2: Stance.ALLY}


def test_chat_drafts_returns_empty_list() -> None:
    """Heuristics never chat."""
    s = _state_with_supply_counts({0: 1, 1: 1})
    drafts = HeuristicAgent().chat_drafts(s, 0)
    assert drafts == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_heuristic_press.py -v`
Expected: 5 failures with `assert {} == {1: Stance.ALLY}` etc — current `choose_press` returns empty stance.

- [ ] **Step 3: Implement closest-supply-count rule**

In `foedus/agents/heuristic.py`, add `Stance` to imports and replace lines 50–52 (the no-op `choose_press`):

```python
# Update imports near top of file (line 19-30):
from foedus.core import (
    ChatDraft,
    GameState,
    Hold,
    Move,
    NodeId,
    Order,
    PlayerId,
    Press,
    Stance,
    Unit,
    UnitId,
)
```

Then replace the existing `choose_press` method:

```python
    def choose_press(self, state: GameState, player: PlayerId) -> Press:
        """ALLY toward the active opponent whose supply count is closest
        to mine; NEUTRAL toward all others (omitted from the dict).
        Ties broken by lower player_id. No intents.

        Spec: docs/superpowers/specs/2026-04-28-press-driver-design.md
        """
        my_supply = state.supply_count(player)
        active_opponents = [
            p for p in range(state.config.num_players)
            if p != player and p not in state.eliminated
        ]
        if not active_opponents:
            return Press(stance={}, intents=[])
        # min() with tuple key gives us closest-distance, then lower-pid.
        closest = min(
            active_opponents,
            key=lambda p: (abs(state.supply_count(p) - my_supply), p),
        )
        return Press(stance={closest: Stance.ALLY}, intents=[])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_heuristic_press.py -v`
Expected: 5 passed.

- [ ] **Step 5: Run full test suite to confirm no regressions**

Run: `python3 -m pytest -q`
Expected: 326 passed, 1 skipped (321 baseline + 5 new). No failures.

- [ ] **Step 6: Commit**

```bash
git add foedus/agents/heuristic.py tests/test_heuristic_press.py
git commit -m "$(cat <<'EOF'
HeuristicAgent: closest-supply-count press behavior

Replaces the no-op choose_press default (silent / empty Press) with a
real heuristic: ALLY toward the active opponent whose supply count is
closest to mine, NEUTRAL toward others. Ties broken by lower player_id.
No intents (heuristics don't pre-commit publicly), no chat.

This unblocks the press-driver playtest in Bundle 3 — without it,
heuristic seats would be silent and the LLMs would have no one to
negotiate with.

Five unit tests in tests/test_heuristic_press.py cover the rule, the
tie-break, the eliminated-opponent filter, the no-active-opponents
edge case, and the chat-drafts no-op.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Smoke test — full heuristic-only game through press path

**Files:**
- Create: `tests/smoke/__init__.py` (empty)
- Create: `tests/smoke/test_press_driver_smoke.py`

This task validates the engine + heuristic combo end-to-end before we layer the LLM driver on top. If something is broken in the press lifecycle, we want to know here, not after writing 400 lines of orchestrator.

- [ ] **Step 1: Create the smoke package marker**

```bash
touch tests/smoke/__init__.py
```

- [ ] **Step 2: Write the smoke test (failing — file doesn't exist yet)**

Create `tests/smoke/test_press_driver_smoke.py`:

```python
"""End-to-end smoke for the Press v0 round-lifecycle path.

Runs a full 4-player heuristic-only game through the same engine API
the orchestrator uses (submit_press_tokens, signal_done, finalize_round)
and asserts the press lifecycle actually exercised — non-empty
press_history with non-empty stance entries.

This catches breakage between the heuristic press behavior (Task 1)
and the engine round-lifecycle (already shipped). The orchestrator
(Tasks 3-6) is then a thin user-facing layer on top.
"""

from __future__ import annotations

from foedus.agents.heuristic import HeuristicAgent
from foedus.core import Archetype, GameConfig, Stance
from foedus.mapgen import generate_map
from foedus.press import (
    finalize_round,
    signal_done,
    submit_press_tokens,
)
from foedus.resolve import initial_state


def test_heuristic_only_game_exercises_press_lifecycle() -> None:
    cfg = GameConfig(
        num_players=4, max_turns=5, seed=42,
        archetype=Archetype.CONTINENTAL_SWEEP,
    )
    m = generate_map(cfg.num_players, seed=cfg.seed,
                     archetype=cfg.archetype, map_radius=cfg.map_radius)
    state = initial_state(cfg, m)

    agent = HeuristicAgent()
    while not state.is_terminal():
        survivors = [
            p for p in range(cfg.num_players) if p not in state.eliminated
        ]
        # Phase 1+2 (no chat for heuristics; press only):
        for p in survivors:
            press = agent.choose_press(state, p)
            state = submit_press_tokens(state, p, press)
            state = signal_done(state, p)
        # Finalize with each player's orders.
        orders = {p: agent.choose_orders(state, p) for p in survivors}
        state = finalize_round(state, orders)

    # press_history should have one entry per turn played.
    assert len(state.press_history) == state.turn, (
        f"expected press_history length == turn ({state.turn}), "
        f"got {len(state.press_history)}"
    )
    # At least one turn must have had a non-empty stance entry from at
    # least one player (heuristic press is non-trivial in a multiplayer
    # game).
    saw_nonempty_stance = any(
        any(p.stance for p in turn_press.values())
        for turn_press in state.press_history
    )
    assert saw_nonempty_stance, (
        "expected at least one non-empty stance across press_history; "
        "got all-empty (heuristic press regressed?)"
    )
    # Spot-check: all non-empty stances should map to ALLY (the heuristic
    # never declares HOSTILE or explicit NEUTRAL).
    for turn_press in state.press_history:
        for p, press in turn_press.items():
            for target, stance in press.stance.items():
                assert stance == Stance.ALLY, (
                    f"unexpected stance {stance} from p{p} toward "
                    f"p{target} — heuristic should only declare ALLY"
                )
```

- [ ] **Step 3: Run the smoke test**

Run: `python3 -m pytest tests/smoke/test_press_driver_smoke.py -v`
Expected: PASS (heuristic press from Task 1 + engine API are wired correctly).

- [ ] **Step 4: Run full test suite**

Run: `python3 -m pytest -q`
Expected: 327 passed, 1 skipped (326 + 1 new smoke).

- [ ] **Step 5: Commit**

```bash
git add tests/smoke/__init__.py tests/smoke/test_press_driver_smoke.py
git commit -m "$(cat <<'EOF'
Smoke test: heuristic-only game through press lifecycle

Runs a full 4-player heuristic-only game using submit_press_tokens
+ signal_done + finalize_round directly (the same engine API the
Bundle 3 orchestrator will use). Asserts press_history is populated
and at least one ALLY stance was declared.

Catches breakage between HeuristicAgent.choose_press and the engine
round-lifecycle — independent of any LLM driver code.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Driver scaffolding — init / status / log / feedback / save / load

**Files:**
- Create: `scripts/__init__.py` (empty)
- Create: `scripts/foedus_press_play.py`

This task ports the unchanged commands from `/tmp/foedus_haiku_play.py` into the repo-tracked location, adapting state-file paths so the new driver doesn't collide with the old one. The chat / commit / advance commands come in Tasks 4, 5, 6.

- [ ] **Step 1: Create the scripts package marker**

```bash
touch scripts/__init__.py
```

- [ ] **Step 2: Write the driver scaffolding**

Create `scripts/foedus_press_play.py` with the imports, state-file constants, save/load helpers, render_map, order_to_str, parse_order, init, status, log, and feedback commands. (Chat / commit / advance come in subsequent tasks; usage string has placeholders for them.)

```python
"""Press-aware orchestrator for a Haiku-vs-HeuristicAgent foedus game.

Drives a two-phase round (chat -> commit) per turn via subagent calls.
State persists in a pickle so this can be invoked iteratively from chat.

Workflow per turn:
  for each LLM seat P in LLM_SEATS:
    prompt_chat P     -> agent prompt for chat phase
    apply_chat P FILE -> driver records the chat draft (or skip)
  for each LLM seat P in LLM_SEATS:
    prompt_commit P     -> agent prompt for commit phase
    apply_commit P FILE -> driver submits press + writes orders
  advance               -> heuristic press + signal_done + finalize_round

Spec: docs/superpowers/specs/2026-04-28-press-driver-design.md
Plan: docs/superpowers/plans/2026-04-28-press-driver-bundle-3.md
"""

from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path

from foedus.agents.heuristic import HeuristicAgent
from foedus.core import (
    Archetype,
    ChatDraft,
    GameConfig,
    Hold,
    Intent,
    Move,
    Order,
    Press,
    Stance,
    SupportHold,
    SupportMove,
    UnitId,
)
from foedus.fog import visible_state_for
from foedus.legal import legal_orders_for_unit
from foedus.mapgen import generate_map
from foedus.press import (
    finalize_round,
    record_chat_message,
    signal_done,
    submit_press_tokens,
)
from foedus.resolve import initial_state

STATE_FILE = Path("/tmp/foedus_press_state.pickle")
CHAT_FILE = lambda p: Path(f"/tmp/foedus_press_chat_p{p}.json")
COMMIT_FILE = lambda p: Path(f"/tmp/foedus_press_commit_p{p}.json")
ORDERS_PICKLE = lambda p: Path(f"/tmp/foedus_press_orders_p{p}.pickle")

LLM_SEATS = {0, 1}        # players 0 and 1 are Haiku
HEURISTIC_SEATS = {2, 3}  # players 2 and 3 are HeuristicAgent


def save(state) -> None:
    with STATE_FILE.open("wb") as f:
        pickle.dump(state, f)


def load():
    with STATE_FILE.open("rb") as f:
        return pickle.load(f)


def cmd_init() -> None:
    cfg = GameConfig(
        num_players=4,
        max_turns=7,
        seed=42,
        archetype=Archetype.CONTINENTAL_SWEEP,
        stagnation_cost=1.0,
    )
    m = generate_map(cfg.num_players, seed=cfg.seed,
                     archetype=cfg.archetype, map_radius=cfg.map_radius)
    state = initial_state(cfg, m)
    save(state)
    # Clean up any per-player files from a previous run.
    for p in range(cfg.num_players):
        for fn in (CHAT_FILE(p), COMMIT_FILE(p), ORDERS_PICKLE(p)):
            if fn.exists():
                fn.unlink()
    print(f"initialized: {len(m.coords)} hexes, "
          f"{cfg.num_players} players (LLM: {sorted(LLM_SEATS)}, "
          f"Heuristic: {sorted(HEURISTIC_SEATS)}), "
          f"max_turns={cfg.max_turns}, "
          f"detente_threshold={cfg.detente_threshold}")


def render_map(state) -> str:
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
            from foedus.core import NodeType
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
            unit = occupant.get(n)
            unit_s = f"u{unit.id}p{unit.owner}" if unit else "    "
            row += f"[{n:>2}{mark}{owner_s}]"
        lines.append(row)
    return "\n".join(lines)


def order_to_str(o: Order) -> str:
    if isinstance(o, Hold):
        return "Hold"
    if isinstance(o, Move):
        return f"Move(dest={o.dest})"
    if isinstance(o, SupportHold):
        return f"SupportHold(target=u{o.target})"
    if isinstance(o, SupportMove):
        return f"SupportMove(target=u{o.target}, target_dest={o.target_dest})"
    return str(o)


def parse_order(d: dict) -> Order:
    t = d["type"]
    if t == "Hold":
        return Hold()
    if t == "Move":
        return Move(dest=int(d["dest"]))
    if t == "SupportHold":
        return SupportHold(target=int(d["target"]))
    if t == "SupportMove":
        return SupportMove(target=int(d["target"]),
                           target_dest=int(d["target_dest"]))
    raise ValueError(f"unknown order type: {t}")


def cmd_status() -> None:
    state = load()
    print(f"turn {state.turn}/{state.config.max_turns}")
    print(f"phase: {state.phase.value}")
    print(f"terminal: {state.is_terminal()}")
    print(f"scores: {state.scores}")
    print(f"eliminated: {sorted(state.eliminated)}")
    print(f"winners: {state.winners()}")
    print(f"mutual_ally_streak: {state.mutual_ally_streak}/"
          f"{state.config.detente_threshold}")
    print(f"round_done: {sorted(state.round_done)}")
    print(f"round_chat msgs: {len(state.round_chat)}")
    print(f"round_press_pending: {sorted(state.round_press_pending)}")


def cmd_log() -> None:
    state = load()
    for line in state.log:
        print(line)


def cmd_feedback(player: int) -> None:
    """Print prompt for end-of-game feedback from one of the LLM players."""
    state = load()
    print(f"=== POST-GAME FEEDBACK PROMPT for PLAYER {player} (Haiku) ===\n")
    print(f"You played as Player {player} in a {state.config.num_players}-player "
          f"foedus game. The game ran for {state.turn} turns.\n")
    print(f"Final scores (all players): {dict(state.final_scores())}")
    print(f"Eliminated: {sorted(state.eliminated)}")
    print(f"Winners: {state.winners()}")
    print(f"Détente reached: {state.detente_reached}")
    print(f"Your final score: {state.scores.get(player, 0)}")
    print()
    print("This game exposed Press v0 features: stance declarations,")
    print("intents, chat. We want your candid feedback on whether press")
    print("actually let you do something interesting, or felt like noise.")
    print()
    print("Full resolution log:")
    for line in state.log:
        print(f"  {line}")
    print()
    print("Questions:")
    print("- Did you use stance / intents / chat in any meaningful way?")
    print("- Did press let you coordinate with other players?")
    print("- Was there any betrayal observation that changed your play?")
    print("- Did the heuristics' ALLY declarations affect your reasoning?")
    print("- Anything you wanted to do but the press surface didn't allow?")
    print("- Compared to a press-less game, did this feel deeper or just noisier?")


# Chat phase commands (Task 4)
def cmd_prompt_chat(player: int) -> None:
    raise NotImplementedError("Task 4 will fill this in.")


def cmd_apply_chat(player: int, path: str) -> None:
    raise NotImplementedError("Task 4 will fill this in.")


# Commit phase commands (Task 5)
def cmd_prompt_commit(player: int) -> None:
    raise NotImplementedError("Task 5 will fill this in.")


def cmd_apply_commit(player: int, path: str) -> None:
    raise NotImplementedError("Task 5 will fill this in.")


# Advance (Task 6)
def cmd_advance() -> None:
    raise NotImplementedError("Task 6 will fill this in.")


COMMANDS = {
    "init": cmd_init,
    "prompt_chat": lambda: cmd_prompt_chat(int(sys.argv[2])),
    "apply_chat": lambda: cmd_apply_chat(int(sys.argv[2]), sys.argv[3]),
    "prompt_commit": lambda: cmd_prompt_commit(int(sys.argv[2])),
    "apply_commit": lambda: cmd_apply_commit(int(sys.argv[2]), sys.argv[3]),
    "advance": cmd_advance,
    "status": cmd_status,
    "feedback": lambda: cmd_feedback(int(sys.argv[2])),
    "log": cmd_log,
}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(f"usage: {sys.argv[0]} {{init|prompt_chat P|apply_chat P FILE|"
              f"prompt_commit P|apply_commit P FILE|advance|status|"
              f"feedback P|log}}")
        sys.exit(1)
    COMMANDS[sys.argv[1]]()
```

- [ ] **Step 3: Manually run init + status + log to verify scaffolding**

Run: `PYTHONPATH=/home/david/foedus python3 scripts/foedus_press_play.py init`
Expected: `initialized: 36 hexes, 4 players ... detente_threshold=8`

Run: `PYTHONPATH=/home/david/foedus python3 scripts/foedus_press_play.py status`
Expected output includes `phase: negotiation`, `mutual_ally_streak: 0/8`, etc.

Run: `PYTHONPATH=/home/david/foedus python3 scripts/foedus_press_play.py log`
Expected: empty (no turns played yet).

Run: `PYTHONPATH=/home/david/foedus python3 scripts/foedus_press_play.py advance`
Expected: `NotImplementedError` traceback (Task 6 will implement).

- [ ] **Step 4: Verify full test suite still green**

Run: `python3 -m pytest -q`
Expected: 327 passed, 1 skipped (no test changes from this task — sanity check that nothing else broke).

- [ ] **Step 5: Commit**

```bash
git add scripts/__init__.py scripts/foedus_press_play.py
git commit -m "$(cat <<'EOF'
Bundle 3: scaffold press-aware orchestrator (init/status/log/feedback)

Promotes the bundle-1 orchestrator out of /tmp into scripts/ and
adapts it for a press-aware round (state file, per-player file paths,
phase/streak/round_done in status output, post-game feedback prompt
focused on press-specific questions).

Chat / commit / advance commands stubbed with NotImplementedError;
filled in by Tasks 4, 5, 6.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Driver chat phase (`prompt_chat` + `apply_chat`)

**Files:**
- Modify: `scripts/foedus_press_play.py` (replace `cmd_prompt_chat` and `cmd_apply_chat`)

- [ ] **Step 1: Implement `cmd_prompt_chat`**

In `scripts/foedus_press_play.py`, replace the stub `cmd_prompt_chat` with:

```python
def cmd_prompt_chat(player: int) -> None:
    """Phase-1 (chat) prompt. Player sees inbound chat earlier in this
    round + last round's press, may submit ONE chat draft (or skip)."""
    state = load()
    view = visible_state_for(state, player)
    print(f"=== TURN {state.turn + 1}/{state.config.max_turns}, "
          f"PHASE: NEGOTIATION (chat round), YOU ARE PLAYER {player} ===\n")

    print(f"Active opponents: {sorted(p for p in range(state.config.num_players) if p != player and p not in state.eliminated)}")
    print(f"Your supply count: {view['supply_count_you']}")
    print(f"Scores: {view['scores']}")
    print(f"Mutual-ally streak: {state.mutual_ally_streak}/"
          f"{state.config.detente_threshold} (détente fires at threshold)")
    print()

    # Public stance matrix from last round.
    if view["public_stance_matrix"]:
        print("PUBLIC STANCE MATRIX (last round):")
        for sender, stances in view["public_stance_matrix"].items():
            entries = ", ".join(
                f"p{tgt}={st}" for tgt, st in sorted(stances.items())
            )
            print(f"  p{sender}: {entries or '(none declared)'}")
        print()

    # Inbound intents from last round.
    if view["your_inbound_intents"]:
        print("INBOUND INTENTS YOU RECEIVED (last round):")
        for sender, intents in view["your_inbound_intents"].items():
            for it in intents:
                print(f"  p{sender} declared u{it.unit_id} -> "
                      f"{order_to_str(it.declared_order)} "
                      f"(visible_to={'public' if it.visible_to is None else sorted(it.visible_to)})")
        print()

    # Betrayals against you.
    if view["your_betrayals"]:
        print(f"BETRAYALS observed (cumulative, {len(view['your_betrayals'])}):")
        for b in view["your_betrayals"][-5:]:
            print(f"  turn {b.turn}: p{b.betrayer} declared "
                  f"u{b.intent.unit_id} -> {order_to_str(b.intent.declared_order)}, "
                  f"actually issued {order_to_str(b.actual_order)}")
        print()

    # Round chat so far (other players' chat earlier in this round).
    if view["round_chat_so_far"]:
        print(f"CHAT THIS ROUND SO FAR ({len(view['round_chat_so_far'])} msgs):")
        for m in view["round_chat_so_far"]:
            recip = ("public" if m.recipients is None
                     else f"to {sorted(m.recipients)}")
            print(f"  [p{m.sender} -> {recip}]: {m.body}")
        print()
    else:
        print("No chat yet this round.\n")

    print("=== INSTRUCTIONS ===")
    print(f"You may send ONE chat message this round (max "
          f"{state.config.chat_char_cap} chars), or skip.")
    print()
    print("RESPOND with a single JSON object — one of:")
    print('  {"recipients": null, "body": "..."}            // public broadcast')
    print('  {"recipients": [0, 2], "body": "..."}          // private to listed pids')
    print('  {}                                              // skip (no chat)')
    print()
    print("Strategic context: this game has Press v0. Stance + intents are")
    print("submitted in the COMMIT phase later. Use chat NOW to coordinate")
    print("alliances, share plans, threaten, deceive. Betrayal observations")
    print("are recorded if you declare an intent and don't follow through.")
```

- [ ] **Step 2: Implement `cmd_apply_chat`**

Replace the stub with:

```python
def cmd_apply_chat(player: int, path: str) -> None:
    """Read chat draft JSON from file. Empty {} -> skip."""
    raw = json.loads(Path(path).read_text())
    if not raw:
        print(f"player {player}: chat skipped (empty draft)")
        return
    if "body" not in raw:
        print(f"WARN: chat draft for p{player} missing 'body'; skipping")
        return
    recipients_raw = raw.get("recipients")
    if recipients_raw is None:
        recipients = None
    else:
        try:
            recipients = frozenset(int(r) for r in recipients_raw)
        except (TypeError, ValueError):
            print(f"WARN: bad recipients for p{player}: {recipients_raw}; skipping")
            return
    draft = ChatDraft(recipients=recipients, body=str(raw["body"]))
    state = load()
    new_state = record_chat_message(state, player, draft)
    if new_state is state or len(new_state.round_chat) == len(state.round_chat):
        # Engine silently dropped (e.g. exceeded char cap, eliminated player).
        # Surface this to the orchestrator so the caller sees something happened.
        print(f"WARN: engine dropped chat from p{player} "
              f"(len={len(draft.body)}, cap={state.config.chat_char_cap}); "
              f"check eliminations, char cap, or phase")
        return
    save(new_state)
    recip_s = ("public" if recipients is None else f"to {sorted(recipients)}")
    print(f"player {player} chat ({recip_s}): {draft.body[:80]}"
          f"{'...' if len(draft.body) > 80 else ''}")
```

- [ ] **Step 3: Manual smoke**

```bash
PYTHONPATH=/home/david/foedus python3 scripts/foedus_press_play.py init
PYTHONPATH=/home/david/foedus python3 scripts/foedus_press_play.py prompt_chat 0
```
Expected: prompt printed with empty press matrix and "No chat yet this round."

```bash
echo '{"recipients": null, "body": "Hello everyone"}' > /tmp/p0_chat.json
PYTHONPATH=/home/david/foedus python3 scripts/foedus_press_play.py apply_chat 0 /tmp/p0_chat.json
PYTHONPATH=/home/david/foedus python3 scripts/foedus_press_play.py prompt_chat 1
```
Expected after apply_chat: `player 0 chat (public): Hello everyone`. After prompt_chat 1: P1's prompt shows the message in CHAT THIS ROUND SO FAR.

```bash
echo '{}' > /tmp/p1_skip.json
PYTHONPATH=/home/david/foedus python3 scripts/foedus_press_play.py apply_chat 1 /tmp/p1_skip.json
```
Expected: `player 1: chat skipped (empty draft)`.

- [ ] **Step 4: Run full test suite to confirm no regressions**

Run: `python3 -m pytest -q`
Expected: 327 passed, 1 skipped.

- [ ] **Step 5: Commit**

```bash
git add scripts/foedus_press_play.py
git commit -m "$(cat <<'EOF'
Bundle 3: chat phase (prompt_chat / apply_chat)

prompt_chat renders inbound chat, last-round press, betrayals, and
chat instructions. apply_chat parses a single ChatDraft (or {} to
skip) and calls record_chat_message. Char-cap and eliminated-player
filters are surfaced as WARN so dropped messages don't fail silently.

Tested manually with init -> prompt_chat 0 -> apply_chat -> prompt_chat 1
to verify cross-player visibility.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Driver commit phase (`prompt_commit` + `apply_commit`)

**Files:**
- Modify: `scripts/foedus_press_play.py` (replace `cmd_prompt_commit` and `cmd_apply_commit`)

- [ ] **Step 1: Implement `cmd_prompt_commit`**

In `scripts/foedus_press_play.py`, replace the stub with:

```python
def cmd_prompt_commit(player: int) -> None:
    """Phase-2 (commit) prompt. Player sees ALL same-turn chat visible
    to them, plus map + legal orders, then submits press + orders."""
    state = load()
    view = visible_state_for(state, player)

    print(f"=== TURN {state.turn + 1}/{state.config.max_turns}, "
          f"PHASE: COMMIT (orders + press), YOU ARE PLAYER {player} ===\n")

    # All chat visible to you this round.
    if view["round_chat_so_far"]:
        print(f"CHAT THIS ROUND ({len(view['round_chat_so_far'])} msgs):")
        for m in view["round_chat_so_far"]:
            recip = ("public" if m.recipients is None
                     else f"to {sorted(m.recipients)}")
            print(f"  [p{m.sender} -> {recip}]: {m.body}")
        print()
    else:
        print("(no chat this round)\n")

    # Map.
    print("MAP (^ = mountain, ~ = water, $ = supply, H = home, "
          "[node-type-owner], u<id>p<player> = unit):")
    print(render_map(state))
    print()
    print(f"Your visible nodes: {view['visible_nodes']}")
    print(f"Your supply count: {view['supply_count_you']}")
    print(f"Scores: {view['scores']}")
    print(f"Mutual-ally streak: {state.mutual_ally_streak}/"
          f"{state.config.detente_threshold}")
    print()

    # Visible units.
    print("VISIBLE UNITS:")
    for u in view["visible_units"]:
        marker = "(YOURS)" if u["owner"] == player else f"(player {u['owner']})"
        print(f"  unit u{u['id']} at node {u['location']} {marker}")
    print()

    # Your units + legal orders.
    print("YOUR UNITS — choose ONE order per unit:")
    for u in state.units.values():
        if u.owner != player:
            continue
        legal = legal_orders_for_unit(state, u.id)
        print(f"  u{u.id} at node {u.location} (adj: "
              f"{sorted(state.map.neighbors(u.location))})")
        for i, o in enumerate(legal):
            print(f"    [{i}] {order_to_str(o)}")
    print()

    print("=== RESPONSE FORMAT ===")
    print("Reply with ONE JSON object combining press tokens and orders:")
    print('{')
    print('  "press": {')
    print('    "stance": {"<other_pid>": "ally|neutral|hostile", ...},')
    print('    "intents": [')
    print('      {"unit_id": <int>,')
    print('       "declared_order": <order>,')
    print('       "visible_to": null | [<pid>, ...]}')
    print('    ]')
    print('  },')
    print('  "orders": {"<unit_id>": <order>, ...}')
    print('}')
    print()
    print("Order objects:")
    print('  {"type": "Hold"}')
    print('  {"type": "Move", "dest": <node_id>}')
    print('  {"type": "SupportHold", "target": <unit_id>}')
    print('  {"type": "SupportMove", "target": <unit_id>, "target_dest": <node_id>}')
    print()
    print("Notes:")
    print("- press.stance / press.intents are optional; default empty.")
    print("- visible_to=null means public broadcast; list = private group.")
    print("- intents about units you don't own are silently dropped.")
    print("- if your declared_order doesn't match your actual order at finalize,")
    print("  recipients see a BetrayalObservation. Plan accordingly.")
    print("- orders is required; default-Hold any owned unit you omit.")
```

- [ ] **Step 2: Implement `cmd_apply_commit`**

Replace the stub with:

```python
def _parse_stance(d: dict) -> dict[int, Stance]:
    out: dict[int, Stance] = {}
    for k, v in d.items():
        try:
            pid = int(k)
            stance = Stance(v if isinstance(v, str) else v.value)
            out[pid] = stance
        except (TypeError, ValueError, AttributeError) as e:
            print(f"WARN: bad stance entry {k}={v!r}: {e}; skipping")
    return out


def _parse_intent(d: dict) -> Intent | None:
    try:
        unit_id = int(d["unit_id"])
        declared = parse_order(d["declared_order"])
        vt_raw = d.get("visible_to")
        if vt_raw is None:
            vt: frozenset[int] | None = None
        else:
            vt = frozenset(int(x) for x in vt_raw)
        return Intent(unit_id=unit_id, declared_order=declared,
                      visible_to=vt)
    except (KeyError, TypeError, ValueError) as e:
        print(f"WARN: bad intent {d!r}: {e}; skipping")
        return None


def cmd_apply_commit(player: int, path: str) -> None:
    """Parse {press, orders} JSON, submit press, store orders for advance."""
    state = load()
    raw = json.loads(Path(path).read_text())

    # Press (optional).
    press_raw = raw.get("press") or {}
    stance = _parse_stance(press_raw.get("stance") or {})
    intents = []
    for it_raw in press_raw.get("intents") or []:
        parsed = _parse_intent(it_raw)
        if parsed is not None:
            intents.append(parsed)
    press = Press(stance=stance, intents=intents)
    state = submit_press_tokens(state, player, press)
    save(state)

    # Orders (required).
    orders_raw = raw.get("orders") or {}
    parsed_orders: dict[UnitId, Order] = {}
    for uid_s, od in orders_raw.items():
        try:
            uid = int(uid_s)
        except ValueError:
            print(f"WARN: non-int unit_id key {uid_s!r}; skipping")
            continue
        unit = state.units.get(uid)
        if unit is None:
            print(f"WARN: unit u{uid} doesn't exist; skipping")
            continue
        if unit.owner != player:
            print(f"WARN: unit u{uid} not owned by p{player}; skipping")
            continue
        try:
            parsed_orders[uid] = parse_order(od)
        except (KeyError, ValueError) as e:
            print(f"WARN: bad order for u{uid}: {e}; defaulting to Hold")
            parsed_orders[uid] = Hold()
    # Default-Hold any owned unit the LLM omitted.
    for u in state.units.values():
        if u.owner == player:
            parsed_orders.setdefault(u.id, Hold())
    with ORDERS_PICKLE(player).open("wb") as f:
        pickle.dump(parsed_orders, f)

    # Summary line.
    stance_s = ", ".join(f"p{p}={s.value}" for p, s in stance.items()) or "(empty)"
    intents_s = f"{len(intents)} intent(s)" if intents else "no intents"
    orders_s = ", ".join(
        f"u{uid}={order_to_str(o)}"
        for uid, o in sorted(parsed_orders.items())
    )
    print(f"player {player} press: stance={{{stance_s}}}, {intents_s}")
    print(f"player {player} orders: {orders_s}")
```

- [ ] **Step 3: Manual smoke**

```bash
PYTHONPATH=/home/david/foedus python3 scripts/foedus_press_play.py init
PYTHONPATH=/home/david/foedus python3 scripts/foedus_press_play.py prompt_commit 0 | head -30
```
Expected: prompt header, no chat (no chat sent), then map, supply count, then visible units and YOUR UNITS sections.

```bash
cat > /tmp/p0_commit.json <<'EOF'
{
  "press": {
    "stance": {"1": "ally"},
    "intents": [
      {"unit_id": 0, "declared_order": {"type": "Hold"}, "visible_to": null}
    ]
  },
  "orders": {
    "0": {"type": "Hold"}
  }
}
EOF
PYTHONPATH=/home/david/foedus python3 scripts/foedus_press_play.py apply_commit 0 /tmp/p0_commit.json
```
Expected: `player 0 press: stance={p1=ally}, 1 intent(s)`, `player 0 orders: u0=Hold, ...` (with default-Hold for any other owned units).

- [ ] **Step 4: Run full test suite**

Run: `python3 -m pytest -q`
Expected: 327 passed, 1 skipped.

- [ ] **Step 5: Commit**

```bash
git add scripts/foedus_press_play.py
git commit -m "$(cat <<'EOF'
Bundle 3: commit phase (prompt_commit / apply_commit)

prompt_commit renders all visible same-turn chat + map + legal orders
+ JSON schema for the combined {press, orders} response. apply_commit
parses press (stance+intents, both optional), submits via
submit_press_tokens, then parses orders (with default-Hold for any
omitted owned unit) and pickles them for advance.

Bad press fields surface as WARN (don't crash); intents about units
the player doesn't own are silently dropped by the engine; intents
with empty visible_to lists are also engine-dropped.

Tested manually with apply_commit consuming a representative
{press, orders} blob.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Driver advance — heuristic press + signal_done + finalize_round

**Files:**
- Modify: `scripts/foedus_press_play.py` (replace `cmd_advance`)

- [ ] **Step 1: Implement `cmd_advance`**

In `scripts/foedus_press_play.py`, replace the stub with:

```python
def cmd_advance() -> None:
    """Run one full round:
       1. Submit heuristic press for HEURISTIC_SEATS.
       2. signal_done for all surviving players.
       3. Load orders from per-player pickles for LLM_SEATS.
       4. HeuristicAgent.choose_orders for HEURISTIC_SEATS.
       5. finalize_round.
    """
    state = load()
    survivors = [
        p for p in range(state.config.num_players)
        if p not in state.eliminated
    ]

    agent = HeuristicAgent()

    # Heuristic seats: submit press now (LLM seats already submitted via
    # apply_commit).
    for p in HEURISTIC_SEATS:
        if p not in survivors:
            continue
        press = agent.choose_press(state, p)
        state = submit_press_tokens(state, p, press)

    # signal_done for everyone surviving.
    for p in survivors:
        state = signal_done(state, p)

    # Build orders dict.
    orders_by_player: dict[int, dict[UnitId, Order]] = {}
    for p in survivors:
        if p in HEURISTIC_SEATS:
            orders_by_player[p] = agent.choose_orders(state, p)
        else:
            f = ORDERS_PICKLE(p)
            if not f.exists():
                print(f"ERROR: no orders submitted for player {p} "
                      f"(run apply_commit first); aborting")
                sys.exit(2)
            with f.open("rb") as fh:
                orders_by_player[p] = pickle.load(fh)
            f.unlink()  # consume

    # Finalize.
    state = finalize_round(state, orders_by_player)
    save(state)

    # Clean up per-player chat / commit files.
    for p in range(state.config.num_players):
        for fn in (CHAT_FILE(p), COMMIT_FILE(p)):
            if fn.exists():
                fn.unlink()

    print(f"advanced to turn {state.turn}/{state.config.max_turns}")
    print(f"scores: {state.scores}")
    print(f"eliminated: {sorted(state.eliminated)}")
    print(f"mutual_ally_streak: {state.mutual_ally_streak}/"
          f"{state.config.detente_threshold}")
    if state.is_terminal():
        print("\n=== GAME OVER ===")
        print(f"Final scores: {dict(state.final_scores())}")
        print(f"Winner(s): {state.winners()}")
        print(f"Détente reached: {state.detente_reached}")
    print("\nRecent log:")
    for line in state.log[-15:]:
        print(f"  {line}")
```

- [ ] **Step 2: End-to-end manual smoke (heuristic-only, no LLM)**

This exercises the full driver path with NO LLM seats — we'll temporarily commit orders for the LLM seats by using empty orders pickles, then advance. Easiest: temporarily flip `LLM_SEATS = set()` and `HEURISTIC_SEATS = {0,1,2,3}` for one run? No — too invasive. Instead, simulate LLM seats by writing JSON commit files and applying:

```bash
PYTHONPATH=/home/david/foedus python3 scripts/foedus_press_play.py init
for P in 0 1; do
  echo '{}' > /tmp/p${P}_chat.json
  PYTHONPATH=/home/david/foedus python3 scripts/foedus_press_play.py apply_chat ${P} /tmp/p${P}_chat.json
  echo '{"press": {}, "orders": {}}' > /tmp/p${P}_commit.json
  PYTHONPATH=/home/david/foedus python3 scripts/foedus_press_play.py apply_commit ${P} /tmp/p${P}_commit.json
done
PYTHONPATH=/home/david/foedus python3 scripts/foedus_press_play.py advance
```
Expected: `advanced to turn 1/7`, scores updated, log shows turn 1 events.

```bash
PYTHONPATH=/home/david/foedus python3 scripts/foedus_press_play.py status
```
Expected: `turn 1/7`, phase=negotiation, mutual_ally_streak likely 0/8 (heuristics ALLY closest-supply opponent — not all-pairs mutual ALLY).

- [ ] **Step 3: Run full test suite**

Run: `python3 -m pytest -q`
Expected: 327 passed, 1 skipped.

- [ ] **Step 4: Run a multi-turn end-to-end smoke**

Repeat the chat-skip / empty-commit / advance loop a few more times to confirm we can drive multiple turns:

```bash
for TURN in 2 3; do
  for P in 0 1; do
    echo '{}' > /tmp/p${P}_chat.json
    PYTHONPATH=/home/david/foedus python3 scripts/foedus_press_play.py apply_chat ${P} /tmp/p${P}_chat.json
    echo '{"press": {}, "orders": {}}' > /tmp/p${P}_commit.json
    PYTHONPATH=/home/david/foedus python3 scripts/foedus_press_play.py apply_commit ${P} /tmp/p${P}_commit.json
  done
  PYTHONPATH=/home/david/foedus python3 scripts/foedus_press_play.py advance
done
```
Expected: turns 2 and 3 advance cleanly; press_history accumulates.

- [ ] **Step 5: Commit**

```bash
git add scripts/foedus_press_play.py
git commit -m "$(cat <<'EOF'
Bundle 3: advance — heuristic press + signal_done + finalize_round

advance composes the round: submits heuristic press tokens for
HEURISTIC_SEATS, signal_done for everyone, gathers orders (LLM seats
from per-player pickle, heuristic seats via HeuristicAgent), and
calls finalize_round. Cleans up per-player chat/commit files after
the round completes. ERROR-aborts if any LLM seat lacks submitted
orders so no half-finalized rounds slip through.

Manually smoked through 3 turns of empty-press/empty-orders LLM seats
to verify the multi-turn loop works.

This completes the press-aware orchestrator. Next: run the actual
Haiku-vs-heuristic playtest with this driver.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Push branch, run final verification, open PR

- [ ] **Step 1: Run full test suite one more time**

Run: `python3 -m pytest -q`
Expected: 327 passed, 1 skipped.

- [ ] **Step 2: Run smoke explicitly**

Run: `python3 -m pytest tests/smoke/ -v`
Expected: 1 passed (`test_heuristic_only_game_exercises_press_lifecycle`).

- [ ] **Step 3: Re-init the orchestrator and run one chat+commit+advance cycle**

```bash
PYTHONPATH=/home/david/foedus python3 scripts/foedus_press_play.py init
PYTHONPATH=/home/david/foedus python3 scripts/foedus_press_play.py prompt_chat 0 | head -10
```
Expected: prompt opens with `=== TURN 1/7, PHASE: NEGOTIATION (chat round), YOU ARE PLAYER 0 ===`.

- [ ] **Step 4: Push and open PR**

```bash
git push -u origin bundle3-press-driver
gh pr create --title "Bundle 3: Press v0 driver wiring (P)" --body "$(cat <<'EOF'
## Summary

Wires Press v0 (stance + intents + chat) into an LLM-facing driver so
the next Haiku-vs-heuristic playtest empirically answers **"does Press
v0 actually shift gameplay?"** Press v0 has been shipped since PR #1
but never exercised in any playtest — every previous run used
\`advance_turn\`, the no-press shim.

This is **Bundle 3 (P only)**. D (fog-respecting legal-orders) and H
(threat-context) are deferred to keep the next playtest signal
attributable to the press knob alone.

## What changes

| | What |
|---|---|
| **Heuristic press** | \`HeuristicAgent.choose_press\` now returns ALLY toward the active opponent with closest supply count (ties broken by lower pid). Heuristics get a real press behavior so LLM seats have someone to negotiate with. \`chat_drafts\` stays empty (heuristics are silent). |
| **Press orchestrator** | New \`scripts/foedus_press_play.py\` — drives a 2-phase round (chat → commit) per turn via subagent prompts. Commands: init / prompt_chat / apply_chat / prompt_commit / apply_commit / advance / status / log / feedback. |
| **Smoke test** | New \`tests/smoke/test_press_driver_smoke.py\` — full 4-player heuristic-only game through the press lifecycle, asserting press_history accumulates and ALLY stances appear. |
| **Heuristic press tests** | New \`tests/test_heuristic_press.py\` — 5 unit tests covering closest-supply rule, tie-break, eliminated-opponent filter, no-active-opponents edge case, chat_drafts no-op. |

## Out of scope

- D — fog-respecting \`legal_orders_for_unit\`
- H — threat-context in per-player view
- Bundle 2 design calls (walk-in capture, strict-majority)
- LLM playtest itself — that's the integration test, run after merge

## Test plan

- [x] \`pytest -q\` → 327 passed, 1 skipped (was 321 + 1 skipped; +6 new tests)
- [x] Smoke: 4-player heuristic-only press game runs to terminal with non-empty press_history
- [x] Manual: \`init → apply_chat → apply_commit → advance\` loops cleanly through multiple turns

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```
Expected: PR URL printed.

- [ ] **Step 5: Spawn Sonnet code reviewer (mirroring Bundle 1 process)**

After PR is open, dispatch a `superpowers:code-reviewer` subagent to give an independent second opinion before requesting any human review. Address any BLOCKING / SHOULD-FIX findings; defer NITs as per author judgment.

---

## Self-Review Checklist (run after writing the plan)

**Spec coverage:**

- [x] HeuristicAgent.choose_press / chat_drafts → Task 1
- [x] Driver script at scripts/foedus_press_play.py → Tasks 3, 4, 5, 6
- [x] All 9 commands (init, prompt_chat, apply_chat, prompt_commit, apply_commit, advance, status, log, feedback) → Tasks 3 (init/status/log/feedback) + 4 (chat) + 5 (commit) + 6 (advance)
- [x] tests/test_heuristic_press.py with 5 unit tests → Task 1
- [x] tests/smoke/test_press_driver_smoke.py → Task 2
- [x] Round flow per spec (chat phase → commit phase → finalize) → Task 6 advance + Tasks 4, 5 phase prompts
- [x] JSON schemas for chat draft (Task 4) and commit blob (Task 5)
- [x] Error handling per spec (malformed JSON, off-fog units, empty visible_to, char cap, etc.) — covered in apply_chat (Task 4) and apply_commit (Task 5) with WARN-and-default-Hold strategy

**Placeholder scan:** No "TBD", no "TODO", no "implement appropriate error handling" without showing the code. The Task 6 manual-smoke step uses a synthetic empty-press/empty-orders bypass which is concrete and reproducible.

**Type consistency:** `Press(stance, intents)`, `ChatDraft(recipients, body)`, `Intent(unit_id, declared_order, visible_to)`, `Stance` enum — all consistent with `foedus/core.py:79-92` and used the same way across Tasks 1, 4, 5, 6. `parse_order` defined once in Task 3, reused in Tasks 4 and 5.
