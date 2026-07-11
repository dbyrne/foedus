"""Per-phase JSON schemas for constrained (structured-output) decoding.

Ollama's ``/api/chat`` accepts an optional ``format`` that is a JSON schema;
llama.cpp compiles it to a generation grammar so the model can ONLY emit text
matching the schema. G2 uses this to force **structurally-valid moves from both
arms** (trained entrant + untrained base) so the surviving placement gap in the
sealed eval measures *strategy*, not JSON fluency -- G1 showed the untrained
base emits invalid JSON ~half the time and falls back to Hold, which confounds
"beats-own-base" with "can-emit-JSON".

Design contract (the #1 review target):

* **Force STRUCTURE, leave VALUES free.** The schema fixes the decision
  *shape* the model is asked to emit (:mod:`foedus.agents.llm.render`) and
  that the parser accepts (:mod:`foedus.agents.llm.parse`) -- which keys exist,
  their JSON types, the closed enums (stance, order ``type``). It never
  constrains a strategic *value*: which unit, which destination/target, which
  stance, whom to ally, how many intents/pacts. Those stay free to the model.
* **Accept every legal decision.** Every real teacher decision in the G1 SFT
  corpus validates against these schemas (asserted in the tests). If the schema
  rejected a legal decision it would silently bias the eval, so "too tight" is a
  bug, not a preference.
* **Ids are int-or-string.** :func:`foedus.agents.llm.parse.coerce_id` accepts a
  bare int (``2``) *or* a letter-prefixed string (``"u2"``, ``"p1"``) -- and the
  corpus actually contains both (20 orders-phase targets are ``"u<n>"`` strings)
  -- so every id field admits ``["integer", "string"]``. Narrowing it to
  integer-only would reject legal teacher output.

Structural validity (does the emitted JSON match the schema) is DISTINCT from
semantic legality (is the order a geometrically-legal move on this board). The
schema enforces only the former; an in-schema but illegal order (e.g. a Move to
a non-adjacent node) is still coerced to Hold by the parser and is measured
separately as *residual illegality*. That separation is the whole point: it
tells us whether the JSON confound is cleanly removed.
"""

from __future__ import annotations

# An id field: a bare int, or a letter-prefixed / bare-digit string. Mirrors
# exactly what parse.coerce_id accepts (unit ids, node ids, player ids, pact
# ids). A fresh dict is returned by _id() per use so no two schema nodes alias
# the same mutable object.
_STANCE_VALUES = ["ally", "neutral", "hostile"]
_ORDER_TYPES = ["Hold", "Move", "Support"]


def _id() -> dict:
    """Schema for one id value (unit/node/player/pact id): int or string."""
    return {"type": ["integer", "string"]}


def order_schema() -> dict:
    """Schema for one order object, as a discriminated union over ``type``.

    Mirrors :func:`foedus.agents.llm.parse.parse_order` and the RESPONSE FORMAT
    block in :mod:`foedus.agents.llm.render`:

    * ``{"type": "Hold"}``
    * ``{"type": "Move", "dest": <id>}``
    * ``{"type": "Support", "target": <id>}``
    * ``{"type": "Support", "target": <id>, "require_dest": <id>}``

    Using ``anyOf`` per ``type`` forces the geometry field that ``type`` needs
    (a Move HAS a dest; a Support HAS a target) so a constrained model cannot
    emit a structurally-headless order -- while leaving the dest/target/
    require_dest *values* free. ``require_dest`` is optional (the opt-in "pin"
    refinement). Each branch is closed (``additionalProperties: false``); the
    corpus never carries an extra key on any order.
    """
    return {
        "anyOf": [
            {
                "type": "object",
                "properties": {"type": {"const": "Hold"}},
                "required": ["type"],
                "additionalProperties": False,
            },
            {
                "type": "object",
                "properties": {"type": {"const": "Move"}, "dest": _id()},
                "required": ["type", "dest"],
                "additionalProperties": False,
            },
            {
                "type": "object",
                "properties": {
                    "type": {"const": "Support"},
                    "target": _id(),
                    "require_dest": _id(),
                },
                "required": ["type", "target"],
                "additionalProperties": False,
            },
        ]
    }


