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


def test_dry_run_records_parallel_seats_config_from_env(tmp_path, monkeypatch):
    """A sealed match must durably record its concurrency setting so a later
    audit never has to ask "was this a WORKERS=2 or WORKERS=3 run?" (the
    ambiguity flagged after run #1's mid-match instrument question)."""
    monkeypatch.setenv("FOEDUS_PARALLEL_SEATS", "1")
    monkeypatch.setenv("FOEDUS_PARALLEL_SEATS_WORKERS", "3")
    out = tmp_path / "run"
    rc = orch.main([
        "--match-id", "unit-test-parallel",
        "--num-games", "8",
        "--seed-rng", "999",
        "--out-dir", str(out),
        "--dry-run",
    ])
    assert rc == 0
    plan = json.loads((out / "campaign_plan.json").read_text())
    assert plan["parallel_seats"] == {"enabled": True, "workers": 3}


def test_dry_run_parallel_seats_config_defaults_off(tmp_path, monkeypatch):
    monkeypatch.delenv("FOEDUS_PARALLEL_SEATS", raising=False)
    monkeypatch.delenv("FOEDUS_PARALLEL_SEATS_WORKERS", raising=False)
    out = tmp_path / "run"
    rc = orch.main([
        "--match-id", "unit-test-noparallel",
        "--num-games", "8",
        "--seed-rng", "999",
        "--out-dir", str(out),
        "--dry-run",
    ])
    assert rc == 0
    plan = json.loads((out / "campaign_plan.json").read_text())
    assert plan["parallel_seats"] == {"enabled": False, "workers": None}


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
    # capture the uninterrupted run's rating + summary to compare against resume
    full_standings = json.loads((out / "standings.json").read_text())["standings"]
    full_summary = json.loads((out / "run_summary.json").read_text())

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

    # NUMERIC PARITY: a resumed match must yield byte-identical OpenSkill ratings
    # to an uninterrupted one (empty stub orders => identical game outcomes, so
    # any divergence here is a resume-replay bug, not stub noise).
    resumed_by_id = {r["identity"]: r for r in standings}
    for fr in full_standings:
        rr = resumed_by_id[fr["identity"]]
        assert (rr["mu"], rr["sigma"]) == (fr["mu"], fr["sigma"]), (fr, rr)

    # run_summary reports WHOLE-match totals after resume, not just the resume leg
    resumed_summary = json.loads((out / "run_summary.json").read_text())
    assert resumed_summary["total_decisions"] == full_summary["total_decisions"]
    assert resumed_summary["total_fell_back"] == full_summary["total_fell_back"]
    assert len(resumed_summary["per_game_wall_clock_s"]) == 2
    assert resumed_summary["resumed"] is True

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


# --- --fresh-identities (attribution-study control) -------------------------


def test_fresh_identity_plan_pure_function():
    plan = orch.fresh_identity_plan(8, 3, "Golf")
    assert len(plan) == 8
    llm_handles = [h for ids in plan for h in ids[:-1]]
    # 24 unique handles, never reused, freerider stable + excluded
    assert len(llm_handles) == 24 == len(set(llm_handles))
    assert all(ids[-1] == "Golf" for ids in plan)
    assert "Golf" not in llm_handles
    # no collision with the prior canonical arms' persistent identities
    assert not {"Delta", "Echo", "Foxtrot"} & set(llm_handles)


def test_fresh_identity_plan_pool_exhaustion_and_collision():
    with pytest.raises(ValueError, match="unique handles"):
        orch.fresh_identity_plan(9, 3, "Golf")   # 27 > 24-handle pool
    with pytest.raises(ValueError, match="collides"):
        orch.fresh_identity_plan(2, 3, "Bravo")  # freerider inside the pool


def test_fresh_identities_dry_run_plan(tmp_path):
    out = tmp_path / "run"
    rc = orch.main([
        "--match-id", "unit-test-fresh",
        "--num-games", "8",
        "--seed-rng", "999",
        "--out-dir", str(out),
        "--fresh-identities",
        "--dry-run",
    ])
    assert rc == 0
    plan = json.loads((out / "campaign_plan.json").read_text())
    assert plan["fresh_identities"] is True
    assert plan["entrant_identities"] is None       # no stable LLM identities
    per_game = plan["per_game_identities"]
    assert len(per_game) == 8

    # every LLM handle appears in exactly ONE game; Golf in all of them
    llm_handles = [h for ids in per_game for h in ids[:-1]]
    assert len(llm_handles) == 24 == len(set(llm_handles))
    assert plan["freerider_handles"] == ["Golf"]
    assert plan["handle_roles"]["Golf"] == "freerider"
    assert sum(1 for r in plan["handle_roles"].values() if r == "llm-entrant") == 24

    # rotation is untouched: Golf still walks the §7.4 cyclic Latin square,
    # and each game's identity_by_seat uses that game's fresh handles
    for g in plan["seatings"]:
        k = g["game_index"]
        assert g["freerider_seats"] == [(3 + k) % 4]
        assert g["identity_by_seat"][(3 + k) % 4] == "Golf"
        assert set(g["identity_by_seat"]) == set(per_game[k])

    # the sealed secret records the fresh plan (crash-resume validation)
    secret = json.loads((out / "seed_manifest.secret.json").read_text())
    assert secret["fresh_identities"] is True
    assert secret["per_game_identities"] == per_game


