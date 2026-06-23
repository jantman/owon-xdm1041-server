# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A single-process asyncio server for the OWON XDM1041 bench multimeter. It owns one USB-serial
connection and exposes the meter two ways simultaneously: a raw-socket **SCPI server** on TCP `:5025`
(for pyvisa/NI-VISA/sigrok) and a **FastAPI web UI / HTTP API** on `:8080` (live dashboard, control
panel, recorded history). Target deployment is a Raspberry Pi under systemd.

`docs/DESIGN.md` is the authoritative design rationale — read it before any non-trivial change.

## Commands

```bash
pip install -e ".[dev]"          # install with the test/lint toolchain

ruff check . && ruff format --check .
mypy                              # strict mode, packages configured in pyproject
pytest                            # full suite, hardware-free against the mock meter
pytest tests/web/test_api.py::test_status   # run a single test
pytest -m hardware                # opt-in tests needing a real meter (deselected by default)

owon-xdm1041-server serve --mock  # run the whole server against the in-memory mock
owon-xdm1041-server probe --mock  # connect, print identity + state + one reading
```

CI (`.github/workflows/ci.yml`) runs ruff check, ruff format --check, mypy, and pytest — all four
must pass. `pytest` enforces `--cov-fail-under=85`, a 30s per-test timeout, and `asyncio_mode=auto`
(no `@pytest.mark.asyncio` needed). Nothing in the suite touches hardware.

## Architecture: the single-owner serial port

The USB serial port allows exactly one owner, so **every path to the meter goes through one
`DeviceManager`** (`device/manager.py`). It serialises all access behind an `asyncio.Lock` as
single-flight transactions (write → read), with per-command timeouts and transparent reconnect on
transport failure. Nothing else opens the port. The manager keeps the meter in LOCAL mode
(`SYST:LOC`) on connect so the physical front panel is never locked out during long-running sessions.

Layering (each layer only talks to the one below it):

- **`device/transport.py`** — abstract `Transport` + `SerialTransport` (pyserial, blocking I/O run in
  threads via `asyncio.to_thread`). The mock counterpart is `device/mock.py` (`MockTransport`), a
  stateful in-memory fake meter — it is the keystone of the hardware-free test suite.
- **`device/manager.py`** — `DeviceManager`, the arbiter. `query()` / `write()`.
- **`device/driver.py`** — `Driver`: typed high-level operations (`read_measurement`, `read_state`,
  `set_function`, etc.).
- **`device/commands.py`** — SCPI strings and `Function`/`Rate` enums with `from_device()` parsing.
- **`device/factory.py`** — `build_driver(settings)` wires transport → manager → driver (mock vs real).

`runner.py` (`serve()`) composes everything: builds components, starts the SCPI server and uvicorn,
and shares the one `DeviceManager` across both. `__main__.py` is the `argparse` CLI (`probe` / `serve`).

### Read-through state (critical invariant)

The meter is the **single source of truth**; cached state is never trusted across idle gaps. The
front panel can change function/range/rate at any time and the meter pushes no notification. Therefore:

- `Driver.read_measurement()` re-reads the active function every call so each value is self-describing.
- The poller re-reads function + value each cycle, so the UI tracks front-panel changes within one poll.
- After a control write, re-read the setting rather than assuming the write took.

Preserve this when adding driver methods or endpoints — do not introduce a long-lived authoritative
mode cache. See `docs/DESIGN.md` "External state changes".

### Web / polling (`web/`)

- **`poller.py`** — `Poller` is **on-demand and reference-counted**: the background sampling task
  starts when the first `/ws/live` subscriber arrives and stops when the last leaves. The meter/bus is
  idle when nobody is watching. Poll errors are logged and the loop continues (a malformed line must
  not kill live clients). Samples publish to a `Broadcaster` (`broadcast.py`) that fans out to
  WebSocket clients and the recorder.
- **`recorder.py`** — subscribes to the broadcaster and writes readings to SQLite (`storage/db.py`,
  aiosqlite). Wired up by the app lifespan in `app.py` only when a `Database` is supplied.
- **`api.py`** — REST + WebSocket routes. Note `_take_reading()` persists each `/api/status` and
  `/api/measurement` read, so an HTTP client that polls keeps the smoothing window fresh without any
  live `/ws/live` viewer. Endpoints needing persistence return 503 when the DB is disabled.
- **`app.py`** — `create_app()` factory; shared `driver`/`poller`/`db` live on `app.state`.
- **`views.py`** + `templates/` (Jinja2 + HTMX) + `static/` — server-rendered pages. The UI loads HTMX
  from a CDN; for an offline Pi, vendor it into `web/static/` and update `base.html`.

The README embeds screenshots of the dashboard, control, and history pages (`docs/images/*.png`),
generated by `scripts/screenshot_ui.py` driving a headless browser against the mock meter. **After
any significant change to the look of these pages** (templates, `static/style.css`, or the JS that
renders them), regenerate and commit the screenshots so the README stays accurate:

```bash
pip install -e ".[docs]" && playwright install chromium   # one-time setup
python scripts/screenshot_ui.py
```

## Conventions

- Python 3.12+, `from __future__ import annotations` everywhere, full type hints (mypy strict).
- ruff line length 100; rule set `E,F,W,I,UP,B,C4,SIM,RUF` (tests ignore `B`).
- Frozen dataclasses for value objects (`Measurement`, `DeviceState`, `Reading`).
- All config is `OWON_`-prefixed env vars via pydantic-settings (`config.py`); every field has a
  default so the mock runs with zero configuration.
- Every change lands with its tests; the suite must stay hardware-free (extend `MockTransport` rather
  than reaching for real hardware).
