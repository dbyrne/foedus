# Depth Eval Framework Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a repeatable depth-eval battery that produces a JSON+Markdown artifact for any engine state, plus a compare tool, so mechanic changes can be evaluated by diffing reports.

**Architecture:** A new orchestrator script (`foedus_depth_eval.py`) shells out to the existing `foedus_sim_sweep.py` once per probe (Tier 1 random pool + Tier 2 fixed-seat probes), aggregates per-game JSONL into structured metrics, and writes the artifact. A second script (`compare_depth_runs.py`) diffs two artifacts. The sweep is extended with five engagement counters; no engine changes.

**Tech Stack:** Python 3.11+, stdlib only (`argparse`, `json`, `subprocess`, `concurrent.futures`, `random`), pytest. Output Markdown is plain stdlib string formatting.

**Spec:** `docs/superpowers/specs/2026-04-29-depth-eval-framework-design.md`

**Branch:** `depth-eval-framework` (already created, off `main`).

**Compatibility note:** This plan is written against `main`, not against PR #15 (`bundle-4-trust-and-aid`). The new engagement counters (`aid_spends_count`, `leverage_bonuses_fired`, `alliance_bonuses_fired`, `detente_streak_resets`) will read from engine state via `getattr(..., default=0)` so they degrade gracefully to zero on main and start showing real numbers once Bundle 4 lands. This decouples the framework from PR #15's merge timing.

---

## File Structure

| File | Status | Responsibility |
|---|---|---|
| `scripts/foedus_depth_eval.py` | Create | Orchestrator: parse args, dispatch sweep subprocesses per probe, aggregate, write artifact. |
| `scripts/compare_depth_runs.py` | Create | Diff two depth-eval JSON artifacts → delta table. |
| `foedus/eval/__init__.py` | Create | Package marker. |
| `foedus/eval/probes.py` | Create | `PROBES` registry — declarative list of named scenarios. |
| `foedus/eval/metrics.py` | Create | Pure functions for aggregating JSONL → metrics (rankings, pairwise winrate, engagement, probe diffs). |
| `foedus/eval/bootstrap.py` | Create | Bootstrap CI helpers. |
| `foedus/eval/render.py` | Create | JSON-to-Markdown renderer. |
| `scripts/foedus_sim_sweep.py` | Modify | Add 5 engagement counter fields to per-game JSONL output. |
| `tests/test_sim_sweep_engagement_counters.py` | Create | Verify new counter fields exist and are non-negative ints. |
| `tests/test_eval_probes.py` | Create | Probe registry sanity. |
| `tests/test_eval_metrics.py` | Create | Metric computation against synthetic JSONL. |
| `tests/test_eval_bootstrap.py` | Create | Bootstrap CI correctness. |
| `tests/test_eval_render.py` | Create | Markdown render smoke. |
| `tests/test_depth_eval_e2e.py` | Create | End-to-end smoke: tiny battery, parseable output. |
| `tests/test_compare_depth_runs.py` | Create | Comparison delta table correctness. |
| `docs/research/depth/.gitkeep` | Create | Reserve artifact directory. |

**Why a `foedus/eval/` package and not a one-script orchestrator:** the metrics, probe registry, and renderer are pure functions easy to unit test in isolation; the orchestrator script becomes a thin CLI over the package. This also makes the framework callable from notebooks or future tools without subprocess.

---

## Task 1: Add engagement counters to the sweep JSONL

**Files:**
- Modify: `scripts/foedus_sim_sweep.py` (per-game loop in `run_one_game`)
- Test: `tests/test_sim_sweep_engagement_counters.py` (create)

**What we're doing:** Five new integer fields per game. Each is read from engine state at the end of the game using `getattr` with `default=0` so the sweep keeps working on main (where Bundle 4 fields don't exist) and produces real numbers when the same script runs on a Bundle-4-enabled state.

The five fields:

| Field | Source | Semantics |
|---|---|---|
| `aid_spends_count` | `sum(len(spends) for spends in state.round_aid_pending.values())` accumulated each turn before `finalize_round` | Total AidSpends submitted across all turns by all players. |
| `leverage_bonuses_fired` | Resolution log scan: count entries matching `"leverage bonus"` | How often the leverage combat bonus added strength to a Move. |
| `alliance_bonuses_fired` | Resolution log scan: count entries matching `"alliance bonus"` | How often the alliance bonus added scoring credit. |
| `betrayals_observed` | `sum(len(b) for b in state.betrayals.values())` at end | Total betrayal observations across all players (already partially exposed via `betrayal_count_per_player`; this is the sum). |
| `detente_streak_resets` | Counter incremented in the per-turn loop when `state.mutual_ally_streak` decreases turn-over-turn | How often détente progress was wiped by an observed betrayal. |

- [ ] **Step 1: Write the failing test**

Create `tests/test_sim_sweep_engagement_counters.py`:

```python
"""Verify the sim sweep emits the five engagement counter fields."""
import json
import subprocess
import sys
from pathlib import Path


REQUIRED_FIELDS = (
    "aid_spends_count",
    "leverage_bonuses_fired",
    "alliance_bonuses_fired",
    "betrayals_observed",
    "detente_streak_resets",
)


def test_sweep_emits_engagement_counters(tmp_path):
    """Run a tiny sweep and assert every JSONL line has all 5 counters."""
    out = tmp_path / "sweep.jsonl"
    repo_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [
            sys.executable, "scripts/foedus_sim_sweep.py",
            "--num-games", "3",
            "--max-turns", "5",
            "--workers", "1",
            "--output", str(out),
            "--seed", "12345",
        ],
        cwd=repo_root,
        capture_output=True, text=True, check=True,
    )
    assert out.exists(), result.stderr
    lines = out.read_text().strip().splitlines()
    assert len(lines) == 3
    for line in lines:
        rec = json.loads(line)
        for field in REQUIRED_FIELDS:
            assert field in rec, f"missing {field} in record: {rec.keys()}"
            assert isinstance(rec[field], int), \
                f"{field} should be int, got {type(rec[field])}"
            assert rec[field] >= 0, f"{field} should be non-negative"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_sim_sweep_engagement_counters.py -v
```

Expected: FAIL — at least `aid_spends_count` will be missing on main.

- [ ] **Step 3: Modify `run_one_game` in `scripts/foedus_sim_sweep.py`**

Find `run_one_game`. Add three new accumulator variables alongside `order_counts` and `dislodgement_count`:

```python
    aid_spends_count = 0
    leverage_bonuses_fired = 0
    alliance_bonuses_fired = 0
    detente_streak_resets = 0
    prev_streak = 0  # for detecting streak resets
```

