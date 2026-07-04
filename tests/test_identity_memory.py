"""Ruleset v1.1 — identity-keyed campaign memory.

The ratified format rotates seats every game, but PR #38 campaign memory keyed
opponents by seat and its self-note prompt told agents "the next game reuses the
SAME seats". Under rotation that misattributes a note about one entrant to
whoever inherits its old seat. v1.1 fixes this: entrants carry stable neutral
HANDLES; agents see opponents by handle in the cross-game record + a per-game
seat legend, and memory/self-notes key on the handle. Handles double as the
OpenSkill identities.

These tests are opt-in: when no `IdentityContext` is supplied, rendering and
facts stay byte-identical to the seat-keyed behaviour (covered by
test_campaign_render.py / test_campaign_memory.py), so the single-game and PR #38
arms are untouched.
"""

from __future__ import annotations

from foedus.agents.llm.campaign_memory import (
    CampaignMemory, GameFacts, GameRecord, IdentityContext, OpponentGameFacts,
    build_game_facts,
)
from foedus.agents.llm.render import (
    _render_visible_units,
    render_campaign_record,
    render_game_facts,
    render_identity_legend,
    render_negotiation_prompt,
    render_orders_prompt,
    render_self_note_prompt,
)
from foedus.eval.memory_metrics import parse_visible_owners
from foedus.fog import visible_state_for
from tests.helpers import simple_two_player_state

# same neutrality bar as the within-game ledger (test_campaign_render.py)
LEADING_WORDS = [
    "exploit", "beware", "punish", "freerid", "betray", "cheat", "distrust",
    "suspicious", "loyal", "enemy", "deserve", "retaliat", "backstab", "liar",
    "untrustworthy", "consider", "recommend", "advise", "warn", "reward",
    "trust", "danger", "should", "must ", "ought", "coalition", "gang",
]


def _handle_facts(idx: int, seed: int, golf_seat: int) -> GameFacts:
    """A game record (seat 0 = me = 'Delta') where the freerider handle 'Golf'
    sat in `golf_seat`, with the other entrants filling the remaining seats."""
    others = iter(["Delta", "Echo", "Foxtrot"])
    handles = {s: ("Golf" if s == golf_seat else next(others)) for s in range(4)}
    return build_game_facts(
        None,
        {"scores": {0: 10.0, 1: 12.0, 2: 9.0, 3: 20.0},
         "your_pacts": [], "your_pact_breaches": [], "your_betrayals": []},
        0, seed=seed, game_index=idx,
        identity=IdentityContext(my_handle=handles[0],
                                 seat_to_handle=dict(handles)),
    )


class TestIdentityContextOnFacts:
    def test_build_game_facts_records_handles(self):
        ident = IdentityContext(
            my_handle="Delta",
            seat_to_handle={0: "Delta", 1: "Echo", 2: "Foxtrot", 3: "Golf"})
        facts = build_game_facts(
            None,
            {"scores": {0: 1.0, 1: 2.0, 2: 3.0, 3: 4.0},
             "your_pacts": [], "your_pact_breaches": [], "your_betrayals": []},
            0, seed=7, game_index=1, identity=ident)
        assert facts.my_handle == "Delta"
        assert facts.handles == {0: "Delta", 1: "Echo", 2: "Foxtrot", 3: "Golf"}

    def test_facts_roundtrip_preserves_handles(self):
        ident = IdentityContext(
            my_handle="Echo",
            seat_to_handle={0: "Delta", 1: "Echo", 2: "Foxtrot", 3: "Golf"})
        facts = build_game_facts(
            None,
            {"scores": {0: 1.0, 1: 2.0, 2: 3.0, 3: 4.0},
             "your_pacts": [], "your_pact_breaches": [], "your_betrayals": []},
            1, seed=7, game_index=0, identity=ident)
        rt = GameFacts.from_dict(facts.to_dict())
        assert rt.my_handle == "Echo"
        assert rt.handles == {0: "Delta", 1: "Echo", 2: "Foxtrot", 3: "Golf"}

    def test_no_identity_leaves_handles_none(self):
        facts = build_game_facts(
            None,
            {"scores": {0: 1.0, 1: 2.0}, "your_pacts": [],
             "your_pact_breaches": [], "your_betrayals": []},
            0, seed=1, game_index=0)
        assert facts.my_handle is None and facts.handles is None


class TestHandleRendering:
    def test_render_game_facts_uses_handles_not_seats(self):
        facts = _handle_facts(0, 11, golf_seat=3)  # Golf at seat 3
        text = "\n".join(render_game_facts(facts, 0))
        assert "Golf" in text and "Echo" in text and "Foxtrot" in text
        # opponents are named by handle, not "p1/p2/p3"
        assert "p1:" not in text and "p2:" not in text and "p3:" not in text

    def test_render_game_facts_handles_are_neutral(self):
        facts = _handle_facts(0, 11, golf_seat=3)
        text = "\n".join(render_game_facts(facts, 0)).lower()
        for w in LEADING_WORDS:
            assert w not in text, f"leading word leaked: {w!r}"

    def test_legend_maps_seats_to_handles_and_marks_you(self):
        ident = IdentityContext(
            my_handle="Echo",
            seat_to_handle={0: "Delta", 1: "Echo", 2: "Foxtrot", 3: "Golf"})
        text = "\n".join(render_identity_legend(ident, 1))
        assert "p0 = Delta" in text and "p1 = Echo" in text
        assert "(you)" in text
        for w in LEADING_WORDS:
            assert w not in text.lower(), f"leading word in legend: {w!r}"


