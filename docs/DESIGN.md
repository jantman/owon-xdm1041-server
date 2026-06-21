# OWON XDM1041 Server — Design & Implementation Plan

A Python server for the OWON XDM1041 bench multimeter that provides:

1. A **network SCPI server** (raw TCP socket, port 5025) that passes commands
   through to the meter over USB serial.
2. A **web UI** for live monitoring, control, and historical charts.

## Target environment

- **Runtime:** Raspberry Pi (or any Linux host) wired to the meter via USB,
  managed as a **systemd** service.
- **Python:** 3.12 (async-first).
- **Device:** XDM1041 enumerates as a USB-serial port (`/dev/ttyUSB*` or
  `/dev/ttyACM*`), **115200 baud, 8N1**, SCPI commands terminated with `\n`.

## Prior art to lean on

- [TheHWcave/OWON-XDM1041](https://github.com/TheHWcave/OWON-XDM1041) — reverse-engineered SCPI command list.
- [ElDuderino/XDM1041Python](https://github.com/ElDuderino/XDM1041Python) — a working Python driver to validate command syntax against.

---

## The central constraint: single-access serial port

The USB serial port allows exactly **one** owner. Both the network SCPI server
and the web UI (live poller + manual control) must reach the meter, so a single
in-process **DeviceManager** owns the port and arbitrates all access. Every
other component talks to the meter *only* through it.

```
                    ┌─────────────────────────────────────────┐
   SCPI clients ───►│  SCPI TCP server (:5025)                 │
 (pyvisa, sigrok)   ├─────────────────────────────────────────┤
                    │            DeviceManager                 │
   Web browser ────►│  Web (FastAPI)   ◄── poller ──► (arbiter)│──► USB serial ──► XDM1041
   (HTMX + WS)      │  REST + WebSocket                        │
                    ├─────────────────────────────────────────┤
                    │  Recorder ──► SQLite                     │
                    └─────────────────────────────────────────┘
```

The DeviceManager runs each request as a **single-flight transaction**
(write command → read response) guarded by an `asyncio.Lock`/queue, with
per-command timeouts and automatic reconnect. Any cached state is treated as a
**last-known snapshot, never authoritative** — see "External state changes".

---

## External state changes (front-panel use, long-running drift)

The server may run for **weeks or months**, and the meter's physical buttons can
be used at any time between web/SCPI sessions. The meter does **not** push
notifications when its function/range/rate changes from the front panel, so the
server must never assume its in-memory view is current. Rules:

- **The meter is the single source of truth.** Cached state is only a last-known
  snapshot used to avoid redundant reads within one coherent operation — it is
  never trusted across idle gaps or presented as authoritative.
- **Read-through on every session boundary.** When a web client opens the control
  panel (or a live view starts), the server re-queries the meter's actual
  function/range/rate and renders *that*, not a cache.
- **Interpret every reading against the live function.** A raw value is
  meaningless without its mode, so each measurement read also resolves the
  current function/unit; the recorder tags each sample with the function actually
  in effect, so a front-panel change mid-log is attributed correctly.
- **The on-demand poller auto-tracks the panel.** Because it re-reads function +
  value each cycle, the live UI reflects physical changes within one poll
  interval; a detected change emits an event the UI updates from.
- **After any write, verify don't assume.** Following a control command, re-read
  the relevant setting (after a short settle delay) rather than trusting that the
  write took — front-panel and remote writes can race.
- **Don't strand the meter in remote-lockout.** Verify in Phase 1 whether the
  XDM1041 enters a front-panel lockout under serial control; if so, ensure the
  panel stays usable (e.g. issue `SYSTem:LOCal`/avoid lockout). The
  [ESP32 owon-xdm-remote](https://github.com/Elektroarzt/owon-xdm-remote) project
  is evidence that long-running coexistence with the front panel works.

---

## Architecture

Single asyncio process. Components:

- **transport** — async serial I/O (`pyserial-asyncio`), framing, reconnect.
- **DeviceManager** — the arbiter: `query(cmd)`, `write(cmd)`, locking, timeouts,
  reconnect, cached device state.
- **driver** — high-level wrappers over SCPI (`set_function`, `set_range`,
  `read_measurement`, `identify`, …) + function/unit enums.
- **mock device** — in-memory fake meter so the whole stack runs and tests pass
  **without hardware**.
- **scpi server** — asyncio TCP server on `:5025`; each newline-terminated line
  is forwarded through the DeviceManager. Multiple clients supported.
- **web** — FastAPI app: REST control endpoints, a WebSocket that streams live
  readings, HTMX server-rendered pages.
- **poller** — samples the meter at a configurable interval and publishes
  readings to a broadcaster (fan-out to WS clients + recorder). **On-demand:**
  polling starts when the first web client subscribes to the live stream and
  stops when the last one disconnects, so the meter/bus is idle when nobody is
  watching. (Rate is configurable; continuous mode can be added later if wanted.)
- **recorder + storage** — subscribes to the reading stream, writes to SQLite;
  serves history for charts.
- **config** — TOML + env (`pydantic-settings`): port path, baud, poll interval,
  bind addresses/ports, DB path.

### Proposed layout

```
src/owon_xdm1041_server/
  __main__.py          # entrypoint: wire up + run all servers
  config.py
  device/
    transport.py       # pyserial-asyncio transport + reconnect
    manager.py         # DeviceManager arbiter (lock, transactions, state cache)
    driver.py          # high-level SCPI wrappers
    commands.py        # SCPI constants, function/range/rate enums
    mock.py            # fake meter
  scpi/server.py       # TCP :5025 passthrough
  web/
    app.py             # FastAPI factory
    api.py             # REST + WebSocket routes
    poller.py
    broadcast.py       # async pub/sub fan-out
    recorder.py        # reading stream -> SQLite
    templates/         # Jinja2 (HTMX)
    static/            # JS charting (uPlot/Chart.js), CSS
  storage/db.py        # SQLite schema + queries (aiosqlite)
packaging/
  owon-xdm1041-server.service   # systemd unit
  99-owon-xdm1041.rules         # udev rule for stable /dev/owon-xdm1041 symlink
tests/
  conftest.py          # shared fixtures (mock meter, app, temp DB)
  device/              # transport, manager, driver unit tests
  scpi/                # TCP server tests
  web/                 # REST, WebSocket, HTMX route tests
  storage/             # recorder + history query tests
  integration/         # full-stack flows against the mock meter
  hardware/            # opt-in smoke tests, skipped without a real device
```

### Data model (SQLite)

- `readings(id, ts, function, value, unit, range, rate)` — append-only samples.
- Optional `sessions(id, started_at, ended_at, note)` to group recordings.
- History endpoint serves downsampled ranges; charts use uPlot/Chart.js.

---

## Testing strategy

Testing is a first-class deliverable, not an afterthought. **Every phase lands
with its tests**, and the entire suite runs **without hardware** by exercising
the stack against the mock meter, so CI is fully self-contained.

**The mock meter is the keystone.** It implements the same interface as the real
transport and simulates a stateful XDM1041: holds function/range/rate, answers
queries, and lets tests inject the conditions that matter for a long-running
server — configurable response latency, timeouts, malformed/partial responses,
disconnect/reconnect, and **external (front-panel) state changes** mutated out of
band mid-test.

Layers of coverage:

- **Unit — device layer.** Transport framing/encoding; DeviceManager arbitration
  (serialized single-flight, no interleaved responses, timeout handling,
  reconnect); driver command construction and response parsing; read-through
  state logic (no stale cache trusted across idle gaps).
- **Unit — SCPI server.** Line framing incl. partial/coalesced reads; passthrough
  correctness; **multiple concurrent clients** sharing the arbiter.
- **Unit — web.** REST control endpoints (FastAPI `TestClient`); WebSocket live
  stream lifecycle; HTMX endpoints return the expected HTML fragments.
- **Unit — storage.** Recorder writes correct rows with the function actually in
  effect; history queries and downsampling; retention.
- **Integration — full stack against the mock.** The scenarios where bugs live:
  a SCPI client changes function while a web live view is active → UI and recorder
  reflect it; a simulated **front-panel change** is picked up within one poll
  interval and tagged correctly; concurrent SCPI + web access stays serialized;
  the poller yields to interactive commands; reconnect after a device drop.
- **Hardware smoke (opt-in).** A small suite gated behind a marker/env flag,
  skipped by default, run by hand in Phase 6 against a real meter (`*IDN?`,
  read a value, verify the front panel isn't locked out).

**Tooling:** `pytest` + `pytest-asyncio`, coverage with a target gate, `ruff` and
`mypy` enforced in CI. Async timeouts on tests so a hung transaction fails loudly
rather than blocking the suite.

---

## Implementation phases

Each phase below is considered done only when its code **and** the tests for it
(per the Testing strategy) are in place and green in CI.

**Phase 0 — Scaffolding.** `pyproject.toml` (package `owon_xdm1041_server`,
console-script entrypoint), tooling: ruff, mypy, pytest + pytest-asyncio,
coverage, pre-commit, and a CI workflow running the full hardware-free suite.

**Phase 1 — Device layer.** transport → DeviceManager arbiter → driver, plus the
mock meter. Ship a small CLI (`... probe`) to connect, `*IDN?`, and read a value.
Unit tests run against the mock.

**Phase 2 — SCPI TCP server.** asyncio server on `:5025`, line-oriented
passthrough through the DeviceManager. Validate with `pyvisa`
(`TCPIP::<host>::5025::SOCKET`).

**Phase 3 — Web backend.** FastAPI app, poller + broadcaster, REST control
endpoints (set function/range/rate, one-shot read), WebSocket live stream.

**Phase 4 — Persistence.** Recorder → SQLite; history query endpoint; retention/
downsampling.

**Phase 5 — Web UI.** HTMX pages: live dashboard (WS-driven gauge/readout),
control panel (function/range/rate forms), history page with charts + CSV export.

**Phase 6 — Packaging & deploy.** systemd unit; **udev rule** matching the
meter's USB vendor/product ID (and serial if exposed) to create a stable
`/dev/owon-xdm1041` symlink so the server has a fixed device path regardless of
`ttyUSB*`/`ttyACM*` enumeration order; install/config docs; hardware-on-the-bench
validation including front-panel-change behavior.

---

## Key risks / decisions to watch

- **Timing:** the XDM1041 is slow; transactions need generous timeouts and strict
  single-flight serialization to avoid interleaved responses.
- **State coherence:** a value's meaning depends on the active function. The
  driver tracks/refreshes cached state when any client changes the mode.
- **Poller vs. passthrough contention:** the poller must yield to interactive
  SCPI/web commands (priority or fair queue in the arbiter).
- **On-demand polling tradeoff:** with polling tied to live web viewers, history
  is only recorded while someone is watching. If continuous background logging is
  ever wanted, the poller gains an always-on mode independent of subscribers.
- **Security:** SCPI on `:5025` and the web UI are unauthenticated by default —
  intended for a trusted LAN. Note this in docs; auth can come later.
