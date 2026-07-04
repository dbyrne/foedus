# Gym pipeline v0 — prove the distillation → QLoRA → serve → play loop

**Date:** 2026-07-04
**Status:** v0 shipped — the training-gym loop is **proven end-to-end** on the battlestation.
**Scope:** v0 proves the loop *runs*, not that it produces a strong entrant. A full
training run + a Ruleset-v1 evaluation of the trained entrant is the explicit
follow-up (see [Follow-up](#follow-up-plan)).

## TL;DR

Sonnet is the demonstrated arena "teacher". This work turns Sonnet's play into an
SFT dataset, QLoRA-fine-tunes a small local model on the RTX 3080 Ti, serves it
through the *existing* `OllamaClient`, and plays a foedus game with it — every stage
run for real:

| Stage | Artifact | Evidence |
|---|---|---|
| **1. Distill** | `foedus/train/build_sft.py` | **252** unique valid Sonnet pairs from the archived corpus (77 winners-only) |
| **2. Train** | `scripts/foedus_train_qlora.py` | QLoRA smoke run: adapter written, **peak VRAM 4.5 GB / 12.9 GB** |
| **3. Serve** | `scripts/foedus_serve_ollama.py` | merge → GGUF → `ollama create foedus-entrant-v0` (q4_K_M) |
| **4. Play** | *existing* `OllamaClient` + `foedus_llm_diplomat_run.py` | 1 game, seat-0 = trained model, **parse-fail 0/6** |

Raw artifacts: [`2026-07-04-gym-pipeline-v0-evidence/`](./2026-07-04-gym-pipeline-v0-evidence/).

## Preflight findings (the gate)

The gating question was: *is a full QLoRA loop feasible in this WSL2 env, or do we
punt to cloud?* **It is feasible.** Nothing here required fighting CUDA.

### GPU / driver
- **NVIDIA GeForce RTX 3080 Ti**, 12.88 GB. Driver 591.86, CUDA 13.1, `/dev/dxg` present.
- Visible from WSL2 via `/usr/lib/wsl/lib/nvidia-smi`. ~11.6 GB free at rest (Xwayland holds ~3.5 GB).

### ML stack
- **The project's default `.venv` is Python 3.14, which has no torch/bitsandbytes wheels.**
  So the `[train]` extra lives in a **dedicated Python 3.12 venv** (`~/.venvs/foedus-train`).
  This is why `[train]` is opt-in and documented as requiring Python ≤ 3.12.
- Installed + **verified working** (exact versions used):

  | package | version | | package | version |
  |---|---|---|---|---|
  | torch | 2.12.1+cu130 | | trl | 1.7.1 |
  | transformers | 5.13.0 | | accelerate | 1.14.0 |
  | peft | 0.19.1 | | datasets | 5.0.0 |
  | bitsandbytes | 0.49.2 | | numpy | 2.2.6 |

- **bitsandbytes on WSL2 CUDA is the historically finicky bit — it works.** A 4-bit
  `Linear4bit` forward pass ran on `cuda:0` during preflight, and the full QLoRA smoke
  train ran clean. `torch.cuda.is_available()` → `True`, device correctly identified.

### Serve path (decided)
Ollama runs as the **Windows** binary serving `http://localhost:11434` (the WSL side
cannot exec the `.exe`), already holding `qwen2.5:*`, `gemma3:*`, etc. We therefore
drive it entirely over **REST** — no CLI needed. The chosen path reuses the
finetune-lab prior art (`create_ollama_model_v3.py`) and **honors its banked lesson**:

> Ollama's built-in **safetensors** converter corrupts Qwen2.5-3B tied embeddings
> (garbage logits + sampler crash). Convert with **llama.cpp** first, hand Ollama a
> finished GGUF, and let it only quantize.

So: **merge LoRA → llama.cpp `convert_hf_to_gguf.py` (f16 GGUF) → upload blob +
`POST /api/create` (quantize q4_K_M) → play via the existing `OllamaClient`.**
`llama.cpp` is already present at `~/finetune-lab/llama.cpp`; Qwen2.5-3B-Instruct is
already in the HF cache (no 6 GB download).

## The pipeline

### Part 1 — SFT dataset builder (`foedus/train/build_sft.py`)

Reads the arena's per-seat decision logs (`decisions_game{N}_seat{M}.jsonl`) and emits
SFT **chat** examples — `{"messages": [system, user, assistant]}` where system+user is
the seat prompt and assistant is the teacher's `raw_response` **verbatim**.

Keeps only **valid teacher decisions**:
- `fell_back == False`, **and**
- `raw_response` is **real JSON** — not a `<client error …>` timeout sentinel, not
  empty, not reasoning prose, and not a bare scalar (a decision is always a JSON
  object). (In the corpus, ~13% of non-fell_back rows had no parseable JSON — a mix
  of timeout sentinels and prose narration — the brief requires dropping those.)

Identical `(system, user, response)` triples are de-duplicated. `--winners-only`
(default **OFF**) keeps only seats that won/tied-top their game (from sibling
`sweep.jsonl` `winners`). Stdlib-only, so it runs in any venv (incl. the 3.14 default).

**Proven on the archived corpus** (`#37` armA + `#38` armB) — see
[`dataset_stats.json`](./2026-07-04-gym-pipeline-v0-evidence/dataset_stats.json):

```
files=24 records=380 written=252 duplicates=1
dropped: fell_back=88  not_json=39  (winners-only → written=77)
```

The builder is dedup-safe: pointing it at the whole `probe_run/` tree (per-seed dirs
*and* the merged dir) collapses the overlap to the same **252** unique pairs.

### Part 2 — QLoRA smoke train (`scripts/foedus_train_qlora.py`)

QLoRA (4-bit NF4 via bitsandbytes, small LoRA via peft, trl `SFTTrainer` over the
conversational `messages` column) on a configurable base — default
**`Qwen/Qwen2.5-3B-Instruct`** (3B QLoRA is comfortable on 12 GB). Config-driven and
resumable: the follow-up full run is a flag change, not a code change. `--smoke` does a
few steps on a tiny subset, writes the LoRA adapter, and logs VRAM. Heavy ML imports
are lazy, so `--help` / the unit tests need no GPU.

**Smoke run evidence** — see
[`smoke_train_summary.json`](./2026-07-04-gym-pipeline-v0-evidence/smoke_train_summary.json):
8 steps on 32 pairs, `train_runtime` ≈ 56 s, LoRA adapter (`adapter_model.safetensors`,
60 MB) written, and:

```
VRAM: peak_alloc=4.5GB, free_now=6.9GB / total=12.9GB (headroom vs total=8.4GB)
```

### Part 3 — serve + play (`scripts/foedus_serve_ollama.py` + existing infra)

`foedus_serve_ollama.py` merges the adapter into an fp16 base, converts to GGUF via
llama.cpp, uploads the blob and `POST /api/create`s `foedus-entrant-v0` (q4_K_M) over
REST. The LoRA merge uses the `[train]` env; GGUF conversion is shelled to a python
that can run `convert_hf_to_gguf.py` (defaults to the finetune-lab venv, overridable),
reusing the environment already proven for Qwen2.5-3B.

**The trained entrant then plays through the `OllamaClient` that already ships on
`main`** (`foedus/agents/llm/client.py`) — no new backend, no engine changes:

```
python scripts/foedus_llm_diplomat_run.py --num-games 1 --max-turns 3 \
  --num-players 3 --llm-seats 0 --heuristics GreedyHold,TitForTat \
  --backend ollama --model foedus-entrant-v0
```

**Play evidence** — see
[`play_game_evidence.json`](./2026-07-04-gym-pipeline-v0-evidence/play_game_evidence.json):
the game ran to completion and seat-0 (the trained model) emitted **6/6 valid-JSON
decisions, parse-fail 0/6**. It plays *weakly* (mostly `Hold`; final scores `[3, 5, 5]`)
— exactly as expected for an 8-step smoke model. The point is proven: **the trained
artifact enters the arena via existing infra and emits parseable decisions.**

## VRAM feasibility (informs the follow-up)

The smoke run peaked at **4.5 GB allocated** for 3B QLoRA (batch 1, grad-accum 8,
max_length 2048, paged 8-bit optimizer, gradient checkpointing). With **8.4 GB of
headroom**:

- **3B QLoRA:** comfortable — room to grow batch/seq or LoRA rank.
- **7B QLoRA:** **feasible.** 7B 4-bit weights ≈ 4.5–5 GB; with QLoRA + checkpointing +
  paged optimizer the earlier finetune-lab work fits 7B on this card. Expect a tighter
  but workable ~9–11 GB.
- **14B QLoRA:** **borderline / likely not** for *training* on 12 GB (14B 4-bit weights
  alone ≈ 8 GB, before activations/optimizer). Feasible for *inference* (a 14B q4 model
  is already served in ollama here), not recommended for v0-style training. Not attempted.

## Follow-up plan

v0 proves the loop; the follow-up makes a *real* entrant:

1. **Bigger corpus.** Point `build_sft.py` at the parallel **canonical-campaign** run
   (same log format) as it lands — no code change. Consider `--winners-only` and/or
   mixing arms once N is large enough.
2. **Full train.** Drop `--smoke`; set `--epochs 2–3` (or a step budget), keep 3B,
   tune LR/warmup. For a crash-resumable full run also pass `--save-steps N` (the
   v0 default is `0` = save only at the end, so `--resume` needs a checkpointed run).
3. **Quality levers to try:** `assistant_only_loss` (mask the prompt so loss is on the
   decision only — verify the Qwen chat template supports assistant masking first);
   LoRA rank/target-module sweeps; possibly the winners-only subset for higher-quality
   imitation.
4. **Evaluate in Ruleset v1.** Enter `foedus-entrant-v1` on the persistent OpenSkill
   ladder from `docs/design/2026-07-04-ruleset-v1.md` against the base 3B + the
   freerider/heuristic anchors. That eval — *is the distilled entrant better than its
   own base model?* — is the real scientific question v0 deliberately defers.
5. **(Stretch) 7B distill** once the 3B result is characterized, using the headroom above.

## Reproduction

```sh
# 1. training venv (Python <=3.12; the project's 3.14 .venv has no ML wheels)
uv venv --python 3.12 ~/.venvs/foedus-train
uv pip install --python ~/.venvs/foedus-train/bin/python -e '.[train]'

# 2. build the SFT dataset (stdlib-only; runs anywhere)
python -m foedus.train.build_sft <run-dir> [<run-dir> ...] --out data/sft.jsonl

# 3. smoke train (proves the loop) — drop --smoke + set --epochs for the full run
python scripts/foedus_train_qlora.py --sft-path data/sft.jsonl --smoke \
  --out-dir runs/qlora_entrant_v0

# 4. serve to ollama (REST; needs llama.cpp + a convert-capable python)
python scripts/foedus_serve_ollama.py --adapter-dir runs/qlora_entrant_v0 \
  --model-name foedus-entrant-v0

# 5. play one game via the existing OllamaClient
python scripts/foedus_llm_diplomat_run.py --num-games 1 --max-turns 3 \
  --num-players 3 --llm-seats 0 --heuristics GreedyHold,TitForTat \
  --backend ollama --model foedus-entrant-v0
```

## Notes & caveats

- **Surface.** This work is purely additive: `foedus/train/`, `scripts/foedus_train_qlora.py`,
  `scripts/foedus_serve_ollama.py`, tests, docs. **Zero** changes to the engine, rating,
  resolve, presets, or the existing `foedus/agents/llm` + runner (which it reuses as-is).
- **`[train]` is opt-in.** CI and non-training contributors are unaffected — the default
  install is unchanged; `pip install -e .[train]` (Python ≤ 3.12 + a CUDA GPU) is only
  needed to actually train/serve.
- **`torch` CUDA build.** On Linux, `pip install` pulls torch's bundled CUDA build
  automatically (here `2.12.1+cu130`, matching the driver's CUDA 13.1). The `[train]`
  floors are set to the validated versions so the trl 1.7 / transformers 5 APIs the
  harness uses are guaranteed present.
- **v0 LR schedule** uses framework defaults (cosine, no explicit warmup). Tuning is a
  follow-up concern, not a smoke-loop concern.