Inside the `while not state.is_terminal():` loop, **after** the press-round block and **before** the orders-collection block, accumulate the aid-spends count. The sweep on main calls `submit_press_tokens` and `signal_chat_done` and `signal_done` — if it later imports `submit_aid_spends` (Bundle 4), the round-aid-pending dict will be populated. Robust read:

```python
        # Engagement counter: aid spends submitted this round.
        round_pending = getattr(state, "round_aid_pending", {})
        for spends in round_pending.values():
            aid_spends_count += len(spends)
```

After `state = finalize_round(state, orders)`, scan the resolution log for the bonus-fire entries and detect streak resets:

```python
        # Engagement counters from resolution log (Bundle 4+).
        log = getattr(state, "resolution_log", None) or []
        # The log is a list[str]; new entries each turn are appended at the
        # end. Count only those for the current turn — they're all in the
        # final tail. Conservative: count any matching line; on main these
        # patterns won't appear so counter stays 0.
        for entry in log:
            if "leverage bonus" in entry:
                leverage_bonuses_fired += 1
            if "alliance bonus" in entry:
                alliance_bonuses_fired += 1
        # Note: scanning the full log every turn double-counts. Track length
        # instead:
```

Wait — that's wrong. We need to count only new entries. Replace with:

```python
        # Engagement counters: scan only NEW resolution-log entries.
        log = getattr(state, "resolution_log", None) or []
        new_log = log[_log_seen_len:] if hasattr(state, "resolution_log") else []
        for entry in new_log:
            if "leverage bonus" in entry:
                leverage_bonuses_fired += 1
            if "alliance bonus" in entry:
                alliance_bonuses_fired += 1
        _log_seen_len = len(log)
        # Détente streak reset detection.
        cur_streak = getattr(state, "mutual_ally_streak", 0)
        if cur_streak < prev_streak:
            detente_streak_resets += 1
        prev_streak = cur_streak
```

Initialize `_log_seen_len = 0` alongside the other accumulators at the top of `run_one_game`.

Update the return dict to include the new fields:

```python
        "aid_spends_count": aid_spends_count,
        "leverage_bonuses_fired": leverage_bonuses_fired,
        "alliance_bonuses_fired": alliance_bonuses_fired,
        "betrayals_observed": sum(
            len(state.betrayals.get(p, []))
            for p in range(num_players)
        ),
        "detente_streak_resets": detente_streak_resets,
```

Place these in the existing return dict right after `betrayal_count_per_player`.

**Verification points** — before running the test, eyeball the changes:
- All five counters declared at top of `run_one_game`.
- `aid_spends_count` accumulated each turn via `getattr(state, "round_aid_pending", {})`.
- Log scan uses `_log_seen_len` so we only count new entries each turn.
- Streak-reset detection compares previous and current `mutual_ally_streak`.
- Return dict has all five fields.

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_sim_sweep_engagement_counters.py -v
```

Expected: PASS.

- [ ] **Step 5: Run the full test suite**

```bash
pytest -q
```

Expected: All previously-passing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add scripts/foedus_sim_sweep.py tests/test_sim_sweep_engagement_counters.py
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
sweep: emit engagement counters in per-game JSONL

Adds five integer fields to each sweep record:
aid_spends_count, leverage_bonuses_fired, alliance_bonuses_fired,
betrayals_observed, detente_streak_resets. All read from engine state
via getattr so they default to 0 on pre-Bundle-4 engine state.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Probe registry

**Files:**
- Create: `foedus/eval/__init__.py`
- Create: `foedus/eval/probes.py`
- Create: `tests/test_eval_probes.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_eval_probes.py`:

```python
"""Tests for the probe registry."""
from foedus.eval.probes import PROBES, Probe


def test_probes_is_list_of_probe_objects():
    assert len(PROBES) >= 8, "expected at least 8 canonical probes"
    for p in PROBES:
        assert isinstance(p, Probe)


def test_probe_names_are_unique():
    names = [p.name for p in PROBES]
    assert len(names) == len(set(names)), f"duplicate probe names: {names}"


def test_each_probe_has_4_seats():
    for p in PROBES:
        assert len(p.seats) == 4, f"probe {p.name} has {len(p.seats)} seats"


def test_canonical_probes_present():
    """The 8 canonical probes from the spec must all be present."""
    expected = {
        "freerider_canary", "coalition_pressure", "detente_lying",
        "mutual_coop", "altruism_punished", "pure_expansion",
        "noise_floor", "aid_asymmetry",
    }
    actual = {p.name for p in PROBES}
    missing = expected - actual
    assert not missing, f"missing canonical probes: {missing}"


