"""Thin glue for building / running foedus agent Docker images.

Shells out to the `docker` CLI for the same reasons castra does — fewer
dependency headaches, easy to substitute `podman`. Foedus deliberately
doesn't depend on castra; agent creators who want richer image management
(multi-region ECR push, EC2 launch, etc.) can use castra alongside.

Three operations:
- `build_agent_image` — wrap an agent class into a runnable container image
- `run_agent_container` — start a container, port-map to host
- `stop_agent_container` — stop and remove
"""

from __future__ import annotations

import shutil
import subprocess
from importlib import resources
from pathlib import Path

DOCKER_BIN = "docker"


class DockerError(RuntimeError):
    """A docker invocation failed (or docker isn't on PATH)."""


def bundled_dockerfile() -> Path:
    """Return the path to the bundled Dockerfile.agent template."""
    return Path(str(resources.files("foedus.remote") / "Dockerfile.agent"))


def _run(argv: list[str], *, check: bool = True) -> str:
    if shutil.which(argv[0]) is None:
        raise DockerError(f"{argv[0]!r} not found on PATH; install Docker first")
    try:
        result = subprocess.run(
            argv, capture_output=True, text=True, check=check,
        )
    except subprocess.CalledProcessError as e:
        msg = (e.stderr or e.stdout or "").strip()
        raise DockerError(
            f"{' '.join(argv)} exited {e.returncode}: {msg}"
        ) from e
    return result.stdout


def build_agent_image(
    tag: str,
    agent_path: str,
    *,
    context: Path | str | None = None,
    dockerfile: Path | str | None = None,
    no_cache: bool = False,
    extra_build_args: dict[str, str] | None = None,
) -> str:
    """Build a Docker image that serves `agent_path` over HTTP.

    Returns `tag`. Build context defaults to the current working directory
    (where the user's pyproject.toml should live). The bundled Dockerfile
    is used unless `dockerfile` is provided.
    """
    ctx = Path(context).resolve() if context else Path.cwd()
    df = Path(dockerfile).resolve() if dockerfile else bundled_dockerfile()

    cmd = [DOCKER_BIN, "build", "-t", tag, "-f", str(df),
           "--build-arg", f"AGENT={agent_path}"]
    for k, v in (extra_build_args or {}).items():
        cmd.extend(["--build-arg", f"{k}={v}"])
    if no_cache:
        cmd.append("--no-cache")
    cmd.append(str(ctx))
    _run(cmd)
    return tag


def run_agent_container(
    tag: str,
    *,
    port: int = 8080,
    name: str | None = None,
    detach: bool = True,
    auto_remove: bool = True,
) -> str:
    """Start an agent container. Returns the container ID."""
    cmd = [DOCKER_BIN, "run"]
    if detach:
        cmd.append("-d")
    if auto_remove:
        cmd.append("--rm")
    if name:
        cmd.extend(["--name", name])
    cmd.extend(["-p", f"{port}:8080", tag])
    return _run(cmd).strip()


def stop_agent_container(name_or_id: str, *, timeout: int = 10) -> None:
    """Stop a running agent container. `--rm` from `run_agent_container`
    handles cleanup; we only call `docker stop`.
    """
    _run([DOCKER_BIN, "stop", "-t", str(timeout), name_or_id])
