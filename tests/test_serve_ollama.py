"""Tests for the pure parts of the merge->GGUF->ollama serve script.

The heavy steps (LoRA merge, llama.cpp conversion, blob upload) are I/O and are
proven by the end-to-end run in the design doc; here we TDD the payload/template
construction and blob digest so the ollama `create` request is well-formed.
"""
from __future__ import annotations

import hashlib

from scripts.foedus_serve_ollama import (
    CHATML_TEMPLATE,
    STOP_TOKEN,
    build_create_payload,
    sha256_file,
)


def test_chatml_template_has_role_markers_and_fields():
    for marker in ("<|im_start|>system", "<|im_start|>user", "<|im_start|>assistant"):
        assert marker in CHATML_TEMPLATE
    # ollama Modelfile template fields for a single system+prompt exchange
    for field in ("{{ .System }}", "{{ .Prompt }}", "{{ .Response }}"):
        assert field in CHATML_TEMPLATE


def test_build_create_payload_shape():
    payload = build_create_payload(
        model_name="foedus-entrant-v0",
        gguf_filename="foedus-entrant-v0.f16.gguf",
        digest="sha256:abc123",
        quantize="q4_K_M",
    )
    assert payload["model"] == "foedus-entrant-v0"
    assert payload["files"] == {"foedus-entrant-v0.f16.gguf": "sha256:abc123"}
    assert payload["quantize"] == "q4_K_M"
    assert payload["template"] == CHATML_TEMPLATE
    assert STOP_TOKEN in payload["parameters"]["stop"]


def test_build_create_payload_system_optional():
    without = build_create_payload("m", "f.gguf", "sha256:x", "q4_K_M")
    assert "system" not in without
    with_sys = build_create_payload("m", "f.gguf", "sha256:x", "q4_K_M", system="You are X.")
    assert with_sys["system"] == "You are X."


def test_sha256_file(tmp_path):
    p = tmp_path / "blob.bin"
    data = b"foedus-entrant-v0 weights"
    p.write_bytes(data)
    expected = "sha256:" + hashlib.sha256(data).hexdigest()
    assert sha256_file(p) == expected