def test_probe_has_interpretation():
    """Each probe declares which seats are the 'subject' for score-diff."""
    for p in PROBES:
        assert p.subject_index is not None
        assert 0 <= p.subject_index < 4
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_eval_probes.py -v
```

Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Create the probes module**

Create `foedus/eval/__init__.py` (empty file).

Create `foedus/eval/probes.py`:

```python
"""Canonical probe battery for depth eval.

Each Probe is a fixed-seat scenario. The framework runs each probe with
n=500 games (overrideable) and reports a score_diff plus engagement
counters.

Adding a probe = adding a Probe(...) entry to PROBES.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Probe:
    name: str
    """Stable identifier; used as JSON key."""
    seats: tuple[str, str, str, str]
    """Heuristic class names, one per seat. Must match keys in
    foedus.agents.heuristics.ROSTER."""
    subject_index: int
    """Which seat is the 'subject' for score_diff calculation. The
    diff is mean(scores[subject]) - mean(mean(scores[~subject]))."""
    description: str
    """One-line human description, rendered into the report."""
    config_override: dict[str, Any] = field(default_factory=dict)
    """Optional per-probe config knob overrides."""


PROBES: list[Probe] = [
    Probe(
        name="freerider_canary",
        seats=("DishonestCooperator", "Cooperator", "Cooperator", "Cooperator"),
        subject_index=0,
        description="Canary: does the freerider beat the cooperators?",
    ),
    Probe(
        name="coalition_pressure",
        seats=("GreedyHold", "AntiLeader", "AntiLeader", "AntiLeader"),
        subject_index=0,
        description="Can a coordinated coalition pressure the leader?",
    ),
    Probe(
        name="detente_lying",
        seats=("Sycophant", "Sycophant", "Sycophant", "Sycophant"),
        subject_index=0,
        description="Détente-by-lying: do all-Sycophants close peace despite breaking intents?",
    ),
    Probe(
        name="mutual_coop",
        seats=("Cooperator", "Cooperator", "Cooperator", "Cooperator"),
        subject_index=0,
        description="Do honest cooperators cooperate without an exploiter present?",
    ),
    Probe(
        name="altruism_punished",
        seats=("Cooperator", "GreedyHold", "GreedyHold", "GreedyHold"),
        subject_index=0,
        description="Cost of being the only cooperator.",
    ),
    Probe(
        name="pure_expansion",
        seats=("GreedyHold", "GreedyHold", "GreedyHold", "GreedyHold"),
        subject_index=0,
        description="Score-victory baseline; engagement floor.",
    ),
    Probe(
        name="noise_floor",
        seats=("RandomAgent", "GreedyHold", "GreedyHold", "GreedyHold"),
        subject_index=0,
        description="Sanity floor: GH should beat noise.",
    ),
    Probe(
        name="aid_asymmetry",
        seats=("TrustfulCooperator", "TrustfulCooperator", "Patron", "Patron"),
        subject_index=0,
        description="Bundle 4: pay-fairly vs subsidize-then-defect.",
    ),
]
```

**Note on seat names:** "RandomAgent", "TrustfulCooperator", "Patron" exist on `bundle-4-trust-and-aid` but **not** on `main`. The probe registry references them by name; the orchestrator (Task 3) will skip probes whose seats aren't in `ROSTER` and emit a warning. This way the probe list is forward-compatible and self-documenting.

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_eval_probes.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add foedus/eval/__init__.py foedus/eval/probes.py tests/test_eval_probes.py
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
eval: add canonical probe registry

Eight named fixed-seat scenarios from the depth-eval spec. Each Probe
declares seats, the subject index for score_diff calculation, a
description, and optional config overrides.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Metrics — rankings + engagement aggregation (pure functions)

**Files:**
- Create: `foedus/eval/metrics.py`
- Create: `tests/test_eval_metrics.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_eval_metrics.py`:

```python
"""Tests for metric aggregation from sweep JSONL records."""
import pytest
from foedus.eval.metrics import (
    rankings_from_records,
    engagement_from_records,
    pairwise_winrate_from_records,
    probe_score_diff,
)


def _make_record(agents, scores, **engagement):
    """Synthetic sweep record."""
    base = {
        "agents": list(agents),
        "final_scores": list(scores),
        "dislodgement_count": 0,
        "aid_spends_count": 0,
        "leverage_bonuses_fired": 0,
        "alliance_bonuses_fired": 0,
        "betrayals_observed": 0,
        "detente_streak_resets": 0,
        "order_type_counts": {},
    }
    base.update(engagement)
    return base


def test_rankings_simple_two_games():
    recs = [
        _make_record(["A", "B", "C", "D"], [10, 5, 3, 2]),
        _make_record(["A", "B", "X", "Y"], [4, 8, 1, 1]),
    ]
    r = rankings_from_records(recs)
    by_name = {row["agent"]: row for row in r}
    assert by_name["A"]["mean_score"] == pytest.approx(7.0)
    assert by_name["A"]["n_appearances"] == 2
    assert by_name["B"]["mean_score"] == pytest.approx(6.5)


def test_engagement_means():
    recs = [
        _make_record(["A","B","C","D"], [1,1,1,1],
                     dislodgement_count=2, aid_spends_count=4),
        _make_record(["A","B","C","D"], [1,1,1,1],
                     dislodgement_count=0, aid_spends_count=10),
    ]
    e = engagement_from_records(recs)
    assert e["dislodgements_per_game"] == pytest.approx(1.0)
    assert e["aid_spends_per_game"] == pytest.approx(7.0)


def test_pairwise_winrate_score_rank():
    """A beats B if score[A] > score[B] in same game."""
    recs = [
        _make_record(["A", "B", "C", "D"], [10, 5, 3, 2]),  # A>B>C>D
        _make_record(["A", "B", "C", "D"], [1, 9, 3, 2]),   # B>C>D>A
    ]
    m = pairwise_winrate_from_records(recs)
    # winrate(A,B) = P(A's score > B's | both in game) = 1/2
    assert m["matrix"][m["row_agents"].index("A")][m["col_agents"].index("B")] == pytest.approx(0.5)
    # winrate(B,A) = 1/2
    assert m["matrix"][m["row_agents"].index("B")][m["col_agents"].index("A")] == pytest.approx(0.5)


def test_probe_score_diff_subject_vs_others():
    recs = [
        _make_record(
            ["DishonestCooperator", "Cooperator", "Cooperator", "Cooperator"],
            [20, 10, 8, 12],
        ),
    ]
    diff = probe_score_diff(recs, subject_index=0)
    # subject mean = 20; others mean = (10+8+12)/3 = 10.0; diff = 10.0
    assert diff == pytest.approx(10.0)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_eval_metrics.py -v
```

Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement `foedus/eval/metrics.py`**

```python
"""Pure metric functions over sweep JSONL records.

