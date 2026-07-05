"""Arena Spectator v0 -- live campaign dashboard + turn-by-turn game replay.

Stdlib-only web server (http.server), self-contained static frontend (no
external CDNs). Read-only over a campaign run-dir; never writes into it.

Usage:
    python3 scripts/foedus_spectator.py serve --run-dir <RUN_DIR> \\
        --port 8321 --host 0.0.0.0

Host 0.0.0.0 by default so it's reachable from a phone over Tailscale.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from foedus.spectate.server import serve


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve_parser = subparsers.add_parser("serve", help="Serve the dashboard + replay theater.")
    serve_parser.add_argument("--run-dir", type=str, required=True,
                               help="Campaign run-dir to read (read-only; never written to).")
    serve_parser.add_argument("--port", type=int, default=8321)
    serve_parser.add_argument("--host", type=str, default="0.0.0.0",
                               help="Default 0.0.0.0 for LAN/Tailscale phone access.")

    args = parser.parse_args(argv)

    run_dir = Path(args.run_dir)
    if not run_dir.is_dir():
        parser.error(f"--run-dir {args.run_dir!r} is not a directory")

    serve(run_dir, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
