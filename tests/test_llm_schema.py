"""Tests for foedus.agents.llm.schema -- the per-phase constrained-decoding
JSON schemas used by G2.

The load-bearing test is :func:`test_schema_accepts_every_corpus_decision`: a
schema that rejected a legal teacher decision would silently bias the whole G2
eval, so EVERY one of the 716 real decisions in the G1 SFT corpus must validate.
It is coverage-guarded and prints its denominators, per this repo's "assert
coverage, fail loudly" rule.

The rest pin the design contract: the schema forces STRUCTURE (skeleton keys,
JSON types, closed enums, geometry field per order type) while leaving strategic
VALUES free (which unit, dest, target, stance; how many intents/pacts), and ids
are int-or-string to match parse.coerce_id.
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from foedus.agents.llm.render import (
    NEGOTIATION_SYSTEM_PROMPT,
    ORDERS_SYSTEM_PROMPT,
)
from foedus.agents.llm.schema import (
    negotiation_decision_schema,
    order_schema,
    orders_decision_schema,
    schema_for_phase,
)
from foedus.eval._coverage import assert_coverage

_CORPUS = (
    Path(__file__).resolve().parents[1]
    / "docs/research/2026-07-10-gym-g1/phase-a/sft_g1.jsonl"
)

NEG = negotiation_decision_schema()
ORD = orders_decision_schema()


def _valid(instance: object, schema: dict) -> bool:
    try:
        jsonschema.validate(instance, schema)
        return True
    except jsonschema.ValidationError:
        return False


# --- schemas are themselves well-formed -----------------------------------

def test_schemas_are_valid_draft7() -> None:
    jsonschema.Draft7Validator.check_schema(NEG)
    jsonschema.Draft7Validator.check_schema(ORD)
    jsonschema.Draft7Validator.check_schema(order_schema())


def test_builders_return_fresh_objects() -> None:
    # Distinct dicts so no two ollama payloads alias a shared mutable schema.
    assert negotiation_decision_schema() is not negotiation_decision_schema()
    assert orders_decision_schema() is not orders_decision_schema()


# --- THE load-bearing acceptance test -------------------------------------

def _load_corpus_decisions() -> tuple[list[dict], list[dict]]:
    assert _CORPUS.exists(), f"missing G1 SFT corpus at {_CORPUS}"
    neg, orders = [], []
    with _CORPUS.open() as f:
        for line in f:
            d = json.loads(line)
            msgs = d["messages"]
            system = msgs[0]["content"]
            decision = json.loads(
                [m for m in msgs if m["role"] == "assistant"][0]["content"]
            )
            if system == NEGOTIATION_SYSTEM_PROMPT:
                neg.append(decision)
            elif system == ORDERS_SYSTEM_PROMPT:
                orders.append(decision)
    return neg, orders


def test_schema_accepts_every_corpus_decision(capsys) -> None:
    """Every real teacher decision (716) must validate. If the schema rejects a
    legal decision it is too tight -- a bug, because it would bias the eval."""
    neg, orders = _load_corpus_decisions()
    total = len(neg) + len(orders)
    # Guard the guard: the corpus must actually have been read.
    assert_coverage(total, 716, "G1 SFT corpus decisions", 1.0)

    neg_ok = sum(_valid(d, NEG) for d in neg)
    ord_ok = sum(_valid(d, ORD) for d in orders)

    with capsys.disabled():
        print(
            f"\n[schema acceptance] negotiate {neg_ok}/{len(neg)}  "
            f"orders {ord_ok}/{len(orders)}  "
            f"TOTAL {neg_ok + ord_ok}/{total}"
        )

    assert neg_ok == len(neg), f"schema rejected {len(neg) - neg_ok} legal negotiate decisions"
    assert ord_ok == len(orders), f"schema rejected {len(orders) - ord_ok} legal orders decisions"
    assert neg_ok + ord_ok == total == 716


# --- order schema: structure forced, values free --------------------------

@pytest.mark.parametrize("order", [
    {"type": "Hold"},
    {"type": "Move", "dest": 7},
    {"type": "Move", "dest": "u7"},          # id as letter-prefixed string
    {"type": "Support", "target": 0},
    {"type": "Support", "target": "u0"},
    {"type": "Support", "target": 0, "require_dest": 5},
])
def test_order_schema_accepts_all_legal_shapes(order) -> None:
    assert _valid(order, order_schema())


@pytest.mark.parametrize("order", [
    {"type": "Move"},                         # Move missing its dest
    {"type": "Support"},                      # Support missing its target
    {"type": "Attack", "dest": 7},            # type not in the closed enum
    {"type": "Hold", "dest": 7},              # extra/wrong key for Hold
    {"type": "Move", "dest": 7, "target": 1},  # dest+target mixed
    {"dest": 7},                              # missing type
    "Hold",                                   # not an object
    {"type": "Move", "dest": [7]},            # dest is neither int nor string
])
def test_order_schema_rejects_structural_violations(order) -> None:
    assert not _valid(order, order_schema())


# --- negotiation schema ---------------------------------------------------

def test_negotiation_minimal_and_full_decisions_validate() -> None:
    minimal = {"press": {"stance": {}, "intents": []},
               "pacts": {"propose": [], "accept": []}}
    full = {
        "press": {
            "stance": {"1": "ally", "2": "hostile", "3": "neutral"},
            "intents": [
                {"unit_id": 4, "declared_order": {"type": "Move", "dest": 9},
                 "visible_to": None},
                {"unit_id": "u5", "declared_order": {"type": "Support", "target": 4},
                 "visible_to": [1, 2]},
            ],
        },
        "pacts": {
            "propose": [
                {"counterparty": 3, "terms": [
                    {"player": 0, "unit_id": 4, "declared_order": {"type": "Hold"}},
                    {"player": 3, "unit_id": 7,
                     "declared_order": {"type": "Support", "target": 4,
                                        "require_dest": 9}},
                ]},
            ],
            "accept": [11, "12"],
        },
    }
    assert _valid(minimal, NEG)
    assert _valid(full, NEG)


@pytest.mark.parametrize("bad", [
    {"pacts": {"propose": [], "accept": []}},                     # no press
    {"press": {"stance": {}, "intents": []}},                     # no pacts
    {"press": {"intents": []}, "pacts": {"propose": [], "accept": []}},  # no stance
    {"press": {"stance": {"1": "friendly"}, "intents": []},       # bad stance value
     "pacts": {"propose": [], "accept": []}},
    {"press": {"stance": {}, "intents": [{"unit_id": 1}]},        # intent missing keys
     "pacts": {"propose": [], "accept": []}},
    {"press": {"stance": {}, "intents": []},
     "pacts": {"propose": [], "accept": []}, "extra": 1},         # extra top key
])
def test_negotiation_rejects_broken_structure(bad) -> None:
    assert not _valid(bad, NEG)


def test_negotiation_leaves_values_free() -> None:
    # Any player set, any stance mix, any number of intents/pacts is fine --
    # the schema constrains none of those strategic choices.
    d = {"press": {"stance": {"99": "hostile", "42": "ally"},
                   "intents": [{"unit_id": i, "declared_order": {"type": "Hold"},
                                "visible_to": None} for i in range(6)]},
         "pacts": {"propose": [], "accept": [1, 2, 3, 4, 5]}}
    assert _valid(d, NEG)


# --- orders schema --------------------------------------------------------

def test_orders_decision_accepts_free_keyed_unit_map() -> None:
    d = {"orders": {"1": {"type": "Move", "dest": 7},
                    "u2": {"type": "Support", "target": 1},
                    "3": {"type": "Hold"}}}
    assert _valid(d, ORD)
    # empty orders map is legal (all units default to Hold downstream)
    assert _valid({"orders": {}}, ORD)


@pytest.mark.parametrize("bad", [
    {},                                            # no orders key
    {"orders": []},                                # orders must be an object
    {"orders": {"1": {"type": "Fly", "dest": 7}}},  # illegal order type
    {"orders": {"1": {"type": "Move"}}},           # order missing geometry
    {"orders": {"1": {"type": "Hold"}}, "x": 1},   # extra top key
])
def test_orders_rejects_broken_structure(bad) -> None:
    assert not _valid(bad, ORD)


# --- schema_for_phase dispatch --------------------------------------------

def test_schema_for_phase_dispatch() -> None:
    assert schema_for_phase("negotiate") == NEG
    assert schema_for_phase("orders") == ORD
    with pytest.raises(ValueError):
        schema_for_phase("self_note")
    with pytest.raises(ValueError):
        schema_for_phase("bogus")


# --- phase dispatch + PhaseConstrainedClient (G2b wiring) -------------------

def test_phase_of_system_prompt_classifies_decision_calls() -> None:
    from foedus.agents.llm.render import (
        NEGOTIATION_SYSTEM_PROMPT,
        ORDERS_SYSTEM_PROMPT,
        SELF_NOTE_SYSTEM_PROMPT,
        SELF_NOTE_SYSTEM_PROMPT_IDENTITY,
    )
    from foedus.agents.llm.schema import phase_of_system_prompt

    assert phase_of_system_prompt(NEGOTIATION_SYSTEM_PROMPT) == "negotiate"
    assert phase_of_system_prompt(ORDERS_SYSTEM_PROMPT) == "orders"
    # The self-note calls are free text and MUST stay unconstrained.
    assert phase_of_system_prompt(SELF_NOTE_SYSTEM_PROMPT) is None
    assert phase_of_system_prompt(SELF_NOTE_SYSTEM_PROMPT_IDENTITY) is None
    assert phase_of_system_prompt("something else entirely") is None
    # Exact match only: a prefix/superset must not be constrained by accident.
    assert phase_of_system_prompt(ORDERS_SYSTEM_PROMPT + " extra") is None


class _FormatCapturingClient:
    """Stub inner client with the per-call `format` param, recording it."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict | None]] = []

    def complete(self, system: str, user: str, format: dict | None = None) -> str:
        self.calls.append((system, format))
        return "{}"


