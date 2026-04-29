# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

`README.md` covers the install + a high-level architecture file map; this file covers what's not visible from a single read.

## Commands

```sh
pip install -e .[dev]          # full dev set (pytest + rating + remote extras)
pip install -e .[rating]       # OpenSkill rating system only
pip install -e .[remote]       # FastAPI/uvicorn/httpx for the wire protocol

pytest                         # ~190 tests, well under a second
pytest tests/test_resolve.py::test_head_to_head_bounce   # single test
pytest -k press                # filter by name
pytest tests/smoke/            # slow integration smoke tests
```

CLI entry point is `foedus = foedus.cli:main`. Subcommand groups:

- `foedus play` — interactive REPL stepping through a fresh game
- `foedus agent serve|build|run|stop` — wrap an `Agent` class as an HTTP server or Docker image
- `foedus play-server start` — game-server HTTP API for UI clients (Godot, web)

`scripts/foedus_press_play.py` is an out-of-process orchestrator that drives a press-aware game by writing prompts to disk for an external LLM (Claude / Haiku) — the engine itself never calls an LLM.

## Architecture invariants

These are load-bearing design choices; preserve them when changing engine code.

**The engine is pure state-transition functions.** `foedus/press.py`, `foedus/resolve.py`, and friends never hold a timer, async loop, or I/O. Every round-lifecycle step (`submit_press_tokens`, `record_chat_message`, `signal_done`, `finalize_round`) takes a `GameState` and returns a new one. Drivers (CLI REPL, game server, training harness, the press_play orchestrator) call them as events arrive. **Don't introduce async, threads, or implicit timers into the engine.**

**Each turn is two phases.** `Phase.NEGOTIATION` (press tokens + chat drafts + per-player `signal_done`) → `Phase.ORDERS` (collect orders, run `finalize_round`). `play_game` (`foedus/loop.py`) is the canonical loop showing the order: press → chat → done → orders → finalize. Agents that don't care about press use the default `choose_press` / `chat_drafts` no-ops on the `Agent` protocol.

**Fog is a convention, not enforced.** Agents receive the full `GameState` and are trusted to call `foedus.fog.visible_state_for(state, player)` if they want to play fairly. The `Agent` protocol docstring spells this out — keep it that way (engine-side enforcement would forbid mixed-trust agents in the same process).

**Order normalization is silent.** `legal.py` enumerates geometrically-valid orders; resolution drops illegal submissions without raising. This matters for fuzzers and untrusted remote agents — don't add exceptions for "bad" orders.

**Game-end conditions are three-way.** Score-victory at `max_turns`, last-player-standing, and **détente** (5 consecutive turns with zero dislodgements → all survivors share the win). Détente is the alliance-track victory condition that gives the project its name (*foedus* = "treaty"); scoring math in `scoring.py` reflects this — don't collapse it into a single sum-of-squares model.

## Wire-protocol gotchas (`foedus/remote/`)

- `GameState` contains `frozenset` edges and int-keyed dicts. `wire.py` transcribes — int keys → strings, frozensets → sorted lists, `NodeType` → `.value`. New fields on `GameState` / `Map` / `Order` need matching serialize/deserialize entries here.
- The resolution log is intentionally **not** transmitted. It grows linearly in turn count and isn't strategic information. Don't add it to the wire format "for debugging."
- `Dockerfile.agent` is bundled as package data (`pyproject.toml` → `[tool.setuptools.package-data]`). If you change its location, update both.

## Docker glue (`foedus/agent_build.py`)

Shells out to the `docker` CLI rather than using a Python SDK — same rationale as castra (fewer deps, easy podman swap). **foedus deliberately does not depend on castra.** Agent creators wanting richer image management (multi-region ECR push, EC2 launch) can use castra alongside, but the dependency direction stays one-way.

The `_run` helper forces `utf-8` + `errors='replace'` on subprocess output — Windows hosts default to cp1252 and docker's progress bytes will crash naive decoding. (See castra commit `21664c7` for the same fix in that codebase.)

## Docs layout

- `docs/design/<date>-<feature>.md` — specs for shipped features
- `docs/plans/<date>-<feature>.md` — planning docs paired with the design doc
- `docs/superpowers/specs/` and `docs/superpowers/plans/` — newer location for in-flight work
- `docs/design/mechanics.md` — living roadmap document (current state + future directions); reference, not strict spec

When adding a new feature, follow the date-prefixed pattern so chronological ordering matches commit history.

## Roadmap context

v1 is shipped (engine + fog + procedural maps + heuristic agent + tests). The frontier is **v2 = small NN trained via no-press self-play**, then **v3 = MCP wrapper + local LLM negotiator for press play**. The two-tier Cicero-style split (strategic NN never sees chat; LLM bias-injects soft constraints) is the long-term target — keep press infrastructure cleanly separable from order-resolution so the NN can be trained without it.
