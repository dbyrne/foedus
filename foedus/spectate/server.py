"""Stdlib-only spectator HTTP server (no fastapi/uvicorn -- the project's
[web]/[dev] extras are known env-broken in some sandboxes, and this tool
must run anywhere `python3` does).

`route()` is a pure function of (run_dir, method, path) -> (status,
content_type, body_bytes) with no socket I/O, so it's testable directly
(see tests/test_spectate_server.py). `serve()` wires it into
http.server.ThreadingHTTPServer for the `foedus_spectator.py serve` CLI.
"""

from __future__ import annotations

import json
import re
import subprocess
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from foedus.spectate.dashboard import build_dashboard
from foedus.spectate.html import DASHBOARD_HTML, REPLAY_HTML
from foedus.spectate.readers import load_sweep
from foedus.spectate.replay import build_replay

_SPECTATE_STREAM_RE = re.compile(r"^spectate_game(\d+)\.jsonl$")


def _list_games(run_dir: Path) -> list[dict]:
    """Finished games (from sweep.jsonl) plus any in-flight game that has an
    opt-in live spectate stream but no sweep record yet -- "the spectator
    server auto-upgrades to live turn-by-turn when the stream exists"."""
    games = [
        {"game_id": r.get("game_id"), "game_index": r.get("game_index"), "live": False}
        for r in load_sweep(run_dir)
    ]
    finished_ids = {g["game_id"] for g in games}
    for path in sorted(run_dir.glob("spectate_game*.jsonl")):
        m = _SPECTATE_STREAM_RE.match(path.name)
        if not m:
            continue
        game_id = int(m.group(1))
        if game_id in finished_ids:
            continue
        games.append({"game_id": game_id, "game_index": game_id, "live": True})
    return games

_ACTIVITY_FILES = (
    "sweep.jsonl", "telemetry.jsonl", "timing.log",
    "campaign_memory_game*_seat*.json", "transcript_game*.md",
)


def count_inflight_claude_calls() -> int:
    """Best-effort count of live `claude -p` subprocesses (the campaign's
    LLM-call backend). Never raises -- returns 0 on any failure (pgrep
    missing, sandboxed, etc)."""
    try:
        result = subprocess.run(
            ["pgrep", "-f", "-c", "claude -p"],
            capture_output=True, text=True, timeout=2,
        )
        return int((result.stdout or "0").strip() or 0)
    except Exception:  # noqa: BLE001 - best-effort telemetry, never fatal
        return 0


def _last_activity_ago_s(run_dir: Path) -> float | None:
    mtimes = []
    for pattern in _ACTIVITY_FILES:
        for path in run_dir.glob(pattern):
            try:
                mtimes.append(path.stat().st_mtime)
            except OSError:
                continue
    if not mtimes:
        return None
    return max(0.0, time.time() - max(mtimes))


def _json_response(data, status: int = 200) -> tuple[int, str, bytes]:
    return status, "application/json", json.dumps(data).encode()


def route(run_dir: str | Path, method: str, path: str) -> tuple[int, str, bytes]:
    """Pure routing: no sockets, no globals -- safe to call directly in tests."""
    run_dir = Path(run_dir)
    if method != "GET":
        return 405, "text/plain", b"method not allowed"

    p = urlsplit(path).path

    if p == "/" or p == "/dashboard":
        return 200, "text/html; charset=utf-8", DASHBOARD_HTML.encode()
    if p == "/replay":
        return 200, "text/html; charset=utf-8", REPLAY_HTML.encode()

    if p == "/api/dashboard":
        data = build_dashboard(run_dir)
        data["inflight_claude_calls"] = count_inflight_claude_calls()
        data["last_activity_ago_s"] = _last_activity_ago_s(run_dir)
        return _json_response(data)

    if p == "/api/games":
        return _json_response(_list_games(run_dir))

    if p.startswith("/api/replay/"):
        raw_id = p[len("/api/replay/"):]
        try:
            game_id = int(raw_id)
        except ValueError:
            return _json_response({"error": f"invalid game id: {raw_id!r}"}, status=400)
        data = build_replay(run_dir, game_id)
        if data is None:
            return _json_response({"error": f"game {game_id} not found"}, status=404)
        return _json_response(data)

    return 404, "text/plain", b"not found"


def make_handler(run_dir: Path):
    class SpectatorHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            status, content_type, body = route(run_dir, "GET", self.path)
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt: str, *args) -> None:  # noqa: A003
            pass  # quiet by default; run with -v-equivalent flag if needed later

    return SpectatorHandler


def serve(run_dir: str | Path, host: str = "0.0.0.0", port: int = 8321) -> None:
    httpd = ThreadingHTTPServer((host, port), make_handler(Path(run_dir)))
    print(f"foedus spectator serving {run_dir} on http://{host}:{port}/")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
