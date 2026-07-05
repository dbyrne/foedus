"""Tests for the pure, CPU-only parts of the QLoRA training harness.

The GPU training loop itself is proven by an actual smoke run (see the design
doc); here we TDD the config parsing, SFT-record loading, and VRAM reporting so
the harness is config-driven and resumable — the follow-up full run is a flag
change, not a code change. Heavy ML imports (torch/transformers/peft/trl) stay
lazy inside ``train()`` so these tests need no GPU.
"""
from __future__ import annotations

import json

from scripts.foedus_train_qlora import (
    TrainConfig,
    format_vram_report,
    load_sft_records,
    parse_args,
)


def _write_sft(path, n):
    with open(path, "w") as fh:
        for i in range(n):
            ex = {
                "messages": [
                    {"role": "system", "content": "S"},
                    {"role": "user", "content": f"U{i}"},
                    {"role": "assistant", "content": "{}"},
                ]
            }
            fh.write(json.dumps(ex) + "\n")


# --- config -----------------------------------------------------------------


def test_parse_args_defaults():
    cfg = parse_args(["--sft-path", "data.jsonl"])
    assert isinstance(cfg, TrainConfig)
    assert cfg.base_model == "Qwen/Qwen2.5-3B-Instruct"
    assert cfg.sft_path == "data.jsonl"
    assert cfg.lora_r == 16
    assert cfg.load_in_4bit is True
    assert cfg.smoke is False
    # not smoke, nothing forced
    assert cfg.max_steps is None
    assert cfg.subset is None


def test_smoke_flag_sets_small_run():
    cfg = parse_args(["--sft-path", "data.jsonl", "--smoke"])
    assert cfg.smoke is True
    assert cfg.max_steps == 8
    assert cfg.subset == 32


def test_explicit_values_override_smoke_defaults():
    cfg = parse_args(
        ["--sft-path", "d", "--smoke", "--max-steps", "3", "--subset", "4"]
    )
    assert cfg.max_steps == 3
    assert cfg.subset == 4


def test_base_model_is_configurable():
    cfg = parse_args(["--sft-path", "d", "--base-model", "Qwen/Qwen2.5-7B-Instruct"])
    assert cfg.base_model == "Qwen/Qwen2.5-7B-Instruct"


def test_resume_and_output_dir_are_plumbed():
    cfg = parse_args(
        ["--sft-path", "d", "--out-dir", "runs/foo", "--resume", "runs/foo/checkpoint-5"]
    )
    assert cfg.out_dir == "runs/foo"
    assert cfg.resume_from_checkpoint == "runs/foo/checkpoint-5"


# --- dataset loading --------------------------------------------------------


def test_load_sft_records_reads_all(tmp_path):
    p = tmp_path / "d.jsonl"
    _write_sft(p, 5)
    recs = load_sft_records(str(p))
    assert len(recs) == 5
    assert recs[0]["messages"][0]["role"] == "system"


def test_load_sft_records_subset_limits(tmp_path):
    p = tmp_path / "d.jsonl"
    _write_sft(p, 5)
    recs = load_sft_records(str(p), subset=2)
    assert len(recs) == 2
    assert recs[1]["messages"][1]["content"] == "U1"


def test_load_sft_records_skips_blank_lines(tmp_path):
    p = tmp_path / "d.jsonl"
    _write_sft(p, 2)
    with open(p, "a") as fh:
        fh.write("\n   \n")
    assert len(load_sft_records(str(p))) == 2


# --- vram report ------------------------------------------------------------


def test_format_vram_report_mentions_gb_values():
    s = format_vram_report(free_bytes=2_000_000_000, total_bytes=12_000_000_000,
                           peak_alloc_bytes=6_500_000_000)
    assert "6.5" in s  # peak allocation in GB
    assert "12" in s   # total
    assert "GB" in s
