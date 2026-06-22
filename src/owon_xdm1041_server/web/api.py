"""REST + WebSocket API routes.

Control endpoints read and change the meter through the shared Driver; the
``/ws/live`` WebSocket streams readings from the on-demand Poller. Subscribing to
the socket is what starts polling, so the meter is only sampled while a client is
actually watching.
"""

from __future__ import annotations

import time
from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from ..device.commands import Function, Rate
from ..device.driver import Driver
from ..models import Aggregate, Reading
from ..storage.db import Database
from .poller import Poller

router = APIRouter()


class MeasurementOut(BaseModel):
    timestamp: float
    function: str
    value: float
    unit: str


class StateOut(BaseModel):
    function: str
    rate: str
    auto_range: bool
    range: str | None


class SmoothedOut(BaseModel):
    function: str
    unit: str
    value: float | None
    samples: int
    window_seconds: float
    min: float | None
    max: float | None


class StatusOut(BaseModel):
    timestamp: float
    function: str
    value: float
    unit: str
    state: StateOut
    smoothed: SmoothedOut


class FunctionOption(BaseModel):
    name: str
    label: str


class FunctionIn(BaseModel):
    function: str
    rtd_type: str = "KITS90"


class RateIn(BaseModel):
    rate: str


_FUNCTION_LABELS: dict[Function, str] = {
    Function.VOLT_DC: "DC Voltage",
    Function.VOLT_AC: "AC Voltage",
    Function.CURR_DC: "DC Current",
    Function.CURR_AC: "AC Current",
    Function.RESISTANCE: "Resistance",
    Function.CAPACITANCE: "Capacitance",
    Function.FREQ: "Frequency",
    Function.PERIOD: "Period",
    Function.DIODE: "Diode",
    Function.CONTINUITY: "Continuity",
    Function.TEMPERATURE: "Temperature",
}


def get_driver(request: Request) -> Driver:
    driver: Driver = request.app.state.driver
    return driver


def get_database(request: Request) -> Database:
    database: Database | None = request.app.state.db
    if database is None:
        raise HTTPException(status_code=503, detail="Persistence is disabled")
    return database


def _optional_database(request: Request) -> Database | None:
    database: Database | None = request.app.state.db
    return database


async def _take_reading(driver: Driver, database: Database | None) -> Reading:
    """Take a fresh on-demand reading and persist it when storage is available.

    Persisting these reads means an HTTP client that polls ``/api/status`` or
    ``/api/measurement`` keeps feeding history, so the smoothing window has data
    even when no ``/ws/live`` client is driving the poller.
    """
    m = await driver.read_measurement()
    reading = Reading.from_measurement(m, time.time())
    if database is not None:
        await database.insert_reading(reading)
    return reading


def _validate_seconds(seconds: float) -> None:
    if seconds <= 0:
        raise HTTPException(status_code=422, detail="seconds must be positive")


def _parse_function(name: str) -> Function:
    try:
        return Function[name]
    except KeyError:
        raise HTTPException(status_code=422, detail=f"Unknown function: {name!r}") from None


def _parse_rate(name: str) -> Rate:
    try:
        return Rate[name]
    except KeyError:
        raise HTTPException(status_code=422, detail=f"Unknown rate: {name!r}") from None


async def _read_state(driver: Driver) -> StateOut:
    state = await driver.read_state()
    return StateOut(
        function=state.function.name,
        rate=state.rate.name,
        auto_range=state.auto_range,
        range=state.range,
    )


@router.get("/api/identify")
async def identify(request: Request) -> dict[str, str]:
    return {"identity": await get_driver(request).identify()}


@router.get("/api/functions")
async def functions() -> list[FunctionOption]:
    return [FunctionOption(name=f.name, label=label) for f, label in _FUNCTION_LABELS.items()]


@router.get("/api/state")
async def state(request: Request) -> StateOut:
    return await _read_state(get_driver(request))


@router.get("/api/measurement")
async def measurement(request: Request) -> MeasurementOut:
    reading = await _take_reading(get_driver(request), _optional_database(request))
    return MeasurementOut(
        timestamp=reading.timestamp,
        function=reading.function,
        value=reading.value,
        unit=reading.unit,
    )


@router.get("/api/measurement/smoothed")
async def measurement_smoothed(
    request: Request, seconds: float = 60.0, function: str | None = None
) -> SmoothedOut:
    _validate_seconds(seconds)
    database = get_database(request)
    reading = await _take_reading(get_driver(request), database)
    func_value = _parse_function(function).value if function is not None else reading.function
    agg = await database.aggregate(since=reading.timestamp - seconds, function=func_value)
    return SmoothedOut(
        function=func_value,
        unit=reading.unit,
        value=agg.mean,
        samples=agg.count,
        window_seconds=seconds,
        min=agg.min,
        max=agg.max,
    )


@router.get("/api/status")
async def status(request: Request, seconds: float = 60.0) -> StatusOut:
    _validate_seconds(seconds)
    driver = get_driver(request)
    database = _optional_database(request)
    reading = await _take_reading(driver, database)
    state = await _read_state(driver)
    if database is not None:
        agg = await database.aggregate(since=reading.timestamp - seconds, function=reading.function)
    else:
        agg = Aggregate(count=0, mean=None, min=None, max=None, first_ts=None, last_ts=None)
    smoothed = SmoothedOut(
        function=reading.function,
        unit=reading.unit,
        value=agg.mean,
        samples=agg.count,
        window_seconds=seconds,
        min=agg.min,
        max=agg.max,
    )
    return StatusOut(
        timestamp=reading.timestamp,
        function=reading.function,
        value=reading.value,
        unit=reading.unit,
        state=state,
        smoothed=smoothed,
    )


@router.post("/api/function")
async def set_function(body: FunctionIn, request: Request) -> StateOut:
    driver = get_driver(request)
    await driver.set_function(_parse_function(body.function), rtd_type=body.rtd_type)
    return await _read_state(driver)


@router.post("/api/rate")
async def set_rate(body: RateIn, request: Request) -> StateOut:
    driver = get_driver(request)
    await driver.set_rate(_parse_rate(body.rate))
    return await _read_state(driver)


@router.post("/api/auto-range")
async def enable_auto_range(request: Request) -> StateOut:
    driver = get_driver(request)
    await driver.enable_auto_range()
    return await _read_state(driver)


@router.get("/api/history")
async def history(
    request: Request,
    since: float | None = None,
    until: float | None = None,
    function: str | None = None,
    limit: int = 1000,
) -> list[MeasurementOut]:
    database = get_database(request)
    function_value = _parse_function(function).value if function is not None else None
    readings = await database.history(
        since=since, until=until, function=function_value, limit=limit
    )
    return [
        MeasurementOut(timestamp=r.timestamp, function=r.function, value=r.value, unit=r.unit)
        for r in readings
    ]


@router.websocket("/ws/live")
async def live(websocket: WebSocket) -> None:
    poller: Poller = websocket.app.state.poller
    await websocket.accept()
    try:
        async with poller.subscribe() as subscription:
            async for reading in subscription:
                await websocket.send_json(asdict(reading))
    except WebSocketDisconnect:
        pass
