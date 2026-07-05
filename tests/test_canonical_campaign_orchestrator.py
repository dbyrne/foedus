"""Integration test for the canonical-campaign orchestrator's non-LLM plumbing.

Exercises `--dry-run` (no games, no LLM calls): the sealed seed manifest and the
per-game rotation plan. The game loop itself is driven by the existing
single-game harness and is validated by the live preflight run, not here.
"""

from __future__ import annotations

import json
import os
import sys

import pytest

_SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

pytest.importorskip("foedus.rating", reason="orchestrator import path is fine "
                    "without openskill, but keep parity with the run env")

import foedus_canonical_campaign as orch  # noqa: E402
from foedus.eval import campaign  # noqa: E402
import random  # noqa: E402


def test_dry_run_emits_sealed_manifest_and_plan(tmp_path):
    out = tmp_path / "run"
    rc = orch.main([
        "--match-id", "unit-test-match",
        "--num-games", "8",
        "--seed-rng", "999",
        "--out-dir", str(out),
        "--dry-run",
    ])
    assert rc == 0

    sealed = json.loads((out / "seed_manifest.sealed.json").read_text())
    assert sealed["match_id"] == "unit-test-match"
    assert sealed["num_games"] == 8
    assert len(sealed["commit"]) == 64
    # sealed = commit only (seeds/nonce withheld until reveal)
    assert sealed["seeds"] is None and sealed["nonce"] is None

    # commitment is reproducible from the same CSPRNG seed (bind-the-operator)
    expect_sealed, _, _ = campaign.seal("unit-test-match", 8, rng=random.Random(999))
    assert sealed["commit"] == expect_sealed.commit

    plan = json.loads((out / "campaign_plan.json").read_text())
    assert plan["board"] == {
        "num_players": 4, "max_turns": 12, "map_radius": 2,
        "archetype": "continental_sweep", "detente_threshold": 8,
    }
    assert plan["rotation"] is True
    # freerider (entrant 3, neutral handle "Golf") sits in seat (3 + k) % 4
    assert plan["freerider_handles"] == ["Golf"]
    assert plan["handle_roles"]["Golf"] == "freerider"
    for g in plan["seatings"]:
        k = g["game_index"]
        assert g["freerider_seats"] == [(3 + k) % 4]
        assert g["identity_by_seat"][(3 + k) % 4] == "Golf"


def _neg() -> str:
    return json.dumps({"press": {"stance": {}, "intents": []},
                       "pacts": {"propose": [], "accept": []}})


def _orders() -> str:
    return json.dumps({"orders": {}})


def _stub_factory(num_games: int, max_turns: int):
    """Each persistent LLM entrant plays every game; script per game
    `max_turns` (negotiate, orders) pairs + one self-note. campaign/recip flags
    come from the env the orchestrator sets before calling the factory."""
    from foedus.agents.llm.client import StubLLMClient
    from foedus.agents.llm.diplomat import LLMDiplomat

    def factory():
        responses: list[str] = []
        for _ in range(num_games):
            responses += [_neg(), _orders()] * max_turns
            responses += ["A neutral private note about the opponents."]
        return LLMDiplomat(client=StubLLMClient(responses))

    return factory


def test_end_to_end_stub_campaign_full_pipeline(tmp_path):
    """Full orchestrator run on a stub client: rotation + identity context +
    per-entrant standings + commit-reveal + archival + the scorecard on top."""
    out = tmp_path / "run"
    rc = orch.main(
        ["--match-id", "e2e", "--num-games", "2", "--max-turns", "2",
         "--seed-rng", "3", "--out-dir", str(out)],
        agent_factory=_stub_factory(num_games=2, max_turns=2),
    )
    assert rc == 0

    # commit-reveal round-trips
    revealed = campaign.SeedManifest.from_dict(
        json.loads((out / "seed_manifest.revealed.json").read_text()))
    assert campaign.verify(revealed)
    assert revealed.commit == json.loads(
        (out / "seed_manifest.sealed.json").read_text())["commit"]

    # 2 sweep records, entrant-identity labelled, freerider (Golf) rotates
    sweeps = [json.loads(l) for l in (out / "sweep.jsonl").read_text().splitlines()]
    assert len(sweeps) == 2
    for g, s in enumerate(sweeps):
        assert set(s["agents"]) == {"Delta", "Echo", "Foxtrot", "Golf"}
        assert s["agents"][(3 + g) % 4] == "Golf"      # rotation
        assert s["identity_by_seat"] == s["agents"]

    # per-entrant OpenSkill standings (4 distinct identities, not collapsed)
    standings = json.loads((out / "standings.json").read_text())["standings"]
    assert {r["identity"] for r in standings} == {"Delta", "Echo", "Foxtrot", "Golf"}

    # game 1's prompt carries the seat legend + PRIOR GAMES by handle
    seat = sweeps[1]["llm_seats"][0]
    recs = [json.loads(x) for x in
            (out / f"decisions_game1_seat{seat}.jsonl").read_text().splitlines()]
    neg = next(r for r in recs if r["phase"] == "negotiate")
    user = neg["prompt"]["user"]
    assert "PLAYER HANDLES THIS GAME" in user       # the legend
    assert "PRIOR GAMES" in user                     # cross-game memory rendered
    assert "= Golf" in user or "= Delta" in user     # legend maps a handle

    # campaign memory persisted per game/seat, tagged with the entrant handle
    mem_files = list(out.glob("campaign_memory_game*_seat*.json"))
    assert mem_files
    any_mem = json.loads(mem_files[0].read_text())
    assert any_mem["entrant_identity"] in {"Delta", "Echo", "Foxtrot"}

    # the scorecard runs end-to-end and finds the freerider by its plan handle
    import foedus_canonical_scorecard as sc
    rep = sc.build_report(str(out))
    assert rep["aggregate"]["n_games"] == 2
    assert len(rep["trajectory"]) == 2
    # 'Golf' was the freerider in the plan -> the scorecard scored it as such
    assert all(t["freerider_seat"] is not None for t in rep["trajectory"])


