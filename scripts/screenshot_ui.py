#!/usr/bin/env python3
"""Regenerate the README screenshots of the web UI against the mock meter.

This launches the full server with ``--mock`` (no hardware needed), drives a
headless Chromium browser through the three main pages, and writes PNGs into
``docs/images/``:

    docs/images/dashboard.png   the live readout
    docs/images/control.png     the control panel
    docs/images/history.png     recorded history + chart

The history page needs recorded readings to look like anything, so the script
keeps the dashboard open for a few seconds first: that streams live samples over
the WebSocket, which the recorder persists to a throwaway SQLite database. The
database, the chosen ports, and the server process are all temporary and cleaned
up on exit.

Usage:

    pip install -e ".[docs]"
    playwright install chromium     # one-time browser download
    python scripts/screenshot_ui.py

Run it whenever a UI change alters how these pages look, and commit the updated
PNGs alongside the change.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

# A fixed, generous viewport keeps the screenshots consistent run to run; the
# 2x scale factor makes them crisp on high-DPI displays without doubling layout.
VIEWPORT = {"width": 1100, "height": 820}
DEVICE_SCALE_FACTOR = 2

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "docs" / "images"

# How long to leave the dashboard streaming so the history chart has data.
SEED_SECONDS = 6.0
SERVER_START_TIMEOUT = 20.0


def _free_port() -> int:
    """Grab an ephemeral TCP port the OS is currently willing to hand out."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_server(base_url: str, timeout: float) -> None:
    """Block until the web UI answers, or raise if it never comes up."""
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(base_url, timeout=1.0) as resp:
                if resp.status == 200:
                    return
        except (urllib.error.URLError, OSError) as exc:  # not up yet
            last_error = exc
            time.sleep(0.25)
    raise RuntimeError(f"server at {base_url} did not start within {timeout}s: {last_error}")


@contextlib.contextmanager
def mock_server(db_path: Path):
    """Run ``serve --mock`` on private ports, yielding its base URL."""
    web_port = _free_port()
    env = {
        **os.environ,
        "OWON_USE_MOCK": "true",
        "OWON_WEB_HOST": "127.0.0.1",
        "OWON_WEB_PORT": str(web_port),
        # Park the SCPI socket on an ephemeral port so we never collide with a
        # real instance that may already own the default :5025.
        "OWON_SCPI_HOST": "127.0.0.1",
        "OWON_SCPI_PORT": str(_free_port()),
        "OWON_DATABASE_PATH": str(db_path),
        # Sample a little faster than default so the seed window fills quickly.
        "OWON_POLL_INTERVAL": "0.25",
    }
    base_url = f"http://127.0.0.1:{web_port}"
    proc = subprocess.Popen(
        [sys.executable, "-m", "owon_xdm1041_server", "serve", "--mock"],
        env=env,
        cwd=str(REPO_ROOT),
    )
    try:
        _wait_for_server(base_url, SERVER_START_TIMEOUT)
        yield base_url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


def capture(base_url: str, output_dir: Path) -> list[Path]:
    """Drive the browser through each page and write the PNGs."""
    # Imported lazily so the rest of the script (and its --help) works without
    # the optional ``docs`` extra installed.
    from playwright.sync_api import sync_playwright

    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch()
        except Exception as exc:  # pragma: no cover - environment-specific
            raise SystemExit(
                f"Could not launch Chromium ({exc}).\n"
                'Run `playwright install chromium` after `pip install -e ".[docs]"`.'
            ) from exc
        context = browser.new_context(viewport=VIEWPORT, device_scale_factor=DEVICE_SCALE_FACTOR)
        page = context.new_page()

        # --- Dashboard: wait for the first live value, then seed history. ---
        page.goto(f"{base_url}/", wait_until="networkidle")
        # The readout shows "—" until a reading streams in over the WebSocket.
        page.wait_for_function("document.getElementById('value').textContent.trim() !== '—'")
        dashboard_png = output_dir / "dashboard.png"
        page.screenshot(path=str(dashboard_png))
        written.append(dashboard_png)

        # Keep this page (and its WebSocket) open so the recorder accumulates
        # readings for the history chart.
        page.wait_for_timeout(int(SEED_SECONDS * 1000))

        # --- Control: server-rendered, ready on load. ---
        control_png = output_dir / "control.png"
        control = context.new_page()
        control.goto(f"{base_url}/control", wait_until="networkidle")
        control.screenshot(path=str(control_png))
        written.append(control_png)

        # --- History: wait for the chart to draw from the seeded readings. ---
        history_png = output_dir / "history.png"
        history = context.new_page()
        history.goto(f"{base_url}/history", wait_until="networkidle")
        # history.js hides #empty once /api/history returns rows.
        history.wait_for_function(
            "document.getElementById('empty').style.display === 'none'",
            timeout=10_000,
        )
        history.screenshot(path=str(history_png))
        written.append(history_png)

        context.close()
        browser.close()

    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Directory for the PNGs (default: {DEFAULT_OUTPUT_DIR}).",
    )
    args = parser.parse_args(argv)

    with tempfile.TemporaryDirectory(prefix="owon-shots-") as tmp:
        db_path = Path(tmp) / "screenshots.sqlite3"
        with mock_server(db_path) as base_url:
            written = capture(base_url, args.output_dir)

    print("Wrote:")
    for path in written:
        rel = path.relative_to(REPO_ROOT) if path.is_relative_to(REPO_ROOT) else path
        print(f"  {rel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
