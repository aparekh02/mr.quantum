"""Run the trainer API: ``python -m trainer.api [--port 8765]``."""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

import uvicorn
from fastapi import FastAPI

from trainer.api.app import create_app

DEVICES = Path(__file__).resolve().parents[1] / "devices"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Stanza Tune-Up Trainer API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--devices-dir", default=str(DEVICES))
    parser.add_argument("--data-dir", default=None, help="where routine data is logged")
    return parser


def make_app(args: argparse.Namespace) -> FastAPI:
    data_dir = Path(args.data_dir or tempfile.mkdtemp(prefix="trainer-api-"))
    return create_app(devices_dir=Path(args.devices_dir), data_dir=data_dir)


def main() -> None:  # pragma: no cover - thin CLI shim over uvicorn
    args = build_parser().parse_args()
    uvicorn.run(make_app(args), host=args.host, port=args.port)


if __name__ == "__main__":  # pragma: no cover
    main()
