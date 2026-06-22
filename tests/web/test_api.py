"""Tests for the REST + WebSocket API."""

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
    # The manager auto-connects on first use, so no explicit start is needed.
    _, driver = build_driver(Settings(use_mock=True))  # type: ignore[call-arg]
    poller = Poller(driver, interval=0.01)
    with TestClient(create_app(driver, poller)) as test_client:
        yield test_client


def test_identify(client: TestClient) -> None:
    resp = client.get("/api/identify")
    assert resp.status_code == 200
    assert resp.json()["identity"].startswith("OWON,XDM1041")


def test_get_state(client: TestClient) -> None:
    body = client.get("/api/state").json()
    assert body == {"function": "VOLT_DC", "rate": "MEDIUM", "auto_range": True, "range": "5V"}


def test_get_measurement(client: TestClient) -> None:
    body = client.get("/api/measurement").json()
    assert body["function"] == "VOLT"
    assert body["unit"] == "V"
    assert isinstance(body["value"], float)


def test_list_functions(client: TestClient) -> None:
    names = {item["name"] for item in client.get("/api/functions").json()}
    assert {"VOLT_DC", "RESISTANCE", "TEMPERATURE"} <= names


def test_set_function(client: TestClient) -> None:
    body = client.post("/api/function", json={"function": "RESISTANCE"}).json()
    assert body["function"] == "RESISTANCE"


def test_set_function_invalid(client: TestClient) -> None:
    assert client.post("/api/function", json={"function": "BOGUS"}).status_code == 422


def test_set_rate(client: TestClient) -> None:
    body = client.post("/api/rate", json={"rate": "SLOW"}).json()
    assert body["rate"] == "SLOW"


def test_set_rate_invalid(client: TestClient) -> None:
    assert client.post("/api/rate", json={"rate": "BOGUS"}).status_code == 422


def test_enable_auto_range(client: TestClient) -> None:
    body = client.post("/api/auto-range").json()
    assert body["auto_range"] is True


def test_websocket_streams_readings(client: TestClient) -> None:
    with client.websocket_connect("/ws/live") as ws:
        data = ws.receive_json()
        assert set(data) == {"timestamp", "function", "value", "unit"}
        assert data["unit"] == "V"
