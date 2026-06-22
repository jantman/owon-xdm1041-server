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


def get_poller(request: Request) -> Poller:
    poller: Poller = request.app.state.poller
    return poller


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
    m = await get_driver(request).read_measurement()
    return MeasurementOut(
        timestamp=time.time(), function=m.function.value, value=m.value, unit=m.unit
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
