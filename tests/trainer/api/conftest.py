"""Fixtures for API tests: an app over the real device files, and a client."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.trainer.api import routines_for_tests
from trainer.api.app import create_app

DEVICES = Path(__file__).resolve().parents[3] / "trainer" / "devices"


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    app = create_app(devices_dir=DEVICES, data_dir=tmp_path)
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def new_session(client: TestClient, device: str = "dqd_with_sensor") -> str:
    response = client.post("/sessions", json={"device": device})
    assert response.status_code == 201, response.text
    sid: str = response.json()["id"]
    return sid


@pytest.fixture(autouse=True)
def _test_routines_registered() -> None:
    routines_for_tests.register()
