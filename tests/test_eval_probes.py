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