def test_phase_constrained_client_dispatches_per_phase_schema() -> None:
    from foedus.agents.llm.render import (
        NEGOTIATION_SYSTEM_PROMPT,
        ORDERS_SYSTEM_PROMPT,
        SELF_NOTE_SYSTEM_PROMPT,
    )
    from foedus.agents.llm.schema import PhaseConstrainedClient

    inner = _FormatCapturingClient()
    client = PhaseConstrainedClient(inner)
    client.complete(NEGOTIATION_SYSTEM_PROMPT, "user")
    client.complete(ORDERS_SYSTEM_PROMPT, "user")
    client.complete(SELF_NOTE_SYSTEM_PROMPT, "user")

    (neg_sys, neg_fmt), (ord_sys, ord_fmt), (note_sys, note_fmt) = inner.calls
    assert neg_fmt == NEG           # negotiate call carries the negotiate schema
    assert ord_fmt == ORD           # orders call carries the orders schema
    assert note_fmt is None         # self-note passes through UNCONSTRAINED
    assert client.inner is inner


def test_phase_constrained_client_satisfies_llmclient_protocol() -> None:
    from foedus.agents.llm.client import LLMClient
    from foedus.agents.llm.schema import PhaseConstrainedClient

    assert isinstance(PhaseConstrainedClient(_FormatCapturingClient()), LLMClient)