Each function takes a list of records (dicts as emitted by
foedus_sim_sweep.py) and returns aggregated structures suitable for
inclusion in the depth-eval JSON artifact.
"""
from __future__ import annotations
from collections import defaultdict
from typing import Iterable


Record = dict


def rankings_from_records(records: Iterable[Record]) -> list[dict]:
    """Mean score per agent across all appearances.

    Returns a list sorted descending by mean_score, each entry:
    {"agent": str, "mean_score": float, "n_appearances": int,
     "scores": list[float]}.

    The "scores" list is preserved (per-game scores) so the caller can
    feed it into bootstrap.
    """
    scores_by_agent: dict[str, list[float]] = defaultdict(list)
    for rec in records:
        for name, score in zip(rec["agents"], rec["final_scores"]):
            scores_by_agent[name].append(float(score))
    rows = []
    for name, scores in scores_by_agent.items():
        rows.append({
            "agent": name,
            "mean_score": sum(scores) / len(scores) if scores else 0.0,
            "n_appearances": len(scores),
            "scores": scores,
        })
    rows.sort(key=lambda r: r["mean_score"], reverse=True)
    return rows


def engagement_from_records(records: Iterable[Record]) -> dict[str, float]:
    """Per-game means for the engagement counters.

    Returns a dict of {metric_name: mean_per_game}.
    """
    records = list(records)
    n = len(records) or 1
    totals = {
        "dislodgements_per_game": sum(r.get("dislodgement_count", 0) for r in records),
        "aid_spends_per_game": sum(r.get("aid_spends_count", 0) for r in records),
        "leverage_bonuses_per_game": sum(r.get("leverage_bonuses_fired", 0) for r in records),
        "alliance_bonuses_per_game": sum(r.get("alliance_bonuses_fired", 0) for r in records),
        "betrayals_per_game": sum(r.get("betrayals_observed", 0) for r in records),
        "detente_resets_per_game": sum(r.get("detente_streak_resets", 0) for r in records),
    }
    # Order-type rates: SupportMove% etc.
    order_totals: dict[str, int] = defaultdict(int)
    total_orders = 0
    for r in records:
        for ot, c in r.get("order_type_counts", {}).items():
            order_totals[ot] += c
            total_orders += c
    out = {k: v / n for k, v in totals.items()}
    if total_orders:
        for ot in ("Hold", "Move", "SupportMove", "SupportHold"):
            out[f"{ot.lower()}_pct"] = order_totals.get(ot, 0) / total_orders
    return out


def pairwise_winrate_from_records(records: Iterable[Record]) -> dict:
    """Pairwise winrate matrix using score-rank-within-game.

    winrate(A, B) = P(score[A] > score[B] | both A and B in game).
    Ties contribute 0.5 to both directions.

    Returns {"row_agents": [...], "col_agents": [...], "matrix": [[...]]}
    with None on the diagonal.
    """
    # Aggregate (a, b) -> [wins_for_a, ties, total_games_with_both]
    counts: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0, 0])
    for rec in records:
        agents = rec["agents"]
        scores = rec["final_scores"]
        for i, a in enumerate(agents):
            for j, b in enumerate(agents):
                if i == j:
                    continue
                key = (a, b)
                counts[key][2] += 1
                if scores[i] > scores[j]:
                    counts[key][0] += 1
                elif scores[i] == scores[j]:
                    counts[key][1] += 1
    all_agents = sorted({a for (a, _) in counts.keys()})
    matrix = []
    for a in all_agents:
        row = []
        for b in all_agents:
            if a == b:
                row.append(None)
                continue
            wins, ties, total = counts.get((a, b), (0, 0, 0))
            if total == 0:
                row.append(None)
            else:
                row.append((wins + 0.5 * ties) / total)
        matrix.append(row)
    return {"row_agents": all_agents, "col_agents": all_agents, "matrix": matrix}


def probe_score_diff(records: Iterable[Record], subject_index: int) -> float:
    """For a fixed-seat probe: mean(subject_score) - mean(other_seats_score).

    The subject is the seat at `subject_index`; "other seats" are the
    other three. Per-game we compute (subject - mean(others)), then
    average across games.
    """
    diffs = []
    for rec in records:
        scores = rec["final_scores"]
        subject = scores[subject_index]
        others = [s for i, s in enumerate(scores) if i != subject_index]
        diffs.append(subject - (sum(others) / len(others)))
    return sum(diffs) / len(diffs) if diffs else 0.0


def probe_per_game_diffs(records: Iterable[Record], subject_index: int) -> list[float]:
    """Same as probe_score_diff but returns the per-game list (for bootstrap)."""
    diffs = []
    for rec in records:
        scores = rec["final_scores"]
        subject = scores[subject_index]
        others = [s for i, s in enumerate(scores) if i != subject_index]
        diffs.append(subject - (sum(others) / len(others)))
    return diffs
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_eval_metrics.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add foedus/eval/metrics.py tests/test_eval_metrics.py
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
eval: pure metric functions for sweep JSONL aggregation

rankings_from_records, engagement_from_records, pairwise_winrate_from_records,
probe_score_diff, probe_per_game_diffs. All pure, all tested with synthetic
records.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Bootstrap CIs

**Files:**
- Create: `foedus/eval/bootstrap.py`
- Create: `tests/test_eval_bootstrap.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_eval_bootstrap.py`:

```python
"""Tests for bootstrap CI helpers."""
import random
import pytest
from foedus.eval.bootstrap import bootstrap_ci_mean


def test_bootstrap_ci_contains_true_mean():
    rng = random.Random(42)
    data = [rng.gauss(10.0, 1.0) for _ in range(500)]
    lo, hi = bootstrap_ci_mean(data, n_resamples=200, seed=0)
    sample_mean = sum(data) / len(data)
    assert lo < sample_mean < hi
    # 95% CI on n=500 with sigma=1 is roughly mean +/- 0.09
    assert hi - lo < 0.5


def test_bootstrap_empty_data_returns_zero_zero():
    assert bootstrap_ci_mean([], n_resamples=50, seed=0) == (0.0, 0.0)


def test_bootstrap_constant_data_returns_constant_ci():
    lo, hi = bootstrap_ci_mean([5.0] * 100, n_resamples=50, seed=0)
    assert lo == pytest.approx(5.0)
    assert hi == pytest.approx(5.0)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_eval_bootstrap.py -v
```

Expected: FAIL — module missing.

- [ ] **Step 3: Implement `foedus/eval/bootstrap.py`**

```python
"""Bootstrap CI helpers for depth eval.

