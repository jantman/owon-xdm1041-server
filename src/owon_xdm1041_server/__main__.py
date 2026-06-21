"""Console entrypoint.

Phase 0 placeholder: wiring up the DeviceManager, SCPI server, and web app lands
in later phases. For now this just confirms configuration loads.
"""

from __future__ import annotations

from .config import load_settings


def main() -> None:
    settings = load_settings()
    print(f"owon-xdm1041-server (mock={settings.use_mock}, port={settings.serial_port})")
    print("Not yet runnable — see docs/DESIGN.md for the implementation roadmap.")


if __name__ == "__main__":
    main()
