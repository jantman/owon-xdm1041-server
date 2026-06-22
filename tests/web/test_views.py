"""Tests for the server-rendered HTML views."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from owon_xdm1041_server.config import Settings
from owon_xdm1041_server.device.factory import build_driver
from owon_xdm1041_server.web.app import create_app
from owon_xdm1041_server.web.poller import Poller


@pytest.fixture
def client() -> Iterator[TestClient]:
    _, driver = build_driver(Settings(use_mock=True))  # type: ignore[call-arg]
    poller = Poller(driver, interval=0.01)
    with TestClient(create_app(driver, poller)) as test_client:
        yield test_client


def test_dashboard_page(client: TestClient) -> None:
    resp = client.get("/")
    assert resp.status_code == 200
    assert 'id="value"' in resp.text
    assert "/static/dashboard.js" in resp.text


def test_control_page_shows_current_state(client: TestClient) -> None:
    resp = client.get("/control")
    assert resp.status_code == 200
    # The mock starts in DC volts at medium rate; those should be reflected.
    assert "VOLT_DC" in resp.text
    assert 'id="state"' in resp.text


def test_control_set_function_returns_updated_partial(client: TestClient) -> None:
    resp = client.post("/control/function", data={"function": "RESISTANCE"})
    assert resp.status_code == 200
    assert 'id="state"' in resp.text
    assert "RESISTANCE" in resp.text


def test_control_set_function_invalid(client: TestClient) -> None:
    assert client.post("/control/function", data={"function": "BOGUS"}).status_code == 422


def test_control_set_rate(client: TestClient) -> None:
    resp = client.post("/control/rate", data={"rate": "SLOW"})
    assert resp.status_code == 200
    assert "SLOW" in resp.text


def test_control_auto_range(client: TestClient) -> None:
    resp = client.post("/control/auto-range")
    assert resp.status_code == 200
    assert "on" in resp.text


def test_history_page(client: TestClient) -> None:
    resp = client.get("/history")
    assert resp.status_code == 200
    assert 'id="chart"' in resp.text
    assert "/static/history.js" in resp.text


def test_api_docs_page(client: TestClient) -> None:
    resp = client.get("/api")
    assert resp.status_code == 200
    # Documents the key endpoints and points at the machine-readable spec.
    assert "/api/status" in resp.text
    assert "/api/measurement/smoothed" in resp.text
    assert "/ws/live" in resp.text
    assert "/openapi.json" in resp.text


def test_nav_links_to_api_docs(client: TestClient) -> None:
    assert 'href="/api"' in client.get("/").text


def test_openapi_schema_available(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    assert "/api/status" in schema["paths"]
    assert "/api/measurement/smoothed" in schema["paths"]


def test_static_assets_served(client: TestClient) -> None:
    assert client.get("/static/style.css").status_code == 200
    assert client.get("/static/dashboard.js").status_code == 200
    assert client.get("/static/history.js").status_code == 200
