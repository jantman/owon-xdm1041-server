# owon-xdm1041-server

A network SCPI server and web UI for the [OWON XDM1041](https://www.owon.com.hk/)
bench digital multimeter.

It connects to the meter over USB serial and exposes it two ways at once:

- **Raw-socket SCPI server** on TCP `:5025` — drive the meter from pyvisa,
  NI-VISA, sigrok, etc. (`TCPIP::<host>::5025::SOCKET`).
- **Web UI** on `:8080` — a live dashboard, a control panel, and recorded
  history with charts and CSV export.

Both interfaces share a single arbitrated connection to the serial port, and the
meter is kept in LOCAL mode so its front panel stays usable at all times.

See [docs/DESIGN.md](docs/DESIGN.md) for the architecture and rationale.

## Features

- Single owner of the serial port (`DeviceManager`) serialises every command, so
  the SCPI server, the web poller, and manual control never collide on the bus.
- Read-through state: every reading re-reads the active function, so values stay
  correctly labelled even when someone changes the mode from the physical panel.
- On-demand polling: the meter is only sampled while a browser is watching the
  live dashboard; readings during that time are recorded to SQLite.
- Runs entirely against a built-in mock meter for development and the full test
  suite — no hardware required.

## Requirements

- Python 3.12+
- A USB connection to the meter (115200 baud, 8N1)

## Install

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e .          # add ".[dev]" for the test/lint toolchain
```

## Run

Against real hardware (set the serial port if it isn't the udev symlink default):

```bash
OWON_SERIAL_PORT=/dev/owon-xdm1041 owon-xdm1041-server serve
```

Against the built-in mock meter (no hardware needed):

```bash
owon-xdm1041-server serve --mock
```

Then open <http://localhost:8080>. Quick checks:

```bash
owon-xdm1041-server probe --mock          # identify + one reading
curl http://localhost:8080/api/state
```

SCPI from Python:

```python
import pyvisa
rm = pyvisa.ResourceManager()
dmm = rm.open_resource("TCPIP::localhost::5025::SOCKET", read_termination="\n")
print(dmm.query("*IDN?"))
```

## Configuration

All settings are environment variables with the `OWON_` prefix (see
[`config.py`](src/owon_xdm1041_server/config.py)):

| Variable | Default | Description |
| --- | --- | --- |
| `OWON_SERIAL_PORT` | `/dev/owon-xdm1041` | Serial device path |
| `OWON_USE_MOCK` | `false` | Use the in-memory mock meter |
| `OWON_POLL_INTERVAL` | `0.5` | Seconds between live samples |
| `OWON_SCPI_HOST` / `OWON_SCPI_PORT` | `0.0.0.0` / `5025` | SCPI socket bind |
| `OWON_WEB_HOST` / `OWON_WEB_PORT` | `0.0.0.0` / `8080` | Web UI bind |
| `OWON_DATABASE_PATH` | `owon_xdm1041.sqlite3` | SQLite history file |

> The SCPI socket and web UI are unauthenticated — intended for a trusted LAN.

## Deploying on a Raspberry Pi

1. Install the project into a venv (e.g. under `/opt/owon-xdm1041-server`).
2. Install the udev rule for a stable device path (edit the USB IDs to match your
   adapter first — see comments in the file):
   ```bash
   sudo cp packaging/99-owon-xdm1041.rules /etc/udev/rules.d/
   sudo udevadm control --reload-rules && sudo udevadm trigger
   ```
3. Install and start the service:
   ```bash
   sudo cp packaging/owon-xdm1041-server.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now owon-xdm1041-server
   ```

## Development

```bash
pip install -e ".[dev]"
ruff check . && ruff format --check .
mypy
pytest                    # full suite runs hardware-free against the mock
```

> The web UI loads HTMX from a CDN. For a fully offline Pi, vendor `htmx.min.js`
> into `web/static/` and point `base.html` at it.

## Credits

SCPI command set reverse-engineered by
[TheHWcave/OWON-XDM1041](https://github.com/TheHWcave/OWON-XDM1041).
