"""Opt-in real-Ollama smoke test for G2 constrained decoding.

NOT part of the default CI signal: requires FOEDUS_LLM_SMOKE=1 AND a reachable
local Ollama server with the `foedus-base-v1` model. Confirms the two live G2a
claims cheaply (one call per phase):

* the per-phase JSON schema COMPILES into an Ollama generation grammar (the call
  returns 200, not a schema/grammar error), and
* the untrained base -- which is JSON-unfit unconstrained -- emits a
  STRUCTURALLY-VALID decision for BOTH phases when the schema is passed.

The full denominated validation (base-repair drop, residual illegality) is
`scripts/foedus_g2_constraint_probe.py`; this is the fast reproducible check.

Run manually:
    OLLAMA_HOST=http://localhost:11434 FOEDUS_LLM_SMOKE=1 \
        pytest tests/smoke/test_llm_schema_ollama_smoke.py -s
"""

from __future__ import annotations

import json
import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("FOEDUS_LLM_SMOKE") != "1",
    reason="opt-in only: set FOEDUS_LLM_SMOKE=1 (and a reachable Ollama) to run",
)

BASE_MODEL = os.environ.get("FOEDUS_G2_BASE_MODEL", "foedus-base-v1")


def _ollama_has_model(host: str, model: str) -> bool:
    try:
        import httpx
        r = httpx.get(f"{host.rstrip('/')}/api/tags", timeout=2.0)
        if r.status_code != 200:
            return False
        names = {m["name"] for m in r.json().get("models", [])}
        return model in names or f"{model}:latest" in names
    except Exception:
        return False


def test_constrained_base_emits_valid_decision_both_phases() -> None:
    import jsonschema

    from foedus.agents.llm.client import OllamaClient
    from foedus.agents.llm.parse import extract_json_with_recovery
    from foedus.agents.llm.render import (
        NEGOTIATION_SYSTEM_PROMPT,
        ORDERS_SYSTEM_PROMPT,
    )
    from foedus.agents.llm.schema import (
        negotiation_decision_schema,
        orders_decision_schema,
    )

    host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    if not _ollama_has_model(host, BASE_MODEL):
        pytest.skip(f"Ollama at {host} lacks model {BASE_MODEL!r}")

    client = OllamaClient(model=BASE_MODEL, host=host, timeout=120.0)

    # Minimal but realistic per-phase prompts (the schema forces structure; the
    # exact board is irrelevant to a STRUCTURAL-validity smoke).
    cases = [
        (NEGOTIATION_SYSTEM_PROMPT,
         "You are Player 0. Opponents: 1, 2, 3. Your units: u1 at node 5 "
         "(legal orders: Hold, Move 6). Reply with the negotiation JSON.",
         negotiation_decision_schema()),
        (ORDERS_SYSTEM_PROMPT,
         "You are Player 0. Your units: u1 at node 5 (legal orders: Hold, "
         "Move 6). Reply with the orders JSON.",
         orders_decision_schema()),
    ]

    for system, user, schema in cases:
        raw = client.complete(system, user, format=schema)
        data, _ = extract_json_with_recovery(raw)
        assert isinstance(data, dict), f"base emitted no dict under constraint: {raw!r}"
        # Structurally-valid decision -- the whole point of constrained decoding.
        jsonschema.validate(data, schema)
        print(f"\n[schema smoke] {BASE_MODEL} phase-ok: {json.dumps(data)[:160]}")
