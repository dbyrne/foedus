"""Blocking subagent client for foedus press games.

Usage:
    PYTHONPATH=. python3 scripts/foedus_press_client.py \
        --server http://localhost:8090 \
        --game $GID \
        --player 0

The client loops until the game terminates. Per round:
    1. Long-poll /wait/{p}/chat
    2. GET /chat-prompt/{p} → print to stdout, on a "----CHAT----" header
    3. Read a line of JSON from stdin
    4. POST /chat with that JSON
    5. Long-poll /wait/{p}/commit
    6. GET /commit-prompt/{p} → print to stdout, on a "----COMMIT----" header
    7. Read a line of JSON from stdin
    8. POST /commit with that JSON
    9. If terminal, print final summary and exit 0

The subagent dispatching this client is expected to alternate
between reading stdout (prompts) and writing stdin (JSON responses),
one line at a time.

Spec: docs/superpowers/specs/2026-04-29-autonomous-press-harness-design.md
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request


def _http(method: str, url: str,
          body: dict | None = None) -> tuple[int, dict | str]:
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method,
                                  headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            payload = resp.read().decode("utf-8")
            ctype = resp.headers.get("Content-Type", "")
            if "application/json" in ctype:
                return resp.status, json.loads(payload)
            return resp.status, payload
    except urllib.error.HTTPError as e:
        payload = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(payload)
        except json.JSONDecodeError:
            return e.code, payload


def _retry(fn, attempts: int = 3, backoff: float = 1.0):
    for i in range(attempts):
        try:
            return fn()
        except (urllib.error.URLError, ConnectionError) as e:
            if i == attempts - 1:
                raise
            time.sleep(backoff * (2 ** i))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", required=True)
    parser.add_argument("--game", required=True)
    parser.add_argument("--player", type=int, required=True)
    parser.add_argument("--max-rounds", type=int, default=100)
    args = parser.parse_args()
    base = args.server.rstrip("/")
    gid = args.game
    pid = args.player

    rounds = 0
    while rounds < args.max_rounds:
        # 1. Wait for chat phase open.
        while True:
            code, body = _retry(lambda: _http(
                "GET", f"{base}/games/{gid}/wait/{pid}/chat"))
            if code != 200:
                print(f"ERR /wait/{pid}/chat: {code} {body}",
                      file=sys.stderr)
                return 1
            if body.get("is_terminal"):
                print("=== GAME TERMINAL ===", flush=True)
                view = _http(
                    "GET", f"{base}/games/{gid}/view/{pid}")[1]
                print(json.dumps({
                    "scores": view.get("scores"),
                    "winners": view.get("winners"),
                    "turn": view.get("turn"),
                }), flush=True)
                return 0
            if body.get("ready"):
                break
            # not ready and not terminal — retry the long-poll
            continue
        # 2. Get chat prompt and emit.
        code, prompt = _http(
            "GET", f"{base}/games/{gid}/chat-prompt/{pid}")
        if code != 200:
            print(f"ERR /chat-prompt/{pid}: {code} {prompt}",
                  file=sys.stderr)
            return 1
        print("----CHAT----", flush=True)
        print(prompt, flush=True)
        print("----END-PROMPT----", flush=True)
        # 3. Read a single JSON line from stdin (or {} for skip).
        line = sys.stdin.readline()
        if not line:
            print("ERR: stdin closed during chat phase", file=sys.stderr)
            return 1
        try:
            chat_payload = json.loads(line.strip() or "{}")
        except json.JSONDecodeError as e:
            print(f"ERR: invalid chat JSON: {e}", file=sys.stderr)
            return 2
        # 4. POST /chat.
        code, body = _http("POST", f"{base}/games/{gid}/chat", body={
            "player": pid,
            "draft": chat_payload if chat_payload else None,
        })
        if code not in (200, 409):
            print(f"ERR /chat: {code} {body}", file=sys.stderr)
            return 1

        # 5. Wait for commit phase open.
        while True:
            code, body = _retry(lambda: _http(
                "GET", f"{base}/games/{gid}/wait/{pid}/commit"))
            if code != 200:
                print(f"ERR /wait/{pid}/commit: {code} {body}",
                      file=sys.stderr)
                return 1
            if body.get("is_terminal"):
                print("=== GAME TERMINAL ===", flush=True)
                return 0
            if body.get("ready"):
                break
            continue
        # 6. Get commit prompt and emit.
        code, prompt = _http(
            "GET", f"{base}/games/{gid}/commit-prompt/{pid}")
        if code != 200:
            print(f"ERR /commit-prompt/{pid}: {code} {prompt}",
                  file=sys.stderr)
            return 1
        print("----COMMIT----", flush=True)
        print(prompt, flush=True)
        print("----END-PROMPT----", flush=True)
        # 7. Read JSON from stdin.
        line = sys.stdin.readline()
        if not line:
            print("ERR: stdin closed during commit phase",
                  file=sys.stderr)
            return 1
        try:
            commit_payload = json.loads(line.strip())
        except json.JSONDecodeError as e:
            print(f"ERR: invalid commit JSON: {e}", file=sys.stderr)
            return 2
        # 8. POST /commit.
        code, body = _http(
            "POST", f"{base}/games/{gid}/commit", body={
                "player": pid,
                "press": commit_payload.get("press", {}),
                "orders": commit_payload.get("orders", {}),
            })
        if code != 200:
            print(f"ERR /commit: {code} {body}", file=sys.stderr)
            return 1
        # 9. If round advanced and game terminal, exit.
        if body.get("is_terminal"):
            print("=== GAME TERMINAL ===", flush=True)
            return 0
        rounds += 1
    print(f"ERR: max-rounds ({args.max_rounds}) hit; aborting",
          file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
