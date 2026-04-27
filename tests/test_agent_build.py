"""Tests for foedus/agent_build.py — the Docker glue.

Mocks subprocess so the suite never shells out to docker.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from foedus import agent_build as ab
from foedus.agent_build import (
    DockerError,
    build_agent_image,
    bundled_dockerfile,
    run_agent_container,
    stop_agent_container,
)


@pytest.fixture
def fake_run():
    """Patch foedus.agent_build._run with a Mock recording calls.

    Returns "" by default. Tests can override via mock.return_value or
    mock.side_effect. Inspect mock.call_args_list for command verification.
    """
    with patch("foedus.agent_build._run") as m:
        m.return_value = ""
        yield m


def test_bundled_dockerfile_exists() -> None:
    """The Dockerfile.agent must ship as package data."""
    p = bundled_dockerfile()
    assert p.exists(), f"missing bundled Dockerfile at {p}"
    text = p.read_text()
    assert "AGENT" in text  # build-arg referenced
    assert "foedus agent serve" in text


def test_build_passes_tag_and_agent(fake_run) -> None:
    fake_run.return_value = ""
    build_agent_image("my-agent:v1", "foedus.RandomAgent")
    cmd = fake_run.call_args_list[0].args[0]
    assert cmd[0] == "docker"
    assert cmd[1] == "build"
    assert "-t" in cmd
    assert "my-agent:v1" in cmd
    # Build-arg AGENT=foedus.RandomAgent is passed
    pairs = [cmd[i + 1] for i, t in enumerate(cmd) if t == "--build-arg"]
    assert "AGENT=foedus.RandomAgent" in pairs


def test_build_uses_bundled_dockerfile_by_default(fake_run) -> None:
    fake_run.return_value = ""
    build_agent_image("img:1", "x.Y")
    cmd = fake_run.call_args_list[0].args[0]
    assert "-f" in cmd
    df_idx = cmd.index("-f")
    df_path = Path(cmd[df_idx + 1])
    assert df_path.name == "Dockerfile.agent"


def test_build_with_custom_dockerfile(fake_run, tmp_path: Path) -> None:
    custom = tmp_path / "Dockerfile.custom"
    custom.write_text("FROM scratch\n")
    fake_run.return_value = ""
    build_agent_image("img:1", "x.Y", dockerfile=custom)
    cmd = fake_run.call_args_list[0].args[0]
    df_idx = cmd.index("-f")
    assert Path(cmd[df_idx + 1]).name == "Dockerfile.custom"


def test_build_with_extra_build_args(fake_run) -> None:
    fake_run.return_value = ""
    build_agent_image("img:1", "x.Y",
                      extra_build_args={"PYTHON_VERSION": "3.12"})
    cmd = fake_run.call_args_list[0].args[0]
    pairs = [cmd[i + 1] for i, t in enumerate(cmd) if t == "--build-arg"]
    assert "AGENT=x.Y" in pairs
    assert "PYTHON_VERSION=3.12" in pairs


def test_build_no_cache_flag(fake_run) -> None:
    fake_run.return_value = ""
    build_agent_image("img:1", "x.Y", no_cache=True)
    cmd = fake_run.call_args_list[0].args[0]
    assert "--no-cache" in cmd


def test_run_constructs_port_mapping(fake_run) -> None:
    fake_run.return_value = "abc123def456\n"
    cid = run_agent_container("img:1", port=9000, name="my-agent")
    assert cid == "abc123def456"
    cmd = fake_run.call_args_list[0].args[0]
    assert cmd[:3] == ["docker", "run", "-d"]
    assert "--rm" in cmd
    # Port mapping host:container
    p_idx = cmd.index("-p")
    assert cmd[p_idx + 1] == "9000:8080"
    assert "--name" in cmd
    assert "my-agent" in cmd
    assert cmd[-1] == "img:1"


def test_run_no_auto_remove(fake_run) -> None:
    fake_run.return_value = "id\n"
    run_agent_container("img:1", auto_remove=False)
    cmd = fake_run.call_args_list[0].args[0]
    assert "--rm" not in cmd


def test_run_no_detach(fake_run) -> None:
    fake_run.return_value = ""
    run_agent_container("img:1", detach=False)
    cmd = fake_run.call_args_list[0].args[0]
    assert "-d" not in cmd


def test_stop_calls_docker_stop(fake_run) -> None:
    fake_run.return_value = ""
    stop_agent_container("my-agent", timeout=5)
    cmd = fake_run.call_args_list[0].args[0]
    assert cmd == ["docker", "stop", "-t", "5", "my-agent"]


# --- error paths ---


def test_run_helper_raises_when_docker_missing(monkeypatch) -> None:
    monkeypatch.setattr("foedus.agent_build.shutil.which", lambda _: None)
    with pytest.raises(DockerError) as exc:
        ab._run(["docker", "ps"])
    assert "not found on PATH" in str(exc.value)


def test_run_helper_raises_on_nonzero_exit(monkeypatch) -> None:
    monkeypatch.setattr("foedus.agent_build.shutil.which",
                        lambda _: "/usr/bin/docker")

    def fake_subprocess_run(*args, **kwargs):
        raise subprocess.CalledProcessError(
            returncode=125, cmd=args[0], output="", stderr="bad image\n",
        )

    monkeypatch.setattr("foedus.agent_build.subprocess.run",
                        fake_subprocess_run)
    with pytest.raises(DockerError) as exc:
        ab._run(["docker", "build", "/x"])
    assert "exited 125" in str(exc.value)
    assert "bad image" in str(exc.value)