def _fresh_stub_factory(max_turns: int):
    """--fresh-identities calls the factory once per entrant per GAME, so each
    instance scripts exactly one game: (negotiate, orders) x max_turns + one
    self-note."""
    from foedus.agents.llm.client import StubLLMClient
    from foedus.agents.llm.diplomat import LLMDiplomat

    def factory():
        responses = [_neg(), _orders()] * max_turns
        responses += ["A neutral private note about the opponents."]
        return LLMDiplomat(client=StubLLMClient(responses))

    return factory


def test_fresh_identities_e2e_no_cross_game_memory(tmp_path):
    """The control's load-bearing property: game 1 runs with EMPTY cross-game
    memory (no PRIOR GAMES block) under fresh handles, while within-game
    machinery (legend, memory files, ratings, scorecard) works as usual."""
    out = tmp_path / "run"
    rc = orch.main(
        ["--match-id", "e2e-fresh", "--num-games", "2", "--max-turns", "2",
         "--seed-rng", "3", "--out-dir", str(out), "--fresh-identities"],
        agent_factory=_fresh_stub_factory(max_turns=2),
    )
    assert rc == 0

    plan = json.loads((out / "campaign_plan.json").read_text())
    per_game = plan["per_game_identities"]
    sweeps = [json.loads(l) for l in (out / "sweep.jsonl").read_text().splitlines()]
    assert len(sweeps) == 2
    for g, s in enumerate(sweeps):
        assert set(s["agents"]) == set(per_game[g])
        assert s["agents"][(3 + g) % 4] == "Golf"   # rotation intact
    # zero handle overlap between games except the freerider
    assert set(sweeps[0]["agents"]) & set(sweeps[1]["agents"]) == {"Golf"}

    # game 1 prompt: legend YES (v1.1 unchanged), PRIOR GAMES NO (fresh memory)
    seat = sweeps[1]["llm_seats"][0]
    recs = [json.loads(x) for x in
            (out / f"decisions_game1_seat{seat}.jsonl").read_text().splitlines()]
    neg = next(r for r in recs if r["phase"] == "negotiate")
    user = neg["prompt"]["user"]
    assert "PLAYER HANDLES THIS GAME" in user
    assert "PRIOR GAMES" not in user

    # every persisted memory file holds exactly ONE record (its own game) —
    # direct audit evidence that nothing accumulated across games
    mem_files = sorted(out.glob("campaign_memory_game*_seat*.json"))
    assert len(mem_files) == 6  # 2 games x 3 LLM seats
    for p in mem_files:
        d = json.loads(p.read_text())
        assert len(d["records"]) == 1, p.name
        assert d["entrant_identity"] in plan["handle_roles"]

    # standings: 2x3 one-game identities + Golf rated across both games
    standings = json.loads((out / "standings.json").read_text())["standings"]
    assert {r["identity"] for r in standings} == set(per_game[0]) | set(per_game[1])
    assert len(standings) == 7

    # commit-reveal + scorecard still work end-to-end
    revealed = campaign.SeedManifest.from_dict(
        json.loads((out / "seed_manifest.revealed.json").read_text()))
    assert campaign.verify(revealed)
    import foedus_canonical_scorecard as sc
    rep = sc.build_report(str(out))
    assert rep["aggregate"]["n_games"] == 2
    assert all(t["freerider_seat"] is not None for t in rep["trajectory"])


