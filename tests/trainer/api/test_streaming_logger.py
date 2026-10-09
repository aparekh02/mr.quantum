"""StreamingDataLogger tees upstream logger sessions into an EventLog."""

from pathlib import Path

import numpy as np

from tests.trainer.conftest import SINGLE_CHANNEL_YAML
from trainer.api.events import EventLog
from trainer.api.streaming import StreamingDataLogger
from trainer.lab import SimulatedLab


def _logger(tmp_path: Path, log: EventLog) -> StreamingDataLogger:
    return StreamingDataLogger(routine_name="device", base_dir=tmp_path, events=log)


def test_live_sweep_points_stream_in_order(tmp_path: Path) -> None:
    log = EventLog()
    lab = SimulatedLab.from_yaml(SINGLE_CHANNEL_YAML, base_dir=tmp_path)
    session = _logger(tmp_path, log).create_session("s1")
    voltages = list(np.linspace(0.0, 1.0, 25))
    lab.device.sweep_1d("P1", voltages, "D", session=session)
    points = [e for e in log.since(0) if e.kind == "sweep_point"]
    assert [p.data["x"][0] for p in points] == voltages
    assert [e.kind for e in log.since(0)][-1] == "sweep"
    done = log.since(0)[-1]
    assert done.data["x_data"] == [[v] for v in voltages]
    assert len(done.data["y_data"]) == 25


def test_log_sweep_is_one_sweep_event(tmp_path: Path) -> None:
    log = EventLog()
    session = _logger(tmp_path, log).create_session("s1")
    session.log_sweep("n gates sweep", [[0.0, 1.0], [0.1, 1.1]], [1e-9, 2e-9], "V", "I")
    (event,) = log.since(0)
    assert event.kind == "sweep"
    assert event.name == "n gates sweep"
    assert event.data["y_data"] == [1e-9, 2e-9]


def test_measurement_and_analysis_are_distinguished(tmp_path: Path) -> None:
    log = EventLog()
    session = _logger(tmp_path, log).create_session("s1")
    session.log_measurement("raw", {"currents": np.array([1.0, 2.0])})
    session.log_analysis("fit", {"popt": np.array([0.5])})
    kinds = [(e.kind, e.name) for e in log.since(0)]
    assert kinds == [("measurement", "raw"), ("analysis", "fit")]
    assert log.since(0)[0].data == {"currents": [1.0, 2.0]}


def test_upstream_files_are_still_written(tmp_path: Path) -> None:
    log = EventLog()
    logger = _logger(tmp_path, log)
    session = logger.create_session("s1")
    session.log_measurement("raw", {"v": 1.0})
    logger.close_session("s1")
    assert any(tmp_path.rglob("*.jsonl"))


def test_events_carry_the_logger_routine_name(tmp_path: Path) -> None:
    log = EventLog()
    session = _logger(tmp_path, log).create_session("health/noise_floor")
    session.log_measurement("raw", {"v": 1.0})
    assert log.since(0)[0].routine == "health/noise_floor"
