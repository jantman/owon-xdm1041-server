"""Console entrypoint.

``probe`` connects to the meter (real or mock) and prints its identity, state,
and a reading. ``serve`` runs the full server: the raw SCPI socket and the web
UI, sharing one connection to the meter.
"""

from __future__ import annotations

import argparse
import asyncio

from . import runner
from .config import Settings, load_settings
from .device.factory import build_driver
from .device.probe import run_probe


def _settings_for(use_mock: bool) -> Settings:
    settings = load_settings()
    if use_mock:
        settings = settings.model_copy(update={"use_mock": True})
    return settings


async def _probe(use_mock: bool) -> int:
    settings = _settings_for(use_mock)
    manager, driver = build_driver(settings)
    await manager.start()
    try:
        summary = await run_probe(driver)
    finally:
        await manager.stop()
    for key, value in summary.items():
        print(f"{key:>10}: {value}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="owon-xdm1041-server")
    sub = parser.add_subparsers(dest="command")
    probe = sub.add_parser("probe", help="Connect to the meter and print its state.")
    probe.add_argument("--mock", action="store_true", help="Use the in-memory mock meter.")
    serve = sub.add_parser("serve", help="Run the SCPI server and web UI.")
    serve.add_argument("--mock", action="store_true", help="Use the in-memory mock meter.")
    args = parser.parse_args(argv)

    if args.command == "probe":
        return asyncio.run(_probe(args.mock))
    if args.command == "serve":
        asyncio.run(runner.serve(_settings_for(args.mock)))
        return 0
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