Uses standard nonparametric bootstrap with percentile method.
stdlib only — no scipy/numpy.
"""
from __future__ import annotations
import random


def bootstrap_ci_mean(
    data: list[float],
    n_resamples: int = 1000,
    confidence: float = 0.95,
    seed: int | None = None,
) -> tuple[float, float]:
    """Percentile-bootstrap CI for the mean of `data`.

    Returns (lo, hi) at the given confidence level. Returns (0.0, 0.0)
    on empty input.
    """
    if not data:
        return (0.0, 0.0)
    rng = random.Random(seed)
    n = len(data)
    means = []
    for _ in range(n_resamples):
        sample = [data[rng.randrange(n)] for _ in range(n)]
        means.append(sum(sample) / n)
    means.sort()
    alpha = (1.0 - confidence) / 2.0
    lo_idx = int(alpha * n_resamples)
    hi_idx = int((1.0 - alpha) * n_resamples) - 1
    return (means[lo_idx], means[hi_idx])
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_eval_bootstrap.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add foedus/eval/bootstrap.py tests/test_eval_bootstrap.py
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
eval: percentile bootstrap CI for the mean (stdlib only)

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Markdown renderer

**Files:**
- Create: `foedus/eval/render.py`
- Create: `tests/test_eval_render.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_eval_render.py`:

```python
"""Smoke test for the JSON-to-Markdown depth report renderer."""
from foedus.eval.render import render_markdown


def _fake_artifact():
    return {
        "run_id": "test-run",
        "git_sha": "deadbeef",
        "git_branch": "main",
        "timestamp": "2026-04-29T12:00:00Z",
        "config": {"max_turns": 15, "players": 4},
        "stat_rigor": "point",
        "tier1_random_pool": {
            "n_games": 100,
            "seed": 42,
            "rankings": [
                {"agent": "GreedyHold", "mean_score": 60.0,
                 "ci95": None, "n_appearances": 50},
                {"agent": "Cooperator", "mean_score": 55.0,
                 "ci95": None, "n_appearances": 47},
            ],
            "pairwise_winrate": {
                "row_agents": ["GreedyHold", "Cooperator"],
                "col_agents": ["GreedyHold", "Cooperator"],
                "matrix": [[None, 0.55], [0.45, None]],
            },
            "engagement": {
                "dislodgements_per_game": 0.2,
                "aid_spends_per_game": 0.0,
            },
        },
        "tier2_probes": [
            {
                "name": "freerider_canary",
                "seats": ["DC", "C", "C", "C"],
                "n": 50,
                "score_diff": 5.5,
                "ci95": None,
                "engagement": {"dislodgements_per_game": 0.1},
            }
        ],
        "tier3_knob_sweep": None,
    }


def test_render_includes_run_id_and_sections():
    md = render_markdown(_fake_artifact())
    assert "test-run" in md
    assert "deadbeef" in md
    assert "## Tier 1" in md
    assert "GreedyHold" in md
    assert "60.0" in md
    assert "## Tier 2" in md
    assert "freerider_canary" in md


def test_render_handles_missing_ci():
    md = render_markdown(_fake_artifact())
    # Should not crash on None ci95
    assert "GreedyHold" in md
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_eval_render.py -v
```

Expected: FAIL — module missing.

- [ ] **Step 3: Implement `foedus/eval/render.py`**

```python
"""Render a depth-eval JSON artifact as a Markdown report."""
from __future__ import annotations
from typing import Any


def render_markdown(artifact: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append(f"# Depth Eval Report — {artifact['run_id']}")
    lines.append("")
    lines.append(f"- **Git:** `{artifact.get('git_branch','?')}` @ "
                 f"`{artifact.get('git_sha','?')}`")
    lines.append(f"- **Timestamp:** {artifact.get('timestamp','?')}")
    lines.append(f"- **Stat rigor:** {artifact.get('stat_rigor','point')}")
    lines.append("")
    lines.append("## Config")
    lines.append("")
    for k, v in (artifact.get("config") or {}).items():
        lines.append(f"- `{k}` = {v}")
    lines.append("")

    t1 = artifact.get("tier1_random_pool") or {}
    if t1:
        lines.append("## Tier 1 — Random pool")
        lines.append("")
        lines.append(f"n_games = {t1.get('n_games', '?')}, "
                     f"seed = {t1.get('seed', '?')}")
        lines.append("")
        lines.append("### Rankings")
        lines.append("")
        lines.append("| # | Agent | Mean | CI95 | N |")
        lines.append("|---|---|---|---|---|")
        for i, row in enumerate(t1.get("rankings", []), 1):
            ci = row.get("ci95")
            ci_s = f"[{ci[0]:.2f}, {ci[1]:.2f}]" if ci else "—"
            lines.append(f"| {i} | {row['agent']} | "
                         f"{row['mean_score']:.2f} | {ci_s} | "
                         f"{row['n_appearances']} |")
        lines.append("")
        lines.append("### Engagement")
        lines.append("")
        lines.append("| Metric | Per-game mean |")
        lines.append("|---|---|")
        for k, v in (t1.get("engagement") or {}).items():
            if isinstance(v, float):
                lines.append(f"| `{k}` | {v:.4f} |")
            else:
                lines.append(f"| `{k}` | {v} |")
        lines.append("")
        lines.append("### Pairwise winrate (row beats column)")
        lines.append("")
        pw = t1.get("pairwise_winrate") or {}
        if pw:
            cols = pw.get("col_agents", [])
            lines.append("| | " + " | ".join(cols) + " |")
            lines.append("|" + "---|" * (len(cols) + 1))
            for ra, mrow in zip(pw.get("row_agents", []),
                                pw.get("matrix", [])):
                cells = []
                for v in mrow:
                    cells.append("—" if v is None else f"{v:.2f}")
                lines.append(f"| **{ra}** | " + " | ".join(cells) + " |")
        lines.append("")

    probes = artifact.get("tier2_probes") or []
    if probes:
        lines.append("## Tier 2 — Fixed-seat probes")
        lines.append("")
        lines.append("| Probe | Seats | n | Score diff | CI95 |")
        lines.append("|---|---|---|---|---|")
        for p in probes:
            ci = p.get("ci95")
            ci_s = f"[{ci[0]:.2f}, {ci[1]:.2f}]" if ci else "—"
            seats_s = ", ".join(p.get("seats", []))
            lines.append(f"| `{p['name']}` | {seats_s} | "
                         f"{p.get('n','?')} | {p['score_diff']:+.2f} | "
                         f"{ci_s} |")
        lines.append("")

    sweep = artifact.get("tier3_knob_sweep")
    if sweep:
        lines.append("## Tier 3 — Knob sweep")
        lines.append("")
        lines.append(f"Knob: `{sweep.get('knob','?')}`")
        lines.append("")

    return "\n".join(lines) + "\n"
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_eval_render.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add foedus/eval/render.py tests/test_eval_render.py
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
eval: JSON-to-Markdown report renderer

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Orchestrator script `foedus_depth_eval.py`

**Files:**
- Create: `scripts/foedus_depth_eval.py`
- Create: `docs/research/depth/.gitkeep`
- Create: `tests/test_depth_eval_e2e.py`

This is the largest task. It assembles Tasks 1–5 into a working CLI.

**Args (argparse):**
- `--output` (path, required) — JSON output path. Markdown sibling auto-derived.
- `--n-tier1` (int, default 2000)
- `--n-tier2` (int, default 500)
- `--probes` (csv, default "all") — comma-separated probe names or "all".
- `--bootstrap` (flag, default false)
- `--bootstrap-n` (int, default 1000)
- `--seed` (int, default 42)
- `--reseed` (flag, default false) — use random seed instead of pinned 42.
- `--map-radius` (int, default 3)
- `--max-turns` (int, default 15)
- `--players` (int, default 4)
- `--workers` (int, default 0 → cpu_count)

**Behaviour:**
1. Validate probes: filter out probes whose seats aren't in `ROSTER`; warn to stderr.
2. Run Tier 1 sweep via subprocess to `foedus_sim_sweep.py`, capture JSONL.
3. Run each Tier 2 probe via subprocess in parallel (each probe uses sweep's `--seats`).
4. Compute metrics from each probe's JSONL.
5. Optionally bootstrap CIs.
6. Build artifact dict, write JSON + Markdown.

- [ ] **Step 1: Write the end-to-end smoke test (failing)**

Create `tests/test_depth_eval_e2e.py`:

```python
"""End-to-end smoke test for foedus_depth_eval.py.

