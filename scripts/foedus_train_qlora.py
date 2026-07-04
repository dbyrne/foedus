"""QLoRA fine-tune a small instruct model on the foedus SFT dataset.

v0 goal: **prove the training loop runs end-to-end on the battlestation**
(RTX 3080 Ti, 12GB) — not to chase eval loss. Run with ``--smoke`` for a few
steps on a tiny subset that writes a LoRA adapter and logs VRAM headroom. The
harness is config-driven and resumable, so the follow-up *full* run is a flag
change (drop ``--smoke``, set ``--epochs``/``--max-steps``), not a code change.

Default base is ``Qwen/Qwen2.5-3B-Instruct`` (3B QLoRA is comfortable on 12GB);
``--base-model`` makes it configurable. Uses 4-bit NF4 (bitsandbytes) + a small
LoRA (peft) + trl's SFTTrainer over the conversational ``messages`` dataset.

Example::

    # smoke: prove the loop (a handful of steps on 32 examples)
    python scripts/foedus_train_qlora.py --sft-path data/sft.jsonl --smoke \
        --out-dir runs/qlora_entrant_v0

    # follow-up full run (same script, flags only)
    python scripts/foedus_train_qlora.py --sft-path data/sft.jsonl --epochs 3 \
        --out-dir runs/qlora_entrant_v1

Heavy ML deps (torch/transformers/peft/bitsandbytes/trl) live behind the
``[train]`` optional extra and are imported lazily inside ``train()`` so that
``--help`` and the unit tests need no GPU / no ML stack.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

# LoRA target modules for Qwen2 / Llama-style attention+MLP projections.
QWEN_TARGET_MODULES = [
    "q_proj",
    "k_proj",
    "v_proj",
    "o_proj",
    "gate_proj",
    "up_proj",
    "down_proj",
]

# --smoke convenience defaults (only applied when the flag is set and the user
# did not pass an explicit value).
SMOKE_MAX_STEPS = 8
SMOKE_SUBSET = 32


@dataclass
class TrainConfig:
    sft_path: str
    base_model: str = "Qwen/Qwen2.5-3B-Instruct"
    out_dir: str = "runs/qlora_entrant_v0"
    lora_r: int = 16
    lora_alpha: int = 32
    lora_dropout: float = 0.05
    load_in_4bit: bool = True
    max_length: int = 2048
    per_device_batch_size: int = 1
    grad_accum: int = 8
    learning_rate: float = 2e-4
    num_train_epochs: float = 1.0
    max_steps: int | None = None
    subset: int | None = None
    seed: int = 0
    logging_steps: int = 1
    save_steps: int = 0  # 0 -> save only at the end
    resume_from_checkpoint: str | None = None
    smoke: bool = False
    target_modules: list[str] = field(default_factory=lambda: list(QWEN_TARGET_MODULES))


def parse_args(argv: list[str] | None = None) -> TrainConfig:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--sft-path", required=True, help="SFT JSONL from build_sft.")
    p.add_argument("--base-model", default="Qwen/Qwen2.5-3B-Instruct")
    p.add_argument("--out-dir", default="runs/qlora_entrant_v0")
    p.add_argument("--lora-r", type=int, default=16)
    p.add_argument("--lora-alpha", type=int, default=32)
    p.add_argument("--lora-dropout", type=float, default=0.05)
    p.add_argument(
        "--no-4bit",
        dest="load_in_4bit",
        action="store_false",
        help="Disable 4-bit NF4 quantization (needs much more VRAM).",
    )
    p.add_argument("--max-length", type=int, default=2048)
    p.add_argument("--batch-size", type=int, default=1)
    p.add_argument("--grad-accum", type=int, default=8)
    p.add_argument("--lr", type=float, default=2e-4)
    p.add_argument("--epochs", type=float, default=1.0)
    p.add_argument("--max-steps", type=int, default=None)
    p.add_argument(
        "--subset", type=int, default=None, help="Train on only the first N examples."
    )
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--logging-steps", type=int, default=1)
    p.add_argument(
        "--save-steps",
        type=int,
        default=0,
        help="Checkpoint every N steps (0 = save only at the end).",
    )
    p.add_argument("--resume", dest="resume_from_checkpoint", default=None)
    p.add_argument(
        "--smoke",
        action="store_true",
        help=f"Smoke run: {SMOKE_MAX_STEPS} steps on {SMOKE_SUBSET} examples "
        "unless --max-steps/--subset given.",
    )
    a = p.parse_args(argv)

    max_steps = a.max_steps
    subset = a.subset
    if a.smoke:
        if max_steps is None:
            max_steps = SMOKE_MAX_STEPS
        if subset is None:
            subset = SMOKE_SUBSET

    return TrainConfig(
        sft_path=a.sft_path,
        base_model=a.base_model,
        out_dir=a.out_dir,
        lora_r=a.lora_r,
        lora_alpha=a.lora_alpha,
        lora_dropout=a.lora_dropout,
        load_in_4bit=a.load_in_4bit,
        max_length=a.max_length,
        per_device_batch_size=a.batch_size,
        grad_accum=a.grad_accum,
        learning_rate=a.lr,
        num_train_epochs=a.epochs,
        max_steps=max_steps,
        subset=subset,
        seed=a.seed,
        logging_steps=a.logging_steps,
        save_steps=a.save_steps,
        resume_from_checkpoint=a.resume_from_checkpoint,
        smoke=a.smoke,
    )


def load_sft_records(path, subset: int | None = None) -> list[dict]:
    """Read the SFT JSONL into a list of ``{"messages": [...]}`` dicts.

    ``subset`` (if given) keeps only the first N non-blank lines.
    """
    records: list[dict] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        records.append(json.loads(line))
        if subset is not None and len(records) >= subset:
            break
    return records


def format_vram_report(free_bytes: int, total_bytes: int, peak_alloc_bytes: int) -> str:
    gb = 1e9
    peak = peak_alloc_bytes / gb
    free = free_bytes / gb
    total = total_bytes / gb
    return (
        f"VRAM: peak_alloc={peak:.1f}GB, free_now={free:.1f}GB / total={total:.1f}GB "
        f"(headroom vs total={total - peak:.1f}GB)"
    )


def train(cfg: TrainConfig) -> dict:  # pragma: no cover - exercised by the smoke run
    """Run QLoRA fine-tuning; write a LoRA adapter + train_summary.json to out_dir."""
    import torch
    from datasets import Dataset
    from peft import LoraConfig
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        BitsAndBytesConfig,
        set_seed,
    )
    from trl import SFTConfig, SFTTrainer

    set_seed(cfg.seed)

    records = load_sft_records(cfg.sft_path, subset=cfg.subset)
    if not records:
        raise SystemExit(f"[qlora] no SFT records loaded from {cfg.sft_path}")
    dataset = Dataset.from_list(records)
    print(f"[qlora] {len(records)} training examples from {cfg.sft_path}", flush=True)

    tokenizer = AutoTokenizer.from_pretrained(cfg.base_model)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    compute_dtype = torch.bfloat16
    quant_config = None
    if cfg.load_in_4bit:
        quant_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=compute_dtype,
            bnb_4bit_use_double_quant=True,
        )

    print(f"[qlora] loading base model {cfg.base_model} (4bit={cfg.load_in_4bit})...", flush=True)
    model = AutoModelForCausalLM.from_pretrained(
        cfg.base_model,
        quantization_config=quant_config,
        dtype=compute_dtype,
        device_map={"": 0},
    )
    model.config.use_cache = False

    lora_config = LoraConfig(
        r=cfg.lora_r,
        lora_alpha=cfg.lora_alpha,
        lora_dropout=cfg.lora_dropout,
        target_modules=cfg.target_modules,
        bias="none",
        task_type="CAUSAL_LM",
    )

    sft_args = SFTConfig(
        output_dir=cfg.out_dir,
        per_device_train_batch_size=cfg.per_device_batch_size,
        gradient_accumulation_steps=cfg.grad_accum,
        learning_rate=cfg.learning_rate,
        num_train_epochs=cfg.num_train_epochs,
        max_steps=cfg.max_steps if cfg.max_steps is not None else -1,
        logging_steps=cfg.logging_steps,
        save_strategy="no" if cfg.save_steps == 0 else "steps",
        save_steps=cfg.save_steps or 500,
        bf16=True,
        max_length=cfg.max_length,
        packing=False,
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        optim="paged_adamw_8bit",
        report_to="none",
        seed=cfg.seed,
        lr_scheduler_type="cosine",
    )

    trainer = SFTTrainer(
        model=model,
        args=sft_args,
        train_dataset=dataset,
        processing_class=tokenizer,
        peft_config=lora_config,
    )

    if torch.cuda.is_available():
        torch.cuda.reset_peak_memory_stats()

    result = trainer.train(resume_from_checkpoint=cfg.resume_from_checkpoint)
    trainer.save_model(cfg.out_dir)  # writes the LoRA adapter

    vram = ""
    if torch.cuda.is_available():
        free, total = torch.cuda.mem_get_info()
        peak = torch.cuda.max_memory_allocated()
        vram = format_vram_report(free, total, peak)
        print("[qlora] " + vram, flush=True)

    summary = {
        "base_model": cfg.base_model,
        "sft_path": cfg.sft_path,
        "n_examples": len(records),
        "smoke": cfg.smoke,
        "metrics": dict(result.metrics),
        "vram": vram,
        "config": asdict(cfg),
    }
    out = Path(cfg.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "train_summary.json").write_text(json.dumps(summary, indent=2))
    print(f"[qlora] adapter + train_summary.json written to {cfg.out_dir}", flush=True)
    return summary


def main(argv: list[str] | None = None) -> int:
    cfg = parse_args(argv)
    train(cfg)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
