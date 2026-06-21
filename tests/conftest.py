"""Shared pytest fixtures.

The mock-meter and app fixtures land alongside their implementations in later
phases; this module currently provides configuration helpers only.
"""

from __future__ import annotations

import pytest

from owon_xdm1041_server.config import Settings


@pytest.fixture
def settings(tmp_path: object) -> Settings:
    """A Settings instance wired for hardware-free testing against the mock meter."""
    return Settings(use_mock=True, database_path=str(tmp_path) + "/test.sqlite3")  # type: ignore[call-arg]
