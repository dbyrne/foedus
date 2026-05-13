"""One-off static server for the Phase 0 spike: serves files with the
COOP/COEP headers Godot 4 HTML5 needs for SharedArrayBuffer.

Usage:
    python scripts/spike_local_serve.py --dir /tmp/foedus-godot-web --port 8080
"""
from __future__ import annotations
import argparse
import http.server
import os
import socketserver


class COOPHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
        self.send_header("Cross-Origin-Resource-Policy", "cross-origin")
        super().end_headers()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="/tmp/foedus-godot-web")
    ap.add_argument("--port", type=int, default=8080)
    args = ap.parse_args()
    os.chdir(args.dir)
    with socketserver.TCPServer(("0.0.0.0", args.port), COOPHandler) as httpd:
        print(f"serving {args.dir} at http://0.0.0.0:{args.port}")
        httpd.serve_forever()


if __name__ == "__main__":
    main()
