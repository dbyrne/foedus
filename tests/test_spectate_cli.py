"""Tests for scripts/foedus_spectator.py's argument parsing (not the actual
server loop -- that's exercised by tests/test_spectate_server.py's route()
tests plus a manual smoke run against a live server)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import pytest

import foedus_spectator as cli


def test_main_requires_command() -> None:
    with pytest.raises(SystemExit):
        cli.main([])


def test_main_rejects_nonexistent_run_dir(tmp_path, capsys) -> None:
    missing = tmp_path / "does-not-exist"
    with pytest.raises(SystemExit):
        cli.main(["serve", "--run-dir", str(missing)])


def test_main_serve_invokes_server_serve(tmp_path, monkeypatch) -> None:
    calls = {}

    def fake_serve(run_dir, host, port):
        calls["run_dir"] = run_dir
        calls["host"] = host
        calls["port"] = port

    monkeypatch.setattr(cli, "serve", fake_serve)
    rc = cli.main(["serve", "--run-dir", str(tmp_path), "--port", "9999", "--host", "127.0.0.1"])
    assert rc == 0
    assert calls == {"run_dir": tmp_path, "host": "127.0.0.1", "port": 9999}
