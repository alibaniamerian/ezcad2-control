# 2026-10-27 — Local web control

## GitHub publication preparation

- Prepared as the independent private repository `alibaniamerian/ezcad2-control`.
- Operator reported that the web panel worked and that three tested actions succeeded; the three actions were not individually named. Do not infer independent verification of every action.
- Added `docs/INTEGRATION.md`, a unified README and Windows offline CI for Python 3.10/3.12.
- Published source uses `--exe` or `EZCAD2_EXE` instead of a workstation-specific installation path. Original local working folder is preserved.
- Publication excludes logs, runtime uploads, virtual environments, machine settings and vendor binaries. All 14 offline tests and JavaScript syntax validation passed again in the independent checkout.
- Next task: integrate the local control contract with the production application, maintaining explicit operator confirmation and separate completion/serial tracking.

## Earlier implementation checkpoint

- Standalone project; no XYPrinter integration or hardware firmware changes.
- Previous operator-confirmed TCP experiment: EZCAD2 requested `TCP:Give me string` when marking and physically marked the server response `A1B2`. Raw ASCII response with connection close worked in that experiment.
- Red was activated through desktop UI and physically confirmed by the operator.
- Desktop panel provides Red / Stop / confirmed Mark and file loading through File > Open. The installed owner-drawn menu did not expose Open text; read-only PE inspection confirmed Ctrl+O command 0xE101. Runtime code reads the actual accelerator resource, rather than hardcoding this ID.
- `web_panel.py` provides the same actions at http://127.0.0.1:8765, with Persian UI, upload or original local path, same-origin/session protection, idempotent request IDs, one-use expiring Mark confirmation, and no automatic retries.
- 14 offline tests passed; JavaScript syntax check passed. Actual local HTML and status endpoints returned HTTP 200. Browser visual QA could not run because the Chrome browser connector was unavailable. Preview service was stopped after verification.
- No hardware commands were sent during web implementation. Next: operator validates file loading, Red and Stop through the web UI. Physical Mark from the web panel remains untested and requires an explicit operator confirmation.
- The panel does not provide a production interlock or independent marking-completion feedback. File submission and Windows message posting must not be reported as physical success.
