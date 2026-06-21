"""Runtime configuration, loaded from environment variables and/or a TOML file.

Settings are read from ``OWON_*`` environment variables (see ``env_prefix``) or a
TOML file pointed at by ``OWON_CONFIG_FILE``. All fields have sensible defaults so
the server can run against the mock meter with zero configuration.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Top-level server configuration."""

    model_config = SettingsConfigDict(env_prefix="OWON_", env_file=None, extra="ignore")

    # --- Device / serial ---
    serial_port: str = Field(
        default="/dev/owon-xdm1041",
        description="Serial device path. The packaged udev rule creates this stable symlink.",
    )
    baud_rate: int = Field(default=115200, description="Serial baud rate (XDM1041 uses 115200).")
    serial_timeout: float = Field(
        default=2.0, description="Per-transaction read timeout, in seconds."
    )
    use_mock: bool = Field(
        default=False,
        description="Use the in-memory mock meter instead of a real serial device.",
    )

    # --- Polling ---
    poll_interval: float = Field(
        default=0.5,
        description="Seconds between samples while at least one live client is watching.",
    )

    # --- SCPI TCP server ---
    scpi_host: str = Field(default="0.0.0.0", description="Bind address for the raw SCPI socket.")
    scpi_port: int = Field(default=5025, description="TCP port for the raw SCPI socket.")

    # --- Web server ---
    web_host: str = Field(default="0.0.0.0", description="Bind address for the web UI.")
    web_port: int = Field(default=8080, description="TCP port for the web UI.")

    # --- Storage ---
    database_path: str = Field(
        default="owon_xdm1041.sqlite3",
        description="Path to the SQLite database file for recorded readings.",
    )


def load_settings() -> Settings:
    """Build a :class:`Settings` instance from the environment."""
    return Settings()
