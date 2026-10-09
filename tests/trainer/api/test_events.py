"""Event log and JSON conversion for the API (trainer/api/events.py)."""

import math
import threading
from dataclasses import dataclass

import numpy as np
import pytest

from trainer.api.events import EventLog, jsonable


def test_events_get_contiguous_sequence_numbers() -> None:
    log = EventLog()
    a = log.append("run_started", routine="r", name="x", data={})
    b = log.append("measurement", routine="r", name="y", data={"v": 1})
    assert (a.seq, b.seq) == (1, 2)
    assert [e.seq for e in log.since(0)] == [1, 2]
    assert [e.seq for e in log.since(1)] == [2]
    assert log.since(2) == []
    assert log.last_seq == 2


def test_since_rejects_negative_cursor() -> None:
    with pytest.raises(ValueError, match="cursor"):
        EventLog().since(-1)


def test_event_to_dict_is_json_ready() -> None:
    log = EventLog(clock=lambda: 1.5)
    event = log.append(
        "sweep_point", routine="r", name="s", data={"x": np.array([1.0])}
    )
    assert event.to_dict() == {
        "seq": 1,
        "time": 1.5,
        "kind": "sweep_point",
        "routine": "r",
        "name": "s",
        "data": {"x": [1.0]},
    }


def test_concurrent_appends_lose_nothing() -> None:
    log = EventLog()

    def writer() -> None:
        for _ in range(500):
            log.append("measurement", routine="r", name="n", data={})

    threads = [threading.Thread(target=writer) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert [e.seq for e in log.since(0)] == list(range(1, 4001))


def test_listeners_are_notified_and_can_unsubscribe() -> None:
    log = EventLog()
    seen: list[int] = []
    unsubscribe = log.subscribe(lambda e: seen.append(e.seq))
    log.append("measurement", routine="r", name="n", data={})
    unsubscribe()
    log.append("measurement", routine="r", name="n", data={})
    assert seen == [1]


def test_unknown_kind_rejected() -> None:
    with pytest.raises(ValueError, match="kind"):
        EventLog().append("gossip", routine="r", name="n", data={})


@dataclass
class _Point:
    x: float


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (np.float64(1.5), 1.5),
        (np.int64(3), 3),
        (np.bool_(True), True),
        (np.array([[1, 2], [3, 4]]), [[1, 2], [3, 4]]),
        ((1, 2), [1, 2]),
        ({1: "a"}, {"1": "a"}),
        (float("nan"), None),
        (math.inf, None),
        (np.array([np.nan, 1.0]), [None, 1.0]),
        (_Point(2.0), {"x": 2.0}),
        (None, None),
        ("s", "s"),
    ],
)
def test_jsonable(value: object, expected: object) -> None:
    assert jsonable(value) == expected


def test_jsonable_falls_back_to_repr_for_unknown_objects() -> None:
    class Odd:
        def __repr__(self) -> str:
            return "Odd()"

    assert jsonable(Odd()) == "Odd()"