def test_resume_continues_from_crash(tmp_path):
    """A crashed match resumes from the sealed secret + persisted memory:
    continues on the SAME seeds, reloads cross-game memory, and completes the
    commit-reveal (the nonce survived on disk)."""
    from foedus.agents.llm.client import StubLLMClient
    from foedus.agents.llm.diplomat import LLMDiplomat

    out = tmp_path / "run"
    argv = ["--match-id", "resume-test", "--num-games", "2", "--max-turns", "2",
            "--seed-rng", "5", "--out-dir", str(out)]
    orch.main(argv, agent_factory=_stub_factory(num_games=2, max_turns=2))
    full = [json.loads(l) for l in (out / "sweep.jsonl").read_text().splitlines() if l.strip()]
    assert len(full) == 2
    assert (out / "seed_manifest.secret.json").exists()  # secret persisted pre-games

    # simulate a crash AFTER game 0: keep game-0 artifacts + the secret, drop
    # everything game 1 / final produced.
    (out / "sweep.jsonl").write_text(json.dumps(full[0]) + "\n")
    tel = [l for l in (out / "telemetry.jsonl").read_text().splitlines() if l.strip()]
    (out / "telemetry.jsonl").write_text(tel[0] + "\n")
    for pat in ("decisions_game1_*", "campaign_memory_game1_*", "transcript_game1.md",
                "seed_manifest.revealed.json", "standings.json", "run_summary.json"):
        for p in out.glob(pat):
            p.unlink()

    def resume_factory():  # fresh agents; game 0 is reloaded from disk
        r = [_neg(), _orders()] * 2 + ["a resumed private note."]
        return LLMDiplomat(client=StubLLMClient(r))

    rc = orch.main(argv + ["--resume"], agent_factory=resume_factory)
    assert rc == 0

    sweeps = [json.loads(l) for l in (out / "sweep.jsonl").read_text().splitlines() if l.strip()]
    assert len(sweeps) == 2                                   # game 1 appended
    assert sweeps[1]["seed"] == full[1]["seed"]               # SAME seed (from secret)

    # commit-reveal completed — the nonce survived the crash on disk
    revealed = campaign.SeedManifest.from_dict(
        json.loads((out / "seed_manifest.revealed.json").read_text()))
    assert campaign.verify(revealed)

    # standings cover both games (rating replayed game 0 + ran game 1)
    standings = json.loads((out / "standings.json").read_text())["standings"]
    assert {r["identity"] for r in standings} == {"Delta", "Echo", "Foxtrot", "Golf"}

    # game 1 saw game 0's reloaded memory
    seat = sweeps[1]["llm_seats"][0]
    recs = [json.loads(x) for x in
            (out / f"decisions_game1_seat{seat}.jsonl").read_text().splitlines()]
    neg = next(r for r in recs if r["phase"] == "negotiate")
    assert "PRIOR GAMES" in neg["prompt"]["user"]


def test_dry_run_no_rotation_pins_freerider(tmp_path):
    out = tmp_path / "run"
    rc = orch.main([
        "--match-id", "unit-test-norot",
        "--num-games", "4",
        "--seed-rng", "7",
        "--out-dir", str(out),
        "--no-rotation",
        "--dry-run",
    ])
    assert rc == 0
    plan = json.loads((out / "campaign_plan.json").read_text())
    assert plan["rotation"] is False
    for g in plan["seatings"]:
        assert g["freerider_seats"] == [3]  # pinned every game