Runs a tiny battery (n=5 per probe, 1 probe) and asserts the produced
JSON parses, has the right shape, and the sibling markdown is written.
"""
import json
import subprocess
import sys
from pathlib import Path


def test_depth_eval_runs_end_to_end(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    out_json = tmp_path / "depth.json"
    result = subprocess.run(
        [
            sys.executable, "scripts/foedus_depth_eval.py",
            "--output", str(out_json),
            "--n-tier1", "5",
            "--n-tier2", "5",
            "--probes", "pure_expansion",
            "--max-turns", "5",
            "--workers", "1",
            "--seed", "12345",
        ],
        cwd=repo_root,
        capture_output=True, text=True,
    )
    assert result.returncode == 0, \
        f"depth-eval failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    assert out_json.exists()
    data = json.loads(out_json.read_text())
    # Structural checks.
    assert "run_id" in data
    assert "git_sha" in data
    assert "tier1_random_pool" in data
    assert data["tier1_random_pool"]["n_games"] == 5
    assert "rankings" in data["tier1_random_pool"]
    assert "engagement" in data["tier1_random_pool"]
    assert "pairwise_winrate" in data["tier1_random_pool"]
    assert "tier2_probes" in data
    assert len(data["tier2_probes"]) == 1
    assert data["tier2_probes"][0]["name"] == "pure_expansion"
    # Markdown sibling exists.
    md = out_json.with_suffix(".md")
    assert md.exists()
    md_text = md.read_text()
    assert "Depth Eval Report" in md_text
    assert "pure_expansion" in md_text
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_depth_eval_e2e.py -v
```

Expected: FAIL — script doesn't exist.

- [ ] **Step 3: Create `docs/research/depth/.gitkeep`**

```bash
touch docs/research/depth/.gitkeep
```

- [ ] **Step 4: Implement `scripts/foedus_depth_eval.py`**

```python
"""Foedus depth eval — repeatable battery over the agent roster.

Spec: docs/superpowers/specs/2026-04-29-depth-eval-framework-design.md

Usage:
    PYTHONPATH=. python3 scripts/foedus_depth_eval.py \
        --output docs/research/depth/2026-04-29-bundle4.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

# Ensure repo root on sys.path so 'foedus.*' imports work when run as a
# script.
_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parents[1]))

from foedus.agents.heuristics import ROSTER
from foedus.eval.bootstrap import bootstrap_ci_mean
from foedus.eval.metrics import (
    rankings_from_records, engagement_from_records,
    pairwise_winrate_from_records, probe_score_diff, probe_per_game_diffs,
)
from foedus.eval.probes import PROBES, Probe
from foedus.eval.render import render_markdown


def _git_info(repo_root: Path) -> tuple[str, str]:
    try:
        sha = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo_root, text=True,
        ).strip()
    except Exception:
        sha = "unknown"
    try:
        branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=repo_root, text=True,
        ).strip()
    except Exception:
        branch = "unknown"
    return sha, branch


def _run_sweep(
    repo_root: Path,
    out_jsonl: Path,
    *,
    num_games: int,
    seed: int,
    seats: tuple[str, ...] | None,
    max_turns: int,
    map_radius: int,
    players: int,
    workers: int,
) -> list[dict]:
    """Invoke foedus_sim_sweep.py as a subprocess; return parsed records."""
    cmd = [
        sys.executable, "scripts/foedus_sim_sweep.py",
        "--num-games", str(num_games),
        "--max-turns", str(max_turns),
        "--seed", str(seed),
        "--workers", str(workers),
        "--output", str(out_jsonl),
    ]
    if hasattr(map_radius, "__int__") and map_radius is not None:
        cmd += ["--map-radius", str(map_radius)]
    if seats:
        cmd += ["--seats", ",".join(seats)]
    proc = subprocess.run(
        cmd, cwd=repo_root, capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"sweep failed: cmd={cmd}\nSTDOUT:{proc.stdout}\nSTDERR:{proc.stderr}"
        )
    records = []
    for line in out_jsonl.read_text().splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def _filter_valid_probes(probes: list[Probe]) -> list[Probe]:
    valid = []
    for p in probes:
        missing = [s for s in p.seats if s not in ROSTER]
        if missing:
            print(f"[depth-eval] skipping probe {p.name}: "
                  f"unknown seats {missing}", file=sys.stderr)
            continue
        valid.append(p)
    return valid


def _select_probes(names_csv: str) -> list[Probe]:
    if names_csv == "all":
        return list(PROBES)
    wanted = {n.strip() for n in names_csv.split(",") if n.strip()}
    by_name = {p.name: p for p in PROBES}
    out = []
    for n in wanted:
        if n not in by_name:
            print(f"[depth-eval] unknown probe: {n}", file=sys.stderr)
            continue
        out.append(by_name[n])
    return out


