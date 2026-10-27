# EZCAD2 Control

Local Windows control of an existing EZCAD2 installation, with a Persian web interface and a desktop panel. Open `.ezd` designs, preview the marking area with **Red**, request **Stop**, and explicitly confirm **Mark**.

The application drives the existing EZCAD2 Windows UI. It does not include EZCAD2, its drivers, an SDK, controller firmware, or machine configuration. EZCAD2 must already be installed, connected, and open.

## Quick start

Requires Windows and Python 3.10+ with tkinter (included in the usual python.org Windows installation). No pip packages are required.

```powershell
git clone https://github.com/alibaniamerian/ezcad2-control.git
cd ezcad2-control
python web_panel.py --exe "C:\Path\To\EZCAD2\EzCad2.exe"
```

Open **http://127.0.0.1:8765** on the same computer. Keep the terminal and EZCAD2 open. The service only listens on loopback.

Alternatively set the executable path for the current PowerShell session:

```powershell
$env:EZCAD2_EXE = "C:\Path\To\EZCAD2\EzCad2.exe"
python web_panel.py
# Or the desktop version:
python control_panel.py
```

The explicit `--exe` option takes precedence over `EZCAD2_EXE`. Without either, `EzCad2.exe` in the current working directory is expected. Keep machine-specific paths out of Git.

## Operator workflow

1. Open EZCAD2 and ensure no other operation is running.
2. Load an `.ezd` file. Upload creates a uniquely named local copy; use the original-path option for designs with relative external dependencies.
3. Respond to any save-changes prompt **in EZCAD2**, then inspect the actual design. File submission is not proof that EZCAD2 accepted it.
4. Use Red and Stop to check positioning.
5. Mark requires a separate, expiring confirmation. It starts physical laser marking with the current EZCAD2 settings.

**Closing the page or service does not stop the machine. Software Stop is not an emergency stop.** Never treat a posted Windows message as independent confirmation of physical completion.

## Integration

See [the local API contract](docs/INTEGRATION.md) for status, loading, Red, Stop, and the two-step Mark flow. The current browser API is deliberately same-origin and local-only. An externally hosted production website cannot call it directly without a separately designed pairing/authentication and origin policy.

The interface has no production queue, durable serial consumption, machine interlock, or independent completion feedback. Preserve these distinctions when integrating with production software.

## Project layout

| File | Purpose |
| --- | --- |
| `web_panel.py`, `web/` | Local HTTP service and Persian web UI |
| `control_panel.py` | Windows UI adapter and Tk desktop panel |
| `server.py`, `client.py` | Separate TCP variable-text experiment; not required for web control |
| `test_*.py` | Offline tests; fake controller for HTTP/Mark tests |
| [WEB_PANEL.md](WEB_PANEL.md) | Persian web instructions |
| [CONTROL_PANEL.md](CONTROL_PANEL.md) | Persian desktop instructions |
| [docs/TCP_TEST.md](docs/TCP_TEST.md) | Original TCP experiment guide |

## Validation and compatibility

```powershell
python -m unittest -v
# Optional, when Node.js is available:
node --check web/app.js
```

Fourteen offline tests passed during preparation. The operator reported successful local web operation; the exact three tested actions were not enumerated, so do not interpret this as independent verification of every hardware action.

The observed installation was EZCAD2 2.14.16 with an English UI. Button matching and Open-dialog recognition depend on that UI. The Open command is resolved from the executable's Ctrl+O accelerator resource when the owner-drawn menu has no readable label. Files are read as data; the parser does not load or execute the binary. Other versions and translations require validation.

No explicit redistribution license is granted in this initial private repository. Third-party EZCAD2 software remains subject to its own licensing.
