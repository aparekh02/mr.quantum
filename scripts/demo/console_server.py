"""Local stand-in for Qollab's Run button, used to record the demo video.

Serves ``console.html`` and ``GET /run?<main() parameters>``, which runs the real
``qollab/main.py`` (Qiskit's BasicSimulator, since there is no Qollab backend here)
in a fresh process and returns its console output.

    .venv/bin/python scripts/demo/console_server.py [--port 8777]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
QOLLAB = HERE.parents[1] / "qollab"

# Coerces each query value to main()'s annotation, then calls main() once.
CHILD = """
import inspect, json, sys
from main import main
raw = json.loads(sys.argv[1])
kinds = {"int": int, "float": float, "str": str}
kwargs = {}
for name, p in inspect.signature(main).parameters.items():
    if name not in raw:
        continue
    kind = p.annotation if isinstance(p.annotation, str) else p.annotation.__name__
    value = raw[name]
    kwargs[name] = value.lower() == "true" if kind == "bool" else kinds[kind](value)
main(**kwargs)
"""


def run_main(params: dict[str, str]) -> str:
    done = subprocess.run(
        [sys.executable, "-c", CHILD, json.dumps(params)],
        cwd=QOLLAB,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    return done.stdout + done.stderr


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        url = urlparse(self.path)
        if url.path == "/run":
            params = {k: v[-1] for k, v in parse_qs(url.query).items()}
            self._send(200, "text/plain; charset=utf-8", run_main(params).encode())
        elif url.path in ("/", "/console.html"):
            page = (HERE / "console.html").read_bytes()
            self._send(200, "text/html; charset=utf-8", page)
        else:
            self._send(404, "text/plain", b"not found")

    def _send(self, status: int, kind: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8777)
    port = parser.parse_args().port
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
