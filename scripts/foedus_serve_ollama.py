"""Serve a QLoRA-trained foedus entrant through Ollama.

Pipeline: merge the LoRA adapter into the fp16 base -> convert to GGUF with
llama.cpp's canonical converter -> register with the running Ollama server via
its REST API (upload the GGUF blob + POST /api/create, quantizing to q4_K_M
server-side). The resulting model (default tag ``foedus-entrant-v0``) then plays
foedus through the *existing* ``OllamaClient`` -- no new backend.

Why this shape (banked from the finetune-lab lessons, see
``create_ollama_model_v3.py``):

* Ollama's **built-in safetensors converter corrupts Qwen2.5-3B tied embeddings**
  (garbage logits + sampler crash). So we convert with llama.cpp first and hand
  Ollama a finished GGUF; it only needs to quantize.
* Talking to Ollama over **REST** (not the CLI) means this works even when the
  Ollama server is the Windows binary (not executable from WSL) -- the WSL client
  just POSTs to ``localhost:11434``.

The LoRA merge needs the ``[train]`` env (torch/peft). The GGUF conversion is
shelled out to a python that can run ``convert_hf_to_gguf.py`` (defaults to the
finetune-lab venv, overridable) so we reuse the environment already proven for
Qwen2.5-3B conversion.

Example::

    python scripts/foedus_serve_ollama.py \
        --adapter-dir runs/qlora_entrant_v0 \
        --model-name foedus-entrant-v0
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

# ChatML wrapping for a single system+prompt exchange (Qwen2.5 uses ChatML).
CHATML_TEMPLATE = (
    "{{ if .System }}<|im_start|>system\n{{ .System }}<|im_end|>\n{{ end }}"
    "{{ if .Prompt }}<|im_start|>user\n{{ .Prompt }}<|im_end|>\n{{ end }}"
    "<|im_start|>assistant\n{{ .Response }}<|im_end|>\n"
)
STOP_TOKEN = "<|im_end|>"

DEFAULT_LLAMA_CPP = os.path.expanduser("~/finetune-lab/llama.cpp")
DEFAULT_CONVERT_PYTHON = os.path.expanduser("~/finetune-lab/.venv/bin/python")
DEFAULT_OLLAMA_HOST = "http://localhost:11434"


# --------------------------------------------------------------------------- #
# pure helpers (testable without torch / network)
# --------------------------------------------------------------------------- #
def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def build_create_payload(
    model_name: str,
    gguf_filename: str,
    digest: str,
    quantize: str,
    system: str | None = None,
    template: str = CHATML_TEMPLATE,
    parameters: dict | None = None,
) -> dict:
    params = {"stop": [STOP_TOKEN], "temperature": 0.2}
    if parameters:
        params.update(parameters)
    payload = {
        "model": model_name,
        "files": {gguf_filename: digest},
        "quantize": quantize,
        "template": template,
        "parameters": params,
    }
    if system:
        payload["system"] = system
    return payload


# --------------------------------------------------------------------------- #
# steps
# --------------------------------------------------------------------------- #
def merge_lora(base_model: str, adapter_dir: str, out_dir: str) -> str:
    """Merge the LoRA adapter into an fp16 copy of ``base_model``; save to out_dir."""
    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer

    print(f"[serve] merging {adapter_dir} into {base_model} (fp16, CPU)...", flush=True)
    base = AutoModelForCausalLM.from_pretrained(
        base_model, dtype=torch.float16, device_map="cpu"
    )
    model = PeftModel.from_pretrained(base, adapter_dir)
    merged = model.merge_and_unload()
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    merged.save_pretrained(out_dir, safe_serialization=True)
    # keep the base tokenizer (carries the ChatML chat_template into the GGUF)
    AutoTokenizer.from_pretrained(base_model).save_pretrained(out_dir)
    print(f"[serve] merged model written to {out_dir}", flush=True)
    return out_dir


def convert_to_gguf(
    merged_dir: str,
    gguf_out: str,
    convert_python: str = DEFAULT_CONVERT_PYTHON,
    llama_cpp: str = DEFAULT_LLAMA_CPP,
    outtype: str = "f16",
) -> str:
    """Convert an HF model dir to a GGUF via llama.cpp's convert_hf_to_gguf.py."""
    script = Path(llama_cpp) / "convert_hf_to_gguf.py"
    if not script.exists():
        raise FileNotFoundError(f"convert_hf_to_gguf.py not found at {script}")
    cmd = [
        convert_python,
        str(script),
        str(merged_dir),
        "--outfile",
        str(gguf_out),
        "--outtype",
        outtype,
    ]
    env = {**os.environ, "PYTHONPATH": str(Path(llama_cpp) / "gguf-py")}
    print(f"[serve] converting to GGUF ({outtype}): {' '.join(cmd)}", flush=True)
    subprocess.run(cmd, check=True, env=env)
    print(f"[serve] GGUF written to {gguf_out}", flush=True)
    return gguf_out