def test_fresh_identities_resume_continues_from_crash(tmp_path):
    """Crash-resume under --fresh-identities: same seeds, same per-game handle
    plan, ratings replayed to numeric parity, and NO cross-game memory restore
    (later games stay fresh)."""
    out = tmp_path / "run"
    argv = ["--match-id", "resume-fresh", "--num-games", "2", "--max-turns", "2",
            "--seed-rng", "5", "--out-dir", str(out), "--fresh-identities"]
    orch.main(argv, agent_factory=_fresh_stub_factory(max_turns=2))
    full = [json.loads(l) for l in (out / "sweep.jsonl").read_text().splitlines() if l.strip()]
    assert len(full) == 2
    full_standings = json.loads((out / "standings.json").read_text())["standings"]

    # crash after game 0
    (out / "sweep.jsonl").write_text(json.dumps(full[0]) + "\n")
    tel = [l for l in (out / "telemetry.jsonl").read_text().splitlines() if l.strip()]
    (out / "telemetry.jsonl").write_text(tel[0] + "\n")
    for pat in ("decisions_game1_*", "campaign_memory_game1_*", "transcript_game1.md",
                "seed_manifest.revealed.json", "standings.json", "run_summary.json"):
        for p in out.glob(pat):
            p.unlink()

    rc = orch.main(argv + ["--resume"], agent_factory=_fresh_stub_factory(max_turns=2))
    assert rc == 0

    sweeps = [json.loads(l) for l in (out / "sweep.jsonl").read_text().splitlines() if l.strip()]
    assert len(sweeps) == 2
    assert sweeps[1]["seed"] == full[1]["seed"]              # SAME sealed seed
    assert sweeps[1]["agents"] == full[1]["agents"]          # SAME fresh handles

    # game 1 still fresh after resume: no PRIOR GAMES in its prompts
    seat = sweeps[1]["llm_seats"][0]
    recs = [json.loads(x) for x in
            (out / f"decisions_game1_seat{seat}.jsonl").read_text().splitlines()]
    neg = next(r for r in recs if r["phase"] == "negotiate")
    assert "PRIOR GAMES" not in neg["prompt"]["user"]

    revealed = campaign.SeedManifest.from_dict(
        json.loads((out / "seed_manifest.revealed.json").read_text()))
    assert campaign.verify(revealed)

    # numeric rating parity with the uninterrupted run
    standings = json.loads((out / "standings.json").read_text())["standings"]
    resumed_by_id = {r["identity"]: r for r in standings}
    for fr in full_standings:
        rr = resumed_by_id[fr["identity"]]
        assert (rr["mu"], rr["sigma"]) == (fr["mu"], fr["sigma"]), (fr, rr)


def test_fresh_identities_resume_flag_mismatch_rejected(tmp_path):
    """Resuming a fresh-identities match WITHOUT the flag (or vice versa) must
    fail loud — it would silently change the identity design mid-seal."""
    out = tmp_path / "run"
    argv = ["--match-id", "mismatch-fresh", "--num-games", "2", "--max-turns", "2",
            "--seed-rng", "5", "--out-dir", str(out), "--fresh-identities"]
    orch.main(argv, agent_factory=_fresh_stub_factory(max_turns=2))
    with pytest.raises(SystemExit):
        orch.main(["--match-id", "mismatch-fresh", "--num-games", "2",
                   "--max-turns", "2", "--seed-rng", "5", "--out-dir", str(out),
                   "--resume"],
                  agent_factory=_fresh_stub_factory(max_turns=2))


def test_fresh_identities_seal_first_launch_flow(tmp_path):
    """The seal-first launch flow used by the attribution study: (1) --dry-run
    writes + we COMMIT the sealed manifest/plan before any game, (2) the real
    run starts via --resume from zero completed games (empty sweep/telemetry),
    so the pre-committed seal is never re-rolled."""
    out = tmp_path / "run"
    argv = ["--match-id", "seal-first", "--num-games", "2", "--max-turns", "2",
            "--seed-rng", "11", "--out-dir", str(out), "--fresh-identities"]
    rc = orch.main(argv + ["--dry-run"])
    assert rc == 0
    sealed_commit = json.loads(
        (out / "seed_manifest.sealed.json").read_text())["commit"]

    # the launch script touches these so --resume accepts a zero-game resume
    (out / "sweep.jsonl").touch()
    (out / "telemetry.jsonl").touch()
    rc = orch.main(argv + ["--resume"],
                   agent_factory=_fresh_stub_factory(max_turns=2))
    assert rc == 0

    # the run played ALL games under the ORIGINAL seal
    sweeps = [json.loads(l) for l in (out / "sweep.jsonl").read_text().splitlines() if l.strip()]
    assert len(sweeps) == 2
    revealed = campaign.SeedManifest.from_dict(
        json.loads((out / "seed_manifest.revealed.json").read_text()))
    assert campaign.verify(revealed)
    assert revealed.commit == sealed_commit
    assert json.loads((out / "run_summary.json").read_text())["resumed"] is True
