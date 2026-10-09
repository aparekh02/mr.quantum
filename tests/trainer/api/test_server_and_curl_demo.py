"""The real server and the curl demo, end to end (Sprint 3 done-criterion)."""

import os
import socket
import subprocess
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
import uvicorn

from trainer.api.__main__ import build_parser, make_app

REPO = Path(__file__).resolve().parents[3]
DEMO = REPO / "trainer" / "demos" / "sprint03.sh"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port: int = s.getsockname()[1]
        return port


@pytest.fixture
def server(tmp_path: Path) -> Iterator[str]:
    port = _free_port()
    args = build_parser().parse_args(["--port", str(port), "--data-dir", str(tmp_path)])
    config = uvicorn.Config(
        make_app(args), host="127.0.0.1", port=port, log_level="warning"
    )
    srv = uvicorn.Server(config)
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while not srv.started and time.time() < deadline:
        time.sleep(0.05)
    assert srv.started
    yield f"http://127.0.0.1:{port}"
    srv.should_exit = True
    thread.join(timeout=10)


def test_parser_defaults() -> None:
    args = build_parser().parse_args([])
    assert args.port == 8765
    assert args.host == "127.0.0.1"
    assert Path(args.devices_dir).name == "devices"


def test_curl_runs_find_sensor_peak_and_watches_the_stream(server: str) -> None:
    out = subprocess.run(
        ["bash", str(DEMO)],
        env={**os.environ, "API": server},
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert out.returncode == 0, out.stderr
    assert "side_B/finger_gate_characterization: succeeded" in out.stdout
    assert "find_sensor_peak: succeeded" in out.stdout
    assert "streamed" in out.stdout and "sweep" in out.stdout
    assert "best_peak_voltage" in out.stdout
