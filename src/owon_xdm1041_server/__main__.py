"""Console entrypoint.

Phase 1 provides the ``probe`` subcommand, which connects to the meter (real or
mock) and prints its identity, state, and a reading. The SCPI server and web app
land in later phases.
"""

from __future__ import annotations

import argparse
import asyncio

from .config import load_settings
from .device.factory import build_driver
from .device.probe import run_probe


async def _probe(use_mock: bool) -> int:
    settings = load_settings()
    if use_mock:
        settings = settings.model_copy(update={"use_mock": True})
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
    args = parser.parse_args(argv)

    if args.command == "probe":
        return asyncio.run(_probe(args.mock))
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
