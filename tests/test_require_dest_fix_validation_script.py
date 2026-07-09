"""Integration test for scripts/foedus_require_dest_fix_validation.py's
file-reading + replay glue (M-foedus-require-dest-legality-fix).

The deep logic it composes -- parse_order acceptance, geometric_legality,
counterfactual re-resolution, replay fidelity -- is unit-tested in
tests/test_llm_parse.py and tests/test_resolution_replay.py against synthetic
fixtures. This covers only what the validation script adds on top: replaying a
sealed-shaped out-dir end-to-end into `build_report` and reporting the
attack-backing require_dest pins found. The tiny synthetic game here has NO
require_dest declarations (its scripted client emits only Move/empty orders),
so the correct result is an empty finding set -- proving the script runs the
whole replay end-to-end without crashing and reports honestly when there is
nothing to reclassify.

The DECISIVE validation (12 dropped->accepted, 9-of-12 counterfactual flips)
is the script's `main()` assertion block run against the REAL sealed corpus,
which reproduces S1.5's autopsy-s1-5-confounds.md numbers exactly; that is not
reproduced here (no test touches the sealed run -- same discipline as
tests/test_resolution_replay.py).
"""

from __future__ import annotations

import os
import sys

_SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

import foedus_require_dest_fix_validation as validation  # noqa: E402

from tests.test_s1_5_confound_check_script import _write_synthetic_run


def test_build_report_end_to_end_finds_no_pins_in_a_pin_free_game(tmp_path):
    out = _write_synthetic_run(tmp_path)
    rep = validation.build_report(str(out))

    # The scripted client never emits a require_dest Support, so there is
    # nothing to reclassify -- the script must run the full replay end-to-end
    # and report an empty, self-consistent finding set (not crash, not
    # hallucinate a pin).
    assert rep["attack_backing_pin_supports"] == []
    t = rep["totals"]
    assert t["count"] == 0
    assert t["after_accepted"] == 0
    assert t["resolver_accepts"] == 0
    assert t["before_in_candidate_list"] == 0
    assert t["mover_flips_to_success"] == 0
