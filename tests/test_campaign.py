"""Tests for the canonical ruleset-v1 match-protocol helpers.

Covers the two pieces of pure match glue that live *around* the engine
(docs/design/2026-07-04-ruleset-v1.md §7.4 seat rotation, §7.5 commit-reveal
seeds). The orchestrator (scripts/foedus_canonical_campaign.py) composes these;
the engine itself is untouched.
"""

from __future__ import annotations

import random

import pytest

from foedus.eval import campaign


# --- §7.4 cyclic seat rotation -------------------------------------------

class TestSeatRotation:
    def test_seat_of_entrant_formula(self):
        # game k: entrant i -> seat (i + k) mod n  (design §7.4)
        assert campaign.seat_of_entrant(0, 0, 4) == 0
        assert campaign.seat_of_entrant(1, 0, 4) == 1
        assert campaign.seat_of_entrant(0, 1, 4) == 1
        assert campaign.seat_of_entrant(3, 1, 4) == 0  # wraps
        assert campaign.seat_of_entrant(2, 3, 4) == 1

    def test_entrant_at_seat_is_inverse(self):
        n = 4
        for k in range(10):
            for i in range(n):
                s = campaign.seat_of_entrant(i, k, n)
                assert campaign.entrant_at_seat(s, k, n) == i

    def test_seat_assignment_is_a_permutation(self):
        for k in range(12):
            assign = campaign.seat_assignment(k, 4)  # seat -> entrant
            assert sorted(assign.keys()) == [0, 1, 2, 3]
            assert sorted(assign.values()) == [0, 1, 2, 3]  # bijection

    def test_latin_square_each_entrant_each_seat_once_per_cycle(self):
        # over any n consecutive games, each entrant occupies each seat once
        n = 4
        seats_seen = {i: set() for i in range(n)}
        for k in range(n):
            for i in range(n):
                seats_seen[i].add(campaign.seat_of_entrant(i, k, n))
        for i in range(n):
            assert seats_seen[i] == {0, 1, 2, 3}

    def test_eight_games_are_two_full_cycles(self):
        # game k and game k+n have identical assignments
        n = 4
        for k in range(n):
            assert campaign.seat_assignment(k, n) == campaign.seat_assignment(k + n, n)

    def test_validation(self):
        with pytest.raises(ValueError):
            campaign.seat_of_entrant(0, 0, 0)
        with pytest.raises(ValueError):
            campaign.seat_of_entrant(5, 0, 4)  # entrant out of range
        with pytest.raises(ValueError):
            campaign.seat_of_entrant(0, -1, 4)  # negative game
        with pytest.raises(ValueError):
            campaign.entrant_at_seat(9, 0, 4)  # seat out of range


# --- §7.5 commit-reveal seed manifest ------------------------------------

class TestSeedManifest:
    def test_commitment_is_deterministic_and_formula_bound(self):
        import hashlib
        match_id = "canonical-v1-test"
        seeds = [10, 20, 30]
        nonce = "deadbeef"
        got = campaign.seed_commitment(match_id, seeds, nonce)
        payload = f"{campaign.DOMAIN}|{match_id}|{campaign.canonical_seed_json(seeds)}|{nonce}"
        want = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        assert got == want
        # stable across calls
        assert got == campaign.seed_commitment(match_id, seeds, nonce)

    def test_canonical_json_preserves_order_and_is_compact(self):
        assert campaign.canonical_seed_json([3, 1, 2]) == "[3,1,2]"

    def test_draw_seeds_reproducible_with_seeded_rng(self):
        a = campaign.draw_seeds(8, rng=random.Random(42))
        b = campaign.draw_seeds(8, rng=random.Random(42))
        assert a == b
        assert len(a) == 8
        assert all(isinstance(s, int) and s >= 0 for s in a)

    def test_seal_produces_commit_only_manifest(self):
        m, seeds, nonce = campaign.seal("m1", 8, rng=random.Random(1))
        assert m.match_id == "m1"
        assert m.num_games == 8
        assert len(m.commit) == 64  # sha256 hex
        # the sealed (publishable-before) manifest hides the seeds + nonce
        assert m.seeds is None
        assert m.nonce is None
        assert not m.revealed
        assert len(seeds) == 8
        assert isinstance(nonce, str) and nonce

    def test_reveal_then_verify_roundtrips(self):
        sealed, seeds, nonce = campaign.seal("m2", 8, rng=random.Random(2))
        revealed = campaign.revealed_manifest(sealed, seeds, nonce)
        assert revealed.revealed
        assert revealed.seeds == seeds
        assert revealed.nonce == nonce
        assert revealed.commit == sealed.commit  # commit unchanged by reveal
        assert campaign.verify(revealed) is True

    def test_verify_rejects_tampered_seed(self):
        sealed, seeds, nonce = campaign.seal("m3", 8, rng=random.Random(3))
        revealed = campaign.revealed_manifest(sealed, seeds, nonce)
        revealed.seeds[0] += 1  # operator tries to swap in a favourable seed
        assert campaign.verify(revealed) is False

    def test_verify_rejects_tampered_nonce_or_match_id(self):
        sealed, seeds, nonce = campaign.seal("m4", 8, rng=random.Random(4))
        r1 = campaign.revealed_manifest(sealed, seeds, nonce)
        r1.nonce = r1.nonce + "00"
        assert campaign.verify(r1) is False
        r2 = campaign.revealed_manifest(sealed, seeds, nonce)
        r2.match_id = "different"
        assert campaign.verify(r2) is False

    def test_verify_requires_reveal(self):
        sealed, _, _ = campaign.seal("m5", 8, rng=random.Random(5))
        # a sealed manifest has no seeds/nonce to check against the commit
        assert campaign.verify(sealed) is False

    def test_to_dict_from_dict_roundtrip_sealed_and_revealed(self):
        sealed, seeds, nonce = campaign.seal("m6", 4, rng=random.Random(6))
        assert campaign.SeedManifest.from_dict(sealed.to_dict()) == sealed
        revealed = campaign.revealed_manifest(sealed, seeds, nonce)
        rt = campaign.SeedManifest.from_dict(revealed.to_dict())
        assert rt == revealed
        assert campaign.verify(rt) is True

    def test_verify_rejects_num_games_mismatch(self):
        sealed, seeds, nonce = campaign.seal("m7", 8, rng=random.Random(7))
        revealed = campaign.revealed_manifest(sealed, seeds, nonce)
        revealed.num_games = 7  # inconsistent with len(seeds) == 8
        assert campaign.verify(revealed) is False