def _run_one_probe(probe_args):
    """Worker entrypoint — runs one probe sweep and returns records."""
    (repo_root, probe, n, seed, max_turns, map_radius, players, workers) = probe_args
    with tempfile.NamedTemporaryFile(
        suffix=".jsonl", delete=False, dir=repo_root
    ) as tmp:
        tmp_path = Path(tmp.name)
    try:
        records = _run_sweep(
            repo_root, tmp_path,
            num_games=n, seed=seed, seats=probe.seats,
            max_turns=max_turns, map_radius=map_radius,
            players=players, workers=workers,
        )
        return probe.name, records
    finally:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--n-tier1", type=int, default=2000)
    parser.add_argument("--n-tier2", type=int, default=500)
    parser.add_argument("--probes", default="all")
    parser.add_argument("--bootstrap", action="store_true")
    parser.add_argument("--bootstrap-n", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--reseed", action="store_true")
    parser.add_argument("--map-radius", type=int, default=3)
    parser.add_argument("--max-turns", type=int, default=15)
    parser.add_argument("--players", type=int, default=4)
    parser.add_argument("--workers", type=int, default=0)
    args = parser.parse_args()

    repo_root = _HERE.parents[1]
    seed = (int.from_bytes(os.urandom(4), "big") if args.reseed
            else args.seed)
    sha, branch = _git_info(repo_root)

    # ---- Tier 1: random pool sweep ----
    print(f"[depth-eval] Tier 1: {args.n_tier1} random-pool games "
          f"(seed={seed})", file=sys.stderr)
    with tempfile.NamedTemporaryFile(
        suffix=".jsonl", delete=False, dir=repo_root
    ) as tmp:
        t1_path = Path(tmp.name)
    try:
        t1_records = _run_sweep(
            repo_root, t1_path,
            num_games=args.n_tier1, seed=seed, seats=None,
            max_turns=args.max_turns, map_radius=args.map_radius,
            players=args.players, workers=args.workers,
        )
    finally:
        try:
            t1_path.unlink()
        except FileNotFoundError:
            pass

    rankings = rankings_from_records(t1_records)
    engagement = engagement_from_records(t1_records)
    pairwise = pairwise_winrate_from_records(t1_records)

    # Strip the "scores" list before serialization but use it for bootstrap.
    if args.bootstrap:
        for row in rankings:
            row["ci95"] = list(bootstrap_ci_mean(
                row["scores"], n_resamples=args.bootstrap_n,
                seed=seed,
            ))
    else:
        for row in rankings:
            row["ci95"] = None
    for row in rankings:
        del row["scores"]

    # ---- Tier 2: fixed-seat probes ----
    probes = _filter_valid_probes(_select_probes(args.probes))
    print(f"[depth-eval] Tier 2: {len(probes)} probes × "
          f"{args.n_tier2} games", file=sys.stderr)

    probe_args_list = [
        (repo_root, p, args.n_tier2, seed,
         args.max_turns, args.map_radius, args.players, 1)
        for p in probes
    ]
    probe_results: dict[str, list[dict]] = {}
    if probe_args_list:
        # Parallelize across probes; each probe's sweep uses 1 worker
        # internally so we don't oversubscribe.
        max_parallel = (args.workers or os.cpu_count() or 1)
        max_parallel = min(max_parallel, len(probe_args_list))
        with ProcessPoolExecutor(max_workers=max_parallel) as ex:
            futures = {ex.submit(_run_one_probe, pa): pa[1].name
                       for pa in probe_args_list}
            for f in as_completed(futures):
                name, records = f.result()
                probe_results[name] = records

    tier2_out = []
    for p in probes:
        recs = probe_results.get(p.name, [])
        diff = probe_score_diff(recs, p.subject_index)
        ci = None
        if args.bootstrap and recs:
            ci = list(bootstrap_ci_mean(
                probe_per_game_diffs(recs, p.subject_index),
                n_resamples=args.bootstrap_n,
                seed=seed,
            ))
        tier2_out.append({
            "name": p.name,
            "description": p.description,
            "seats": list(p.seats),
            "subject_index": p.subject_index,
            "n": len(recs),
            "score_diff": diff,
            "ci95": ci,
            "engagement": engagement_from_records(recs),
        })

    # ---- Artifact ----
    artifact = {
        "run_id": args.output.stem,
        "git_sha": sha,
        "git_branch": branch,
        "timestamp": dt.datetime.now(dt.timezone.utc)
                       .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "config": {
            "players": args.players,
            "map_radius": args.map_radius,
            "max_turns": args.max_turns,
        },
        "stat_rigor": "bootstrap" if args.bootstrap else "point",
        "n_bootstrap_resamples": args.bootstrap_n if args.bootstrap else None,
        "tier1_random_pool": {
            "n_games": len(t1_records),
            "seed": seed,
            "rankings": rankings,
            "pairwise_winrate": pairwise,
            "engagement": engagement,
        },
        "tier2_probes": tier2_out,
        "tier3_knob_sweep": None,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(artifact, indent=2) + "\n")
    md_path = args.output.with_suffix(".md")
    md_path.write_text(render_markdown(artifact))

    print(f"[depth-eval] wrote {args.output}", file=sys.stderr)
    print(f"[depth-eval] wrote {md_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

**Note about `--seats` and `--map-radius`:** the spec assumes the sweep already supports both. Confirm before running — if either is missing, abort and report so we add them as a prerequisite step.

- [ ] **Step 5: Verify sweep CLI compatibility**

```bash
python3 scripts/foedus_sim_sweep.py --help 2>&1 | grep -E "seats|map-radius|output|seed"
```

Expected: all four flags present. If `--seats` or `--map-radius` is missing, stop and add them before continuing (these were added in PRs #11 and #12 — should already be on `main`).

- [ ] **Step 6: Run the e2e test**

```bash
pytest tests/test_depth_eval_e2e.py -v
```

Expected: PASS.

- [ ] **Step 7: Run the full suite to make sure nothing else broke**

```bash
pytest -q
```

Expected: all green.

- [ ] **Step 8: Commit**

```bash
git add scripts/foedus_depth_eval.py docs/research/depth/.gitkeep tests/test_depth_eval_e2e.py
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
eval: depth-eval orchestrator (foedus_depth_eval.py)

Runs Tier 1 random pool + Tier 2 fixed-seat probes (parallel),
aggregates via foedus.eval.metrics, optionally bootstraps CIs, writes
JSON + Markdown artifact to docs/research/depth/.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Compare-runs script

**Files:**
- Create: `scripts/compare_depth_runs.py`
- Create: `tests/test_compare_depth_runs.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_compare_depth_runs.py`:

```python
"""Tests for compare_depth_runs.py."""
import json
import subprocess
import sys
from pathlib import Path


def _write_artifact(path, dislodgements, freerider_diff):
    artifact = {
        "run_id": path.stem,
        "git_sha": "abc",
        "tier1_random_pool": {
            "engagement": {
                "dislodgements_per_game": dislodgements,
                "aid_spends_per_game": 0.0,
            },
            "rankings": [],
            "pairwise_winrate": {"row_agents": [], "col_agents": [], "matrix": []},
        },
        "tier2_probes": [
            {"name": "freerider_canary", "score_diff": freerider_diff,
             "ci95": None, "engagement": {}, "seats": [], "n": 0,
             "subject_index": 0, "description": ""},
        ],
    }
    path.write_text(json.dumps(artifact))


def test_compare_emits_delta_for_changed_metric(tmp_path):
    a = tmp_path / "before.json"
    b = tmp_path / "after.json"
    _write_artifact(a, dislodgements=0.17, freerider_diff=10.7)
    _write_artifact(b, dislodgements=1.88, freerider_diff=5.33)
    repo_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "scripts/compare_depth_runs.py",
         str(a), str(b)],
        cwd=repo_root,
        capture_output=True, text=True, check=True,
    )
    assert "dislodgements_per_game" in result.stdout
    assert "freerider_canary" in result.stdout
    assert "+1.71" in result.stdout or "1.71" in result.stdout


def test_compare_unchanged_metrics_omitted_by_default(tmp_path):
    a = tmp_path / "before.json"
    b = tmp_path / "after.json"
    _write_artifact(a, dislodgements=0.17, freerider_diff=10.7)
    _write_artifact(b, dislodgements=0.17, freerider_diff=10.7)
    repo_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "scripts/compare_depth_runs.py",
         str(a), str(b)],
        cwd=repo_root,
        capture_output=True, text=True, check=True,
    )
    # No metric crossed the epsilon threshold; output should be empty
    # or note "no significant changes".
    assert ("no significant" in result.stdout.lower()
            or result.stdout.strip() == "")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_compare_depth_runs.py -v