def _intent_schema() -> dict:
    """One declared intent: unit + its declared order + visibility.

    ``visible_to`` is ``null`` (public broadcast) or a list of player ids (a
    private group) -- exactly what parse.parse_intent reads. Every corpus intent
    carries all three keys, so all three are required (forcing the base to emit
    them); the visibility *value* stays free.
    """
    return {
        "type": "object",
        "properties": {
            "unit_id": _id(),
            "declared_order": order_schema(),
            "visible_to": {"type": ["null", "array"], "items": _id()},
        },
        "required": ["unit_id", "declared_order", "visible_to"],
        "additionalProperties": False,
    }


def _pact_term_schema() -> dict:
    """One pact term: a (player, unit) pledged to a declared order."""
    return {
        "type": "object",
        "properties": {
            "player": _id(),
            "unit_id": _id(),
            "declared_order": order_schema(),
        },
        "required": ["player", "unit_id", "declared_order"],
        "additionalProperties": False,
    }


def negotiation_decision_schema() -> dict:
    """Schema for the negotiate-phase decision object.

    Shape (from render's RESPONSE FORMAT + parse_negotiation_response)::

        {
          "press": {
            "stance": {"<pid>": "ally|neutral|hostile", ...},
            "intents": [ {unit_id, declared_order, visible_to}, ... ]
          },
          "pacts": {
            "propose": [ {counterparty, terms:[{player, unit_id, declared_order}]} ],
            "accept": [ <pact_id>, ... ]
          }
        }

    ``stance`` is a free-keyed object (which players is the model's choice) whose
    values are the closed stance enum. ``intents`` / ``propose`` / ``accept`` are
    arrays that may be empty. The skeleton keys (press/pacts, stance/intents,
    propose/accept) are all required: every corpus decision carries the full
    skeleton, so requiring it rejects no legal decision while forcing the base to
    emit the whole structure rather than a fragment that degrades to Hold.
    """
    return {
        "type": "object",
        "properties": {
            "press": {
                "type": "object",
                "properties": {
                    "stance": {
                        "type": "object",
                        "additionalProperties": {"enum": list(_STANCE_VALUES)},
                    },
                    "intents": {"type": "array", "items": _intent_schema()},
                },
                "required": ["stance", "intents"],
                "additionalProperties": False,
            },
            "pacts": {
                "type": "object",
                "properties": {
                    "propose": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "counterparty": _id(),
                                "terms": {
                                    "type": "array",
                                    "items": _pact_term_schema(),
                                },
                            },
                            "required": ["counterparty", "terms"],
                            "additionalProperties": False,
                        },
                    },
                    "accept": {"type": "array", "items": _id()},
                },
                "required": ["propose", "accept"],
                "additionalProperties": False,
            },
        },
        "required": ["press", "pacts"],
        "additionalProperties": False,
    }


def orders_decision_schema() -> dict:
    """Schema for the orders-phase decision object.

    Shape (from render + parse_orders_response)::

        {"orders": {"<unit_id>": <order>, ...}}

    ``orders`` is a free-keyed object (which units, and how many, is the model's
    choice -- an omitted owned unit defaults to Hold downstream) mapping each id
    to an order object. Values are forced to the order schema; keys stay free
    (parse.coerce_id turns the string key back into a unit id).
    """
    return {
        "type": "object",
        "properties": {
            "orders": {
                "type": "object",
                "additionalProperties": order_schema(),
            }
        },
        "required": ["orders"],
        "additionalProperties": False,
    }


#: Phase name -> schema builder. The negotiate/orders phases are the two
#: constrained decision calls; the (campaign-only) self-note call is free text
#: and is intentionally absent -- it must never be constrained to JSON.
_PHASE_SCHEMAS = {
    "negotiate": negotiation_decision_schema,
    "orders": orders_decision_schema,
}


def schema_for_phase(phase: str) -> dict:
    """Return a fresh decision schema for ``phase`` ("negotiate" | "orders")."""
    try:
        return _PHASE_SCHEMAS[phase]()
    except KeyError:
        raise ValueError(
            f"no constrained-decoding schema for phase {phase!r}; "
            f"expected one of {sorted(_PHASE_SCHEMAS)}"
        ) from None
