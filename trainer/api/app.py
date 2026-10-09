"""FastAPI app: sessions, pads, voltages, routines, runs and the event stream."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Query, Request, WebSocket
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response, StreamingResponse
from starlette.websockets import WebSocketDisconnect

from stanza.models import PadType
from stanza.routines import get_registered_routines
from stanza.utils import load_device_config
from trainer.api.schemas import (
    AttemptInfo,
    CreateSession,
    DeviceInfo,
    EventOut,
    HintOut,
    LevelInfo,
    MeasureRequest,
    MeasureResponse,
    PadInfo,
    RoutineInfo,
    RunInfo,
    RunRequest,
    SessionInfo,
    SetVoltages,
)
from trainer.api.sessions import (
    AttemptClosed,
    AttemptRegistry,
    BadRequest,
    LabSession,
    SessionBusy,
    SessionRegistry,
    describe_routine,
)
from trainer.game.levels import LEVELS, get_level
from trainer.routines import register_builtin_routines


def get_registry(app: Any) -> SessionRegistry:
    registry: SessionRegistry = app.state.registry
    return registry


def create_app(devices_dir: Path, data_dir: Path) -> FastAPI:
    register_builtin_routines()
    app = FastAPI(title="Stanza Tune-Up Trainer API")
    app.state.registry = SessionRegistry(Path(devices_dir), Path(data_dir))
    app.state.attempts = AttemptRegistry(app.state.registry)

    @app.exception_handler(BadRequest)
    async def bad_request(_: Request, exc: BadRequest) -> JSONResponse:
        return JSONResponse(
            status_code=422, content={"detail": jsonable_encoder(exc.errors)}
        )

    @app.exception_handler(SessionBusy)
    async def busy(_: Request, __: SessionBusy) -> JSONResponse:
        return JSONResponse(
            status_code=409, content={"detail": "a routine is running on this session"}
        )

    @app.exception_handler(AttemptClosed)
    async def closed(_: Request, __: AttemptClosed) -> JSONResponse:
        return JSONResponse(
            status_code=409, content={"detail": "attempt already submitted"}
        )

    def attempts() -> AttemptRegistry:
        registry: AttemptRegistry = app.state.attempts
        return registry

    def attempt_or_404(aid: str) -> Any:
        try:
            return attempts().get(aid)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"no attempt {aid}") from None

    @app.get("/levels", response_model=list[LevelInfo])
    def levels() -> list[dict[str, Any]]:
        return [level.public() for level in LEVELS]

    @app.post(
        "/levels/{level_id}/attempts", status_code=201, response_model=AttemptInfo
    )
    def start_attempt(level_id: str) -> dict[str, Any]:
        try:
            level = get_level(level_id)
        except KeyError:
            raise HTTPException(
                status_code=404, detail=f"no level {level_id}"
            ) from None
        info: dict[str, Any] = attempts().start(level).info()
        return info

    @app.get("/attempts/{aid}", response_model=AttemptInfo)
    def get_attempt(aid: str) -> dict[str, Any]:
        info: dict[str, Any] = attempt_or_404(aid).info()
        return info

    @app.post("/attempts/{aid}/hints", response_model=HintOut)
    def hint(aid: str) -> HintOut:
        record = attempt_or_404(aid)
        text = record.attempt.next_hint()
        return HintOut(hint=text, hints_shown=record.attempt.hints_shown)

    @app.post("/attempts/{aid}/submit", response_model=AttemptInfo)
    def submit(aid: str) -> dict[str, Any]:
        attempt_or_404(aid)
        info: dict[str, Any] = attempts().submit(aid).info()
        return info

    def session_or_404(sid: str) -> LabSession:
        try:
            return get_registry(app).get(sid)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"no session {sid}") from None

    def session_info(s: LabSession) -> SessionInfo:
        groups = {
            name: [*g.gates, *(g.contacts or [])]
            for name, g in s.lab.config.groups.items()
        }
        return SessionInfo(
            id=s.id, device=s.device, title=s.lab.config.name, groups=groups
        )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/devices", response_model=list[DeviceInfo])
    def devices() -> list[DeviceInfo]:
        return [
            DeviceInfo(name=name, title=load_device_config(path).name)
            for name, path in get_registry(app).device_files().items()
        ]

    @app.post("/sessions", status_code=201, response_model=SessionInfo)
    def create_session(body: CreateSession) -> SessionInfo:
        return session_info(get_registry(app).create(body.device))

    @app.get("/sessions/{sid}", response_model=SessionInfo)
    def get_session(sid: str) -> SessionInfo:
        return session_info(session_or_404(sid))

    @app.delete("/sessions/{sid}", status_code=204)
    def delete_session(sid: str) -> Response:
        session_or_404(sid)
        get_registry(app).delete(sid)
        return Response(status_code=204)

    @app.get("/sessions/{sid}/pads", response_model=list[PadInfo])
    def pads(sid: str) -> list[PadInfo]:
        s = session_or_404(sid)
        groups = s.lab.config.groups
        out = []
        for name, cfg in s.channel_configs.items():
            member = next(
                (
                    g
                    for g, grp in groups.items()
                    if name in grp.gates or name in (grp.contacts or [])
                ),
                None,
            )
            low, high = cfg.voltage_range
            out.append(
                PadInfo(
                    name=name,
                    pad_type=str(PadType(cfg.pad_type)),
                    electrode_type=str(cfg.electrode_type.value),
                    v_lower_bound=low,
                    v_upper_bound=high,
                    controllable=cfg.control_channel is not None,
                    measurable=cfg.measure_channel is not None,
                    group=member,
                )
            )
        return out

    @app.get("/sessions/{sid}/voltages")
    def get_voltages(sid: str) -> dict[str, float]:
        return session_or_404(sid).voltages()

    @app.put("/sessions/{sid}/voltages")
    def put_voltages(sid: str, body: SetVoltages) -> dict[str, float]:
        return session_or_404(sid).set_voltages(body.voltages)

    @app.post("/sessions/{sid}/measure", response_model=MeasureResponse)
    def measure(sid: str, body: MeasureRequest) -> MeasureResponse:
        return MeasureResponse(currents=session_or_404(sid).measure(body.pads))

    @app.get("/sessions/{sid}/routines", response_model=list[RoutineInfo])
    def routines(sid: str) -> list[RoutineInfo]:
        session_or_404(sid)
        register_builtin_routines()
        return [
            describe_routine(n, f) for n, f in sorted(get_registered_routines().items())
        ]

    @app.post("/sessions/{sid}/runs", response_model=RunInfo)
    def start_run(sid: str, body: RunRequest, wait: bool = False) -> JSONResponse:
        s = session_or_404(sid)
        run = s.start_run(body.routine, body.parameters)
        if wait:
            run.done.wait()
            return JSONResponse(status_code=200, content=run.info())
        return JSONResponse(status_code=202, content=run.info())

    @app.get("/sessions/{sid}/runs", response_model=list[RunInfo])
    def list_runs(sid: str) -> list[dict[str, Any]]:
        return [r.info() for r in session_or_404(sid).runs.values()]

    @app.get("/sessions/{sid}/runs/{rid}", response_model=RunInfo)
    def get_run(sid: str, rid: str, wait: bool = False) -> dict[str, Any]:
        s = session_or_404(sid)
        run = s.runs.get(rid)
        if run is None:
            raise HTTPException(status_code=404, detail=f"no run {rid}")
        if wait:
            run.done.wait()
        return run.info()

    @app.get("/sessions/{sid}/events", response_model=list[EventOut])
    def events(sid: str, after: int = Query(0, ge=0)) -> list[dict[str, Any]]:
        return [e.to_dict() for e in session_or_404(sid).events.since(after)]

    @app.get("/sessions/{sid}/events/stream")
    def event_stream(
        sid: str,
        request: Request,
        after: int = Query(0, ge=0),
        follow: bool = True,
        until: str | None = None,
        last_event_id: int | None = Header(None, ge=0),
    ) -> StreamingResponse:
        """Server-sent events. ``follow=false`` replays and ends; ``until=<kind>``
        ends after the first event of that kind (e.g. ``run_finished``)."""
        s = session_or_404(sid)
        start = last_event_id if last_event_id is not None else after

        async def body() -> AsyncIterator[str]:
            async for event in _follow(
                s, start, follow, lambda: request.is_disconnected()
            ):
                yield (
                    f"id: {event['seq']}\nevent: {event['kind']}\n"
                    f"data: {json.dumps(event)}\n\n"
                )
                if until is not None and event["kind"] == until:
                    return

        return StreamingResponse(body(), media_type="text/event-stream")

    @app.websocket("/sessions/{sid}/stream")
    async def stream(websocket: WebSocket, sid: str, after: int = 0) -> None:
        try:
            s = get_registry(app).get(sid)
        except KeyError:
            await websocket.close(code=4404)
            return
        await websocket.accept()
        loop = asyncio.get_running_loop()
        wake = asyncio.Event()

        def notify(_: Any) -> None:
            try:
                loop.call_soon_threadsafe(wake.set)
            except RuntimeError:  # loop already closed
                pass

        unsubscribe = s.events.subscribe(notify)
        disconnected = asyncio.ensure_future(websocket.receive())
        cursor = max(0, after)
        try:
            while not disconnected.done():
                wake.clear()
                batch = s.events.since(cursor)
                for event in batch:
                    await websocket.send_json(event.to_dict())
                    cursor = event.seq
                if batch:
                    continue
                waiter = asyncio.ensure_future(wake.wait())
                await asyncio.wait(
                    {waiter, disconnected}, return_when=asyncio.FIRST_COMPLETED
                )
                waiter.cancel()
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            unsubscribe()
            disconnected.cancel()

    return app


async def _follow(
    session: LabSession,
    cursor: int,
    follow: bool,
    disconnected: Any,
) -> AsyncIterator[dict[str, Any]]:
    """Yield events after ``cursor`` in order; with ``follow``, wait for more."""
    loop = asyncio.get_running_loop()
    wake = asyncio.Event()

    def notify(_: Any) -> None:
        try:
            loop.call_soon_threadsafe(wake.set)
        except RuntimeError:  # loop already closed
            pass

    unsubscribe = session.events.subscribe(notify)
    try:
        while True:
            wake.clear()
            batch = session.events.since(cursor)
            for event in batch:
                yield event.to_dict()
                cursor = event.seq
            if batch:
                continue
            if not follow or await disconnected():
                return
            try:
                await asyncio.wait_for(wake.wait(), timeout=0.5)
            except TimeoutError:
                pass
    finally:
        unsubscribe()