```

Expected: FAIL — script missing.

- [ ] **Step 3: Implement `scripts/compare_depth_runs.py`**

```python
"""Diff two depth-eval JSON artifacts.

Usage:
    python3 scripts/compare_depth_runs.py before.json after.json
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path


def _engagement_rows(art: dict) -> dict[str, float]:
    eng = (art.get("tier1_random_pool") or {}).get("engagement", {})
    return {f"tier1.engagement.{k}": float(v) for k, v in eng.items()}


def _probe_rows(art: dict) -> dict[str, float]:
    out = {}
    for p in art.get("tier2_probes", []):
        out[f"probe.{p['name']}.score_diff"] = float(p["score_diff"])
        for k, v in (p.get("engagement") or {}).items():
            out[f"probe.{p['name']}.engagement.{k}"] = float(v)
    return out


def _collect_metrics(art: dict) -> dict[str, float]:
    metrics = {}
    metrics.update(_engagement_rows(art))
    metrics.update(_probe_rows(art))
    return metrics


def _is_significant(key: str, before: float, after: float,
                    eps_rate: float, eps_score: float) -> bool:
    delta = abs(after - before)
    if "score_diff" in key or "score" in key:
        return delta >= eps_score
    return delta >= eps_rate


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    parser.add_argument("--full", action="store_true",
                        help="Print all metrics, not just changed ones.")
    parser.add_argument("--eps-rate", type=float, default=0.05)
    parser.add_argument("--eps-score", type=float, default=0.5)
    args = parser.parse_args()

    a = json.loads(args.before.read_text())
    b = json.loads(args.after.read_text())
    ma = _collect_metrics(a)
    mb = _collect_metrics(b)
    keys = sorted(set(ma.keys()) | set(mb.keys()))
    rows = []
    for k in keys:
        va = ma.get(k)
        vb = mb.get(k)
        if va is None or vb is None:
            rows.append((k, va, vb, None))
            continue
        if args.full or _is_significant(
            k, va, vb, args.eps_rate, args.eps_score
        ):
            rows.append((k, va, vb, vb - va))
    if not rows:
        print("no significant changes (use --full to see all metrics)")
        return 0
    width = max(len(r[0]) for r in rows)
    print(f"{'metric'.ljust(width)}    before     after        Δ")
    for k, va, vb, d in rows:
        va_s = "—" if va is None else f"{va:>+8.3f}"
        vb_s = "—" if vb is None else f"{vb:>+8.3f}"
        d_s = "—" if d is None else f"{d:>+8.3f}"
        print(f"{k.ljust(width)} {va_s} {vb_s} {d_s}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_compare_depth_runs.py -v
```

Expected: PASS.

- [ ] **Step 5: Run the full suite**

```bash
pytest -q
```

Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add scripts/compare_depth_runs.py tests/test_compare_depth_runs.py
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
eval: compare_depth_runs.py — diff two depth-eval artifacts

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Reproduce Bundle 4's reported numbers (acceptance gate)

**Files:** none new; this task is a verification run.

The spec's acceptance criterion §12 says: "The Bundle 4 PR's hand-counted numbers reproduce within bootstrap CI when the framework is run against `bundle-4-trust-and-aid`."

- [ ] **Step 1: Merge depth-eval into a worktree of `bundle-4-trust-and-aid`**

```bash
git worktree add /tmp/foedus-depth-on-b4 bundle-4-trust-and-aid
cd /tmp/foedus-depth-on-b4
git merge --no-ff --no-edit depth-eval-framework
pytest -q
```

Expected: all green (no merge conflicts; engagement counters now show real values when sweeping the Bundle-4 engine).

- [ ] **Step 2: Run a small canonical battery**

```bash
PYTHONPATH=. python3 scripts/foedus_depth_eval.py \
    --output /tmp/depth-bundle4-smoke.json \
    --n-tier1 200 --n-tier2 100 \
    --bootstrap --bootstrap-n 200
```

Expected: completes in <2 minutes; `/tmp/depth-bundle4-smoke.json` and `.md` exist.

- [ ] **Step 3: Spot-check the report**

Open `/tmp/depth-bundle4-smoke.md`. Verify:
- Tier-1 rankings have TrustfulCooperator near the top.
- `aid_spends_per_game > 0`.
- `freerider_canary` score_diff is **positive but smaller than ~+10** (Bundle 4 partially closes it; PR claims ~+5.33).
- `detente_lying` score_diff is near zero (matching PR's "100%→0% détente rate" claim — all four Sycophants score similarly when nobody collectively wins by lying).

If any of these are wildly off, halt and investigate before declaring the framework correct.

- [ ] **Step 4: Clean up worktree**

```bash
cd /home/david/foedus
git worktree remove /tmp/foedus-depth-on-b4
```

- [ ] **Step 5: No commit**

This task is verification only.

---

## Task 9: README for the framework

**Files:**
- Create: `docs/research/depth/README.md`

- [ ] **Step 1: Write the README**

Create `docs/research/depth/README.md`:

```markdown
# Depth Eval Reports

Generated by `scripts/foedus_depth_eval.py`. Each pair of `<run-id>.json`
+ `<run-id>.md` is a single canonical battery run. The JSON is the
source of truth; the Markdown is a rendering for humans.

## Generate a snapshot

```sh
PYTHONPATH=. python3 scripts/foedus_depth_eval.py \
    --output docs/research/depth/$(date -I)-<bundle-name>.json
```

Add `--bootstrap` for confidence intervals (slower; use when committing
a result).

## Compare two snapshots

```sh
python3 scripts/compare_depth_runs.py before.json after.json
```

Prints a delta table on metrics that crossed the epsilon thresholds.
Add `--full` to see all metrics.

## Spec

`docs/superpowers/specs/2026-04-29-depth-eval-framework-design.md`
```

- [ ] **Step 2: Commit**

```bash
git add docs/research/depth/README.md
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
docs: README for depth-eval reports directory

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Done

At this point:
- The depth-eval framework is implemented and tested on `main`.
- The compare tool works.
- Engagement counters degrade gracefully on pre-Bundle-4 engine state.
- Acceptance run against `bundle-4-trust-and-aid` confirms reproducibility (Task 8).

**Next steps after merge** (out of scope for this plan):
- Run the canonical bootstrap battery against `main` post-Bundle-4 merge; commit the artifact as the new "shipping" baseline.
- When Bundle 5 lands, repeat and `compare_depth_runs.py` to publish the bundle's measured impact.
