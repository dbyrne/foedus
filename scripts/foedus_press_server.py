"""Run the foedus press game server on port 8090 (default).

Usage:
    PYTHONPATH=. python3 scripts/foedus_press_server.py
    PYTHONPATH=. python3 scripts/foedus_press_server.py --port 9000
"""

from __future__ import annotations

import argparse
import os
import sys

import uvicorn  # type: ignore[import-not-found]

from foedus.game_server.server import make_app


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8090)
    parser.add_argument("--wait-timeout", type=float, default=30.0,
                        help="Long-poll max-wait seconds")
    args = parser.parse_args()
    os.environ["FOEDUS_PRESS_WAIT_TIMEOUT"] = str(args.wait_timeout)
    print(f"foedus press server starting on http://{args.host}:{args.port}")
    uvicorn.run(make_app(), host=args.host, port=args.port,
                log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
