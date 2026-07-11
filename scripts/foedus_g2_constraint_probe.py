"""G2a validation probe: does constrained decoding remove the JSON confound?

Opt-in, LOCAL, $0 -- talks only to a local Ollama server; no API-backed model
is reachable from here. Produces the live G2a gate metrics, denominated.

**Part A -- controlled replay (structural fidelity).** Replays real teacher-turn
prompts from the G1 SFT corpus through each model on IDENTICAL prompts,
UNCONSTRAINED and CONSTRAINED (the per-phase schema from
:mod:`foedus.agents.llm.schema`). For each reply it reports both:

* ``json_ok`` -- the lenient extractor the parser uses
  (:func:`extract_json_with_recovery`) recovered *some* dict. This stays high
  even for the untrained base (recovery is forgiving), which is exactly why it
  is NOT the structural-fidelity metric.
* ``schema_ok`` -- that recovered dict is a *full, valid decision* (validates
  against the phase schema). This is the real structural-fidelity signal:
  the untrained base rarely emits a valid decision unconstrained; constrained,
  it (structurally) always does.

**Part B -- real games, G1-comparable fallback + decomposition.** Runs short
real games (a phase-aware wrapper picks the negotiate/orders schema per call) so
the parser legality-gates against a real board, then reads the decision log --
the SAME ``fell_back`` signal G1 reported as ``parse_fail_count / n_decisions``
(base 234/456=51.3%, trained 121/470=25.7%). Runs BOTH conditions per model and
DECOMPOSES the total fallback into:

* ``structural`` fallback = the extracted dict is not a schema-valid decision
  (the JSON confound). Constrained decoding should drive this to ~0.
* ``semantic`` fallback = schema-valid decision, yet the parser still fell back
  because an order/intent/pact was geometrically ILLEGAL and coerced to Hold.
  This is *residual illegality* -- schema-valid but semantically-illegal -- the
  part constrained decoding does NOT fix, reported per model as a distinct rate.

Everything is coverage-guarded (:mod:`foedus.eval._coverage`) and prints its
denominators; a probe that silently measured nothing must fail, not report a
clean-looking zero.

Run:
    python scripts/foedus_g2_constraint_probe.py \
        --out docs/research/2026-07-11-gym-g2/phase-a/constraint_probe.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import jsonschema

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))
if str(_REPO / "scripts") not in sys.path:
    sys.path.insert(0, str(_REPO / "scripts"))

from foedus.agents.llm import render
from foedus.agents.llm.client import OllamaClient
from foedus.agents.llm.parse import extract_json_with_recovery
from foedus.agents.llm.schema import (
    negotiation_decision_schema,
    orders_decision_schema,
    schema_for_phase,
)
from foedus.eval._coverage import assert_coverage

CORPUS = _REPO / "docs/research/2026-07-10-gym-g1/phase-a/sft_g1.jsonl"
BASE_MODEL = "foedus-base-v1"
ENTRANT_MODEL = "foedus-entrant-v1"

_NEG_SCHEMA = negotiation_decision_schema()
_ORD_SCHEMA = orders_decision_schema()
_SCHEMA_BY_PHASE = {"negotiate": _NEG_SCHEMA, "orders": _ORD_SCHEMA}


def _phase_of_system(system: str) -> str | None:
    """Classify a system prompt into the decision phase, or None (self-note)."""
    if system == render.NEGOTIATION_SYSTEM_PROMPT:
        return "negotiate"
    if system == render.ORDERS_SYSTEM_PROMPT:
        return "orders"
    return None


def _decision_ok(raw: str, schema: dict) -> bool:
    """Does the raw output yield a *schema-valid full decision* via the parser's
    own extractor? This mirrors what parse.py actually consumes."""
    data, _ = extract_json_with_recovery(raw)
    if not isinstance(data, dict):
        return False
    try:
        jsonschema.validate(data, schema)
        return True
    except jsonschema.ValidationError:
        return False


def _json_ok(raw: str) -> bool:
    data, _ = extract_json_with_recovery(raw)
    return isinstance(data, dict)


class _PhaseConstrainedClient:
    """Probe-only wrapper: dispatches each call to the per-phase schema via the
    new per-call ``format`` param of :class:`OllamaClient`. This exercises the
    G2a capability end-to-end; the G2b eval wires the same idea. A prompt that
    is neither decision phase (the campaign self-note) is left unconstrained --
    it must stay free text."""

    def __init__(self, inner: OllamaClient) -> None:
        self._inner = inner

    def complete(self, system: str, user: str) -> str:
        phase = _phase_of_system(system)
        fmt = schema_for_phase(phase) if phase is not None else None
        return self._inner.complete(system, user, format=fmt)


# --------------------------------------------------------------------------
# Part A -- controlled replay over identical corpus prompts
# --------------------------------------------------------------------------

def _load_prompts(n_per_phase: int) -> dict[str, list[tuple[str, str]]]:
    out: dict[str, list[tuple[str, str]]] = {"negotiate": [], "orders": []}
    with CORPUS.open() as f:
        for line in f:
            d = json.loads(line)
            msgs = d["messages"]
            system, user = msgs[0]["content"], msgs[1]["content"]
            phase = _phase_of_system(system)
            if phase is None:
                continue
            if len(out[phase]) < n_per_phase:
                out[phase].append((system, user))
            if all(len(v) >= n_per_phase for v in out.values()):
                break
    return out


def part_a_structural(models: dict[str, str], n_per_phase: int,
                      host: str, timeout: float) -> dict:
    prompts = _load_prompts(n_per_phase)
    for phase, ps in prompts.items():
        assert_coverage(len(ps), n_per_phase, f"partA prompts[{phase}]", 1.0)

    results: dict = {}
    for arm, model in models.items():
        client = OllamaClient(model=model, host=host, timeout=timeout)
        results[arm] = {}
        for cond in ("unconstrained", "constrained"):
            cond_out: dict = {}
            for phase, ps in prompts.items():
                schema = _SCHEMA_BY_PHASE[phase]
                json_ok = decision_ok = 0
                for system, user in ps:
                    fmt = schema if cond == "constrained" else None
                    raw = client.complete(system, user, format=fmt)
                    json_ok += _json_ok(raw)
                    decision_ok += _decision_ok(raw, schema)
                n = len(ps)
                cond_out[phase] = {
                    "n": n,
                    "json_ok": json_ok,
                    "decision_valid": decision_ok,
                    "decision_valid_rate": decision_ok / n,
                }
                print(f"[A] {arm:8s} {cond:13s} {phase:9s}: "
                      f"json_ok {json_ok}/{n}  "
                      f"decision_valid {decision_ok}/{n} "
                      f"({decision_ok / n:.1%})", flush=True)
            tot = sum(v["n"] for v in cond_out.values())
            dok = sum(v["decision_valid"] for v in cond_out.values())
            cond_out["_all"] = {
                "n": tot, "decision_valid": dok,
                "decision_valid_rate": dok / tot,
            }
            results[arm][cond] = cond_out
    return results


# --------------------------------------------------------------------------
# Part B -- residual illegality from short real games, both conditions
# --------------------------------------------------------------------------

def _count_orders_emitted(raw: str) -> int:
    data, _ = extract_json_with_recovery(raw)
    if isinstance(data, dict) and isinstance(data.get("orders"), dict):
        return len(data["orders"])
    return 0


def _make_factory(model: str, constrained: bool, host: str, timeout: float):
    from foedus.agents.llm.diplomat import LLMDiplomat

    def factory():
        base = OllamaClient(model=model, host=host, timeout=timeout)
        client = _PhaseConstrainedClient(base) if constrained else base
        return LLMDiplomat(client=client, recip_ledger=False, campaign=False)

    return factory


def _run_condition(arm: str, model: str, constrained: bool, n_games: int,
                   max_turns: int, host: str, timeout: float) -> dict:
    import foedus_llm_diplomat_run as harness

    factory = _make_factory(model, constrained, host, timeout)
    # NB structural_invalid (schema-invalid raw) and total_parse_fallback
    # (parse.py fell_back) are DISTINCT lenses that do NOT partition: parse.py's
    # leniency can salvage a schema-invalid dict without falling back, and a
    # schema-valid dict can still fall back on an illegal move. So they are
    # reported side by side, not summed. Residual illegality is measured over
    # the schema-VALID denominator (decision level) and, more crisply, per
    # emitted order (orders phase).
    agg = {
        "n_decisions": 0,
        "decision_valid": 0,          # raw is a schema-valid full decision
        "structural_invalid": 0,      # raw is NOT a schema-valid decision (confound)
        "total_parse_fallback": 0,    # parse.py fell_back -- the G1 parse_fail metric
        "residual_illegal_decisions": 0,  # schema-VALID yet parser fell back (semantic)
        "orders_emitted": 0,
        "orders_illegal_coerced": 0,
        "by_phase": {"negotiate": 0, "orders": 0},
    }
    for g in range(n_games):
        _sweep, _tel, final_state, agent = harness.run_one_llm_game(
            game_id=g, seed=1000 + g, llm_seat=0,
            heuristic_names=["GreedyHold", "GreedyHold", "GreedyHold"],
            max_turns=max_turns,
            llm_agent_factory=factory,
        )
        assert final_state.is_terminal()
        for rec in agent.decision_log:
            phase = rec["phase"]
            raw = rec["raw_response"]
            schema = _SCHEMA_BY_PHASE[phase]
            decision_valid = _decision_ok(raw, schema)
            fell_back = bool(rec["fell_back"])
            agg["n_decisions"] += 1
            agg["by_phase"][phase] += 1
            if decision_valid:
                agg["decision_valid"] += 1
                if fell_back:
                    agg["residual_illegal_decisions"] += 1
            else:
                agg["structural_invalid"] += 1
            if fell_back:
                agg["total_parse_fallback"] += 1
            if phase == "orders":
                agg["orders_emitted"] += _count_orders_emitted(raw)
                agg["orders_illegal_coerced"] += rec["n_coerced"]
    n = agg["n_decisions"]
    assert_coverage(n, n or 1, f"partB {arm}/{'constr' if constrained else 'uncon'}", 1.0)
    dv = agg["decision_valid"]
    oe = agg["orders_emitted"]
    agg["structural_invalid_rate"] = agg["structural_invalid"] / n
    agg["total_parse_fallback_rate"] = agg["total_parse_fallback"] / n
    # residual illegality among structurally-VALID decisions (its natural denom)
    agg["residual_illegal_decision_rate"] = (
        agg["residual_illegal_decisions"] / dv if dv else 0.0)
    agg["order_illegality_rate"] = agg["orders_illegal_coerced"] / oe if oe else 0.0
    print(f"[B] {arm:8s} {'constrained' if constrained else 'unconstrained':13s}: "
          f"n {n}  parse_fb {agg['total_parse_fallback']}/{n} "
          f"({agg['total_parse_fallback_rate']:.1%})  "
          f"struct_invalid {agg['structural_invalid']}/{n} "
          f"({agg['structural_invalid_rate']:.1%})  "
          f"residual_illegal(valid) {agg['residual_illegal_decisions']}/{dv} "
          f"({agg['residual_illegal_decision_rate']:.1%})  "
          f"order_illegal {agg['orders_illegal_coerced']}/{oe} "
          f"({agg['order_illegality_rate']:.1%})", flush=True)
    return agg


def part_b_games(models: dict[str, str], n_games: int, max_turns: int,
                 host: str, timeout: float) -> dict:
    results: dict = {}
    for arm, model in models.items():
        results[arm] = {
            "unconstrained": _run_condition(arm, model, False, n_games,
                                            max_turns, host, timeout),
            "constrained": _run_condition(arm, model, True, n_games,
                                          max_turns, host, timeout),
        }
    return results


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n-structural", type=int, default=40,
                    help="corpus prompts per phase for Part A (default 40)")
    ap.add_argument("--n-games", type=int, default=3,
                    help="short games per model per condition for Part B (default 3)")
    ap.add_argument("--max-turns", type=int, default=8,
                    help="turns per Part B game (default 8)")
    ap.add_argument("--base-model", default=BASE_MODEL)
    ap.add_argument("--entrant-model", default=ENTRANT_MODEL)
    ap.add_argument("--host", default="http://localhost:11434")
    ap.add_argument("--timeout", type=float, default=180.0)
    ap.add_argument("--out", type=Path, default=None,
                    help="write the full JSON report here")
    ap.add_argument("--skip-games", action="store_true",
                    help="Part A only (skip the real-game residual probe)")
    args = ap.parse_args(argv)

    models = {"base": args.base_model, "entrant": args.entrant_model}

    print("=== Part A: controlled replay (structural fidelity) ===", flush=True)
    part_a = part_a_structural(models, args.n_structural, args.host, args.timeout)

    part_b = None
    if not args.skip_games:
        print("\n=== Part B: real games -- fallback decomposition ===", flush=True)
        part_b = part_b_games(models, args.n_games, args.max_turns,
                              args.host, args.timeout)

    report = {
        "config": {
            "n_structural_per_phase": args.n_structural,
            "n_games": args.n_games,
            "max_turns": args.max_turns,
            "models": models,
            "host": args.host,
        },
        "part_a_controlled_replay": part_a,
        "part_b_fallback_decomposition": part_b,
    }
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2) + "\n")
        print(f"\nwrote {args.out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