class TestCrossGameHandleRoundTrip:
    def test_same_handle_tracks_entrant_across_rotated_seats(self):
        # Nova's required round-trip: a record about 'Golf' in game 0 (seat 3)
        # is still about 'Golf' in game 1 (seat 1), regardless of seat.
        cm = CampaignMemory()
        cm.append(GameRecord(facts=_handle_facts(0, 100, golf_seat=3),
                             self_note="Golf ran ahead last game."))
        cm.append(GameRecord(facts=_handle_facts(1, 101, golf_seat=1),
                             self_note="Golf again."))
        text = "\n".join(render_campaign_record(cm, 0))
        # both prior games attribute facts to the stable handle 'Golf'
        assert text.count("Golf") >= 2
        # the verbatim notes are preserved
        assert "Golf ran ahead last game." in text


class TestSelfNotePromptIdentity:
    def test_self_note_prompt_drops_same_seats_and_uses_handles(self):
        facts = _handle_facts(0, 5, golf_seat=3)
        system, user = render_self_note_prompt(facts, 0)
        assert "SAME seats" not in system
        # opponents named by handle in the facts handed to the model
        assert "Golf" in user

    def test_self_note_prompt_without_handles_is_unchanged(self):
        facts = GameFacts(game_index=0, seed=0, my_seat=0, my_rank=1, n_players=2,
                          final_scores={0: 1.0, 1: 2.0}, per_opponent={})
        system, _ = render_self_note_prompt(facts, 0)
        assert "SAME seats" in system  # back-compat: seat-mode wording intact


class TestNegotiationPromptToggle:
    def _state_view(self):
        state = simple_two_player_state()
        view = visible_state_for(state, 0)
        return state, view

    def test_identity_adds_legend(self):
        state, view = self._state_view()
        ident = IdentityContext(my_handle="Delta",
                                seat_to_handle={0: "Delta", 1: "Echo"})
        _, user = render_negotiation_prompt(state, view, 0, identity=ident)
        assert "Delta" in user and "Echo" in user
        assert "= Delta" in user  # the legend line

    def test_no_identity_is_byte_identical(self):
        state, view = self._state_view()
        _, a = render_negotiation_prompt(state, view, 0)
        _, b = render_negotiation_prompt(state, view, 0, identity=None)
        assert a == b
        assert "= Delta" not in a  # no legend when identity absent


class TestVisibleUnitsRenderMetricsContract:
    """Locks the render <-> memory_metrics ownership-parse contract for BOTH
    arms, so the marker format and the extractor regex can never silently drift
    (the bug both reviewers caught: subsidy/coalition silently zeroed)."""

    VIEW = {"visible_units": [
        {"id": 5, "location": 12, "owner": 0},   # mine (me = seat 0)
        {"id": 8, "location": 7, "owner": 2},    # enemy seat 2
        {"id": 9, "location": 3, "owner": 3},    # enemy seat 3
    ]}
    IDENT = IdentityContext(
        my_handle="Delta",
        seat_to_handle={0: "Delta", 1: "Echo", 2: "Foxtrot", 3: "Golf"})

    def test_identity_arm_owners_parse(self):
        text = "\n".join(_render_visible_units(self.VIEW, 0, self.IDENT))
        assert "(p2 (Foxtrot))" in text and "(p3 (Golf))" in text
        assert parse_visible_owners(text, 0) == {5: 0, 8: 2, 9: 3}

    def test_baseline_arm_is_byte_identical_and_parses(self):
        text = "\n".join(_render_visible_units(self.VIEW, 0, None))
        # true back-compat: the pre-v1.1 literal marker, not "(p2)"
        assert "u8 at node 7 (player 2)" in text
        assert "(p2" not in text
        assert parse_visible_owners(text, 0) == {5: 0, 8: 2, 9: 3}

    def test_full_orders_prompt_owners_parse_under_identity(self):
        state = simple_two_player_state()
        view = visible_state_for(state, 0)
        ident = IdentityContext(my_handle="Delta",
                                seat_to_handle={0: "Delta", 1: "Echo"})
        _, user = render_orders_prompt(state, view, 0, [], identity=ident)
        owners = parse_visible_owners(user, 0)
        # every VISIBLE UNIT line is recovered (own + any visible enemy)
        assert owners  # non-empty
        for u in view["visible_units"]:
            assert owners.get(u["id"]) == u["owner"]
