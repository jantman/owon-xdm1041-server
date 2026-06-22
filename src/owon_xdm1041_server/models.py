"""Shared data models used across the web, poller, and storage layers."""

from __future__ import annotations

from dataclasses import dataclass

from .device.driver import Measurement


@dataclass(frozen=True)
class Reading:
    """A timestamped measurement, ready to broadcast or persist.

    ``function`` is the meter's device string (e.g. ``VOLT``), so a reading is
    self-describing and correctly attributed even across front-panel changes.
    """

    timestamp: float
    function: str
    value: float
    unit: str

    @classmethod
    def from_measurement(cls, measurement: Measurement, timestamp: float) -> Reading:
        return cls(
            timestamp=timestamp,
            function=measurement.function.value,
            value=measurement.value,
            unit=measurement.unit,
        )
