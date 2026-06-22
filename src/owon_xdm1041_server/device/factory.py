"""Construct the device stack (transport → manager → driver) from settings."""

from __future__ import annotations

from ..config import Settings
from .driver import Driver
from .manager import DeviceManager
from .mock import MockTransport
from .transport import SerialTransport, Transport


def build_transport(settings: Settings) -> Transport:
    """Build the appropriate transport for ``settings`` (mock or real serial)."""
    if settings.use_mock:
        return MockTransport()
    return SerialTransport(settings.serial_port, settings.baud_rate)


def build_driver(settings: Settings) -> tuple[DeviceManager, Driver]:
    """Build a connected-on-start manager and driver pair from ``settings``."""
    transport = build_transport(settings)
    manager = DeviceManager(transport, default_timeout=settings.serial_timeout)
    return manager, Driver(manager)