def _blob_exists(host: str, digest: str) -> bool:
    req = urllib.request.Request(f"{host}/api/blobs/{digest}", method="HEAD")
    try:
        urllib.request.urlopen(req)
        return True
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return False
        raise


def upload_blob(host: str, gguf_path: str, digest: str) -> None:
    if _blob_exists(host, digest):
        print(f"[serve] blob {digest[:19]}... already on server", flush=True)
        return
    size = os.path.getsize(gguf_path)
    print(f"[serve] uploading blob ({size / 1e9:.2f} GB)...", flush=True)
    with open(gguf_path, "rb") as fh:
        req = urllib.request.Request(
            f"{host}/api/blobs/{digest}", data=fh, method="POST"
        )
        req.add_header("Content-Type", "application/octet-stream")
        req.add_header("Content-Length", str(size))
        with urllib.request.urlopen(req) as resp:
            print(f"[serve] blob upload -> HTTP {resp.status}", flush=True)


def ollama_create(host: str, payload: dict) -> None:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{host}/api/create", data=data, method="POST",
        headers={"Content-Type": "application/json"},
    )
    print(f"[serve] POST /api/create {payload['model']} (quantize={payload['quantize']})...", flush=True)
    with urllib.request.urlopen(req) as resp:
        for raw in resp:
            line = raw.decode("utf-8").strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
                print("[serve]  ", msg.get("status", line), flush=True)
            except json.JSONDecodeError:
                print("[serve]  ", line, flush=True)


def list_models(host: str) -> list[str]:
    with urllib.request.urlopen(f"{host}/api/tags") as resp:
        tags = json.loads(resp.read())
    return [m["name"] for m in tags.get("models", [])]


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--adapter-dir", required=True, help="LoRA adapter dir from training.")
    p.add_argument("--base-model", default="Qwen/Qwen2.5-3B-Instruct")
    p.add_argument("--model-name", default="foedus-entrant-v0")
    p.add_argument(
        "--work-dir",
        default=None,
        help="Where merged model + GGUF go (default: <adapter-dir>/serve).",
    )
    p.add_argument("--quantize", default="q4_K_M")
    p.add_argument("--ollama-host", default=DEFAULT_OLLAMA_HOST)
    p.add_argument("--llama-cpp", default=DEFAULT_LLAMA_CPP)
    p.add_argument("--convert-python", default=DEFAULT_CONVERT_PYTHON)
    p.add_argument("--system", default=None, help="Optional system prompt baked into the model.")
    p.add_argument("--skip-merge", action="store_true")
    p.add_argument("--skip-convert", action="store_true")
    p.add_argument("--skip-create", action="store_true")
    args = p.parse_args(argv)

    work = Path(args.work_dir or (Path(args.adapter_dir) / "serve"))
    work.mkdir(parents=True, exist_ok=True)
    merged_dir = work / "merged"
    gguf_path = work / f"{args.model_name}.f16.gguf"

    if not args.skip_merge:
        merge_lora(args.base_model, args.adapter_dir, str(merged_dir))
    if not args.skip_convert:
        convert_to_gguf(str(merged_dir), str(gguf_path), args.convert_python, args.llama_cpp)
    if not args.skip_create:
        digest = sha256_file(gguf_path)
        print(f"[serve] gguf sha256={digest}", flush=True)
        upload_blob(args.ollama_host, str(gguf_path), digest)
        payload = build_create_payload(
            args.model_name, gguf_path.name, digest, args.quantize, system=args.system
        )
        ollama_create(args.ollama_host, payload)
        print(f"[serve] models now: {list_models(args.ollama_host)}", flush=True)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
