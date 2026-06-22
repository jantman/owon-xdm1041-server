"""Server-rendered HTML routes (Jinja2 + HTMX).

The dashboard streams live readings over the WebSocket; the control page posts to
fragment endpoints that perform the action and return an updated state partial
(HTMX swaps it in place); the history page fetches ``/api/history`` and charts it.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from ..device.commands import Rate
from ..device.driver import Driver
from .api import _FUNCTION_LABELS, _parse_function, _parse_rate, get_driver

_WEB_DIR = Path(__file__).parent
TEMPLATES_DIR = _WEB_DIR / "templates"
STATIC_DIR = _WEB_DIR / "static"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
html_router = APIRouter()

_RATE_LABELS: dict[Rate, str] = {Rate.SLOW: "Slow", Rate.MEDIUM: "Medium", Rate.FAST: "Fast"}


async def _state_context(driver: Driver) -> dict[str, object]:
    state = await driver.read_state()
    return {
        "function": state.function.name,
        "rate": state.rate.name,
        "auto_range": state.auto_range,
        "range": state.range,
    }


def _state_response(request: Request, state: dict[str, object]) -> HTMLResponse:
    return templates.TemplateResponse(request, "_state.html", {"state": state})


@html_router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "dashboard.html")


@html_router.get("/control", response_class=HTMLResponse)
async def control(request: Request) -> HTMLResponse:
    driver = get_driver(request)
    context = {
        "functions": [(f.name, label) for f, label in _FUNCTION_LABELS.items()],
        "rates": [(r.name, _RATE_LABELS[r]) for r in Rate],
        "state": await _state_context(driver),
    }
    return templates.TemplateResponse(request, "control.html", context)


@html_router.post("/control/function", response_class=HTMLResponse)
async def control_set_function(
    request: Request,
    function: str = Form(...),
    rtd_type: str = Form("KITS90"),
) -> HTMLResponse:
    driver = get_driver(request)
    await driver.set_function(_parse_function(function), rtd_type=rtd_type)
    return _state_response(request, await _state_context(driver))


@html_router.post("/control/rate", response_class=HTMLResponse)
async def control_set_rate(request: Request, rate: str = Form(...)) -> HTMLResponse:
    driver = get_driver(request)
    await driver.set_rate(_parse_rate(rate))
    return _state_response(request, await _state_context(driver))


@html_router.post("/control/auto-range", response_class=HTMLResponse)
async def control_auto_range(request: Request) -> HTMLResponse:
    driver = get_driver(request)
    await driver.enable_auto_range()
    return _state_response(request, await _state_context(driver))


@html_router.get("/history", response_class=HTMLResponse)
async def history_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "history.html")
