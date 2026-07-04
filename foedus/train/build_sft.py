"""Build an SFT dataset from the arena's per-seat decision logs.

The LLM arena harness writes one JSONL file per (game, seat), named
``decisions_game{N}_seat{M}.jsonl``. Each line is one decision record::

    {
      "turn": 3, "phase": "negotiate", "player": 0,
      "prompt": {"system": "...", "user": "..."},
      "raw_response": "<the model's raw text>",
      "parsed": "<repr of the parsed decision>",
      "fell_back": false, "n_coerced": 0
    }

This module distils those into SFT *chat* examples::

    {"messages": [
        {"role": "system", "content": <prompt.system>},
        {"role": "user", "content": <prompt.user>},
        {"role": "assistant", "content": <raw_response, verbatim>}
    ]}

Only **valid teacher decisions** are kept:

* ``fell_back`` is falsey (the harness didn't fall back to a default order), AND
* ``raw_response`` is *real JSON* — not a ``<client error ...>`` timeout
  sentinel, not empty, and not free-form reasoning prose. (In the archived
  corpus ~13% of non-fell_back rows were prose narration with no parseable JSON;
  the brief requires we drop those.)

Identical ``(system, user, assistant)`` triples are de-duplicated. With
``--winners-only`` (default OFF) only decisions from seats that won or tied-top
their game are kept, read from the sibling ``sweep.jsonl`` (``winners`` field).

CLI::

    python -m foedus.train.build_sft RUN_DIR [RUN_DIR ...] --out out.jsonl \
        [--winners-only]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

SENTINEL_PREFIX = "<client error"
_DECISION_FILE_RE = re.compile(r"decisions_game(\d+)_seat(\d+)\.jsonl$")
_FENCE_RE = re.compile(r"^```[a-zA-Z0-9_-]*\n(.*)\n```$", re.DOTALL)


# --------------------------------------------------------------------------- #
# validity
# --------------------------------------------------------------------------- #
def _strip_code_fence(text: str) -> str:
    """Return the inside of a ```...``` fenced block, or ``text`` unchanged."""
    m = _FENCE_RE.match(text.strip())
    return m.group(1) if m else text


def _is_real_json(raw_response: object) -> bool:
    """True iff ``raw_response`` is a non-empty string that parses as JSON.

    Tolerates a single Markdown code fence around the JSON. Rejects the
    ``<client error ...>`` sentinel, empty strings, and reasoning prose.
    """
    if not isinstance(raw_response, str):
        return False
    stripped = raw_response.strip()
    if not stripped or stripped.startswith(SENTINEL_PREFIX):
        return False
    candidate = _strip_code_fence(stripped)
    try:
        json.loads(candidate)
    except (ValueError, TypeError):
        return False
    return True


def _has_prompt(record: dict) -> bool:
    prompt = record.get("prompt")
    return (
        isinstance(prompt, dict)
        and isinstance(prompt.get("system"), str)
        and isinstance(prompt.get("user"), str)
    )


def is_valid_teacher(record: dict) -> bool:
    """A genuine teacher decision: not ``fell_back`` and ``raw_response`` is real JSON."""
    if record.get("fell_back"):
        return False
    return _is_real_json(record.get("raw_response"))


# --------------------------------------------------------------------------- #
# transforms
# --------------------------------------------------------------------------- #
def to_chat_example(record: dict) -> dict:
    """Build a ``{"messages": [...]}`` chat example from a decision record.

    The assistant turn is the teacher's ``raw_response`` **verbatim**.
    """
    prompt = record["prompt"]
    return {
        "messages": [
            {"role": "system", "content": prompt["system"]},
            {"role": "user", "content": prompt["user"]},
            {"role": "assistant", "content": record["raw_response"]},
        ]
    }


def _dedup_key(record: dict) -> tuple[str, str, str]:
    prompt = record["prompt"]
    return (prompt["system"], prompt["user"], record["raw_response"])


def parse_game_seat(path) -> tuple[int, int]:
    """Extract ``(game_id, seat)`` from a ``decisions_game{N}_seat{M}.jsonl`` path."""
    m = _DECISION_FILE_RE.search(Path(path).name)
    if not m:
        raise ValueError(f"not a decision-log filename: {path}")
    return int(m.group(1)), int(m.group(2))


def load_winners(directory) -> dict[int, set[int]]:
    """Map ``game_id -> set(winning seats)`` from ``sweep.jsonl`` in ``directory``.

    Returns ``{}`` when no ``sweep.jsonl`` is present. ``winners`` already
    encodes ties and détente shared wins (a list of seat indices).
    """
    sweep = Path(directory) / "sweep.jsonl"
    if not sweep.exists():
        return {}
    winners: dict[int, set[int]] = {}
    for line in sweep.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        winners[int(row["game_id"])] = {int(s) for s in row.get("winners", [])}
    return winners


# --------------------------------------------------------------------------- #
# build
# --------------------------------------------------------------------------- #
@dataclass
class BuildStats:
    files: int = 0
    records: int = 0
    fell_back: int = 0
    not_json: int = 0
    malformed_prompt: int = 0
    winners_filtered: int = 0
    duplicates: int = 0
    written: int = 0

    def summary(self) -> str:
        return (
            f"files={self.files} records={self.records} "
            f"written={self.written} duplicates={self.duplicates} | "
            f"dropped: fell_back={self.fell_back} not_json={self.not_json} "
            f"malformed_prompt={self.malformed_prompt} "
            f"winners_filtered={self.winners_filtered}"
        )


def _iter_decision_files(run_dirs: Iterable) -> Iterable[Path]:
    for run_dir in run_dirs:
        for path in sorted(Path(run_dir).rglob("decisions_game*_seat*.jsonl")):
            yield path


def build_dataset(run_dirs, winners_only: bool = False):
    """Return ``(examples, BuildStats)`` for all decision logs under ``run_dirs``.

    ``run_dirs`` is one or more directories searched recursively. Identical
    ``(system, user, response)`` pairs are de-duplicated across all inputs.
    """
    stats = BuildStats()
    seen: set[tuple[str, str, str]] = set()
    examples: list[dict] = []
    winners_cache: dict[Path, dict[int, set[int]]] = {}

    for path in _iter_decision_files(run_dirs):
        stats.files += 1
        game_id, seat = parse_game_seat(path)
        if winners_only:
            if path.parent not in winners_cache:
                winners_cache[path.parent] = load_winners(path.parent)
            game_winners = winners_cache[path.parent]
            if not game_winners:
                sys.stderr.write(
                    f"[build_sft] warning: --winners-only but no sweep.jsonl in "
                    f"{path.parent}; dropping its decisions\n"
                )

        for line in path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            stats.records += 1

            if record.get("fell_back"):
                stats.fell_back += 1
                continue
            if not _is_real_json(record.get("raw_response")):
                stats.not_json += 1
                continue
            if not _has_prompt(record):
                stats.malformed_prompt += 1
                continue
            if winners_only and seat not in winners_cache[path.parent].get(game_id, set()):
                stats.winners_filtered += 1
                continue

            key = _dedup_key(record)
            if key in seen:
                stats.duplicates += 1
                continue
            seen.add(key)
            examples.append(to_chat_example(record))
            stats.written += 1

    return examples, stats


def write_jsonl(examples: Iterable[dict], out_path) -> None:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for ex in examples:
            fh.write(json.dumps(ex, ensure_ascii=False) + "\n")


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Distil arena decision logs into an SFT chat dataset."
    )
    parser.add_argument(
        "run_dirs",
        nargs="+",
        help="One or more run directories (searched recursively for "
        "decisions_game*_seat*.jsonl).",
    )
    parser.add_argument("--out", required=True, help="Output SFT JSONL path.")
    parser.add_argument(
        "--winners-only",
        action="store_true",
        help="Keep only decisions from seats that won or tied-top their game "
        "(read from sibling sweep.jsonl). Default OFF.",
    )
    args = parser.parse_args(argv)

    examples, stats = build_dataset(args.run_dirs, winners_only=args.winners_only)
    write_jsonl(examples, args.out)
    sys.stderr.write(f"[build_sft] {stats.summary()}\n")
    sys.stderr.write(f"[build_sft] wrote {stats.written} examples -> {args.out}\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
