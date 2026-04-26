# Production Jenkins Setup

## What was cleaned up
- Kept all flow files unchanged in:
  - `Non printing flows/`
  - `Printing Flow/`
  - `flows/`
- Removed old or conflicting Jenkinsfiles and placeholder runner scripts.
- Removed checked-in `.git`, `node_modules`, and `agent.jar` from the package.
- Added one production `Jenkinsfile` in the repo root.

## Expected Jenkins nodes
- `built-in` (or your controller) for **Git checkout only**
- `devices` for all Windows work:
  - ADB
  - Maestro
  - Python
  - Node/npm

## Jenkins job configuration
- Definition: **Pipeline script from SCM**
- Script Path: `Jenkinsfile`
- Lightweight checkout: **unchecked**

## Software required on the `devices` node
- ADB in PATH
- Maestro CLI in PATH or installed at `C:\maestro\bin\maestro.exe`
- Python 3
- Node.js + npm

## Pipeline stages
1. Fetch Code from GitHub
2. Install Dependencies
3. Environment Precheck
4. Detect Connected Devices
5. Execute Non Printing Flows
6. Generate Excel Report for Non Printing
7. Execute Printing Flows on Physical Devices
8. Generate Excel Report for Printing
9. AI Failure Analysis + Smart Retry
10. Build Summary
11. Send Final Email
12. Archive Reports & Artifacts
13. Finalize Build Result

## Parameters
- `DEVICES_AGENT`: Windows node label, default `devices`
- `APP_PACKAGE`: default `com.kodaksmile`
- `MAESTRO_CMD`: optional override path to Maestro
- `RUN_NON_PRINTING`: run Non printing flows
- `RUN_PRINTING`: run Printing Flow
- `RETRY_FAILED`: retry each failed flow once on the same device
- `RUN_AI_ANALYSIS`: run AI doctor only when failures exist

## Output folders produced by the pipeline
- `reports/`
- `status/`
- `collected-artifacts/`
- `build-summary/`
- `.maestro/screenshots/`

## Notes
- This setup is designed for **one Windows Jenkins agent controlling all connected Android devices**.
- Flows are executed **per flow across all detected devices in parallel**.
- If a flow fails on one device, the pipeline continues and still generates reports.


## End-of-run email
The pipeline now sends one email after all flows finish.

### What the email attaches
- `build-summary/final_execution_report.xlsx`
- `reports/nonprinting_summary/summary.xlsx`
- `reports/printing_summary/summary.xlsx`
- `build-summary/summary.html`
- AI analysis files from `ai-doctor/artifacts/` when generated

### Required Jenkins environment variables for email
Set these on the job or node before enabling `SEND_FINAL_EMAIL`:
- `MAIL_TO`
- `SMTP_HOST`
- `SMTP_PORT` (optional, default 587)
- `SMTP_USER`
- `SMTP_PASS`
- `SMTP_FROM` (optional)
- `MAIL_SUBJECT` (optional)

If `MAIL_TO` is not set, the email stage skips without failing the build.

## Execution model
This package runs exactly as requested:
- Flow 1 runs on all detected devices in parallel.
- Jenkins waits until Flow 1 finishes on every detected device.
- Then Flow 2 starts on all detected devices in parallel.
- The same pattern continues for the full suite.


## Continue-on-failure behavior

This package is configured so that all major stages continue even when an earlier stage fails.
- Each flow runs on all detected devices in parallel.
- The next flow starts only after the current flow finishes on all devices.
- Non-printing and printing suites continue independently.
- Excel, AI analysis, archive, and end-of-run email still run even if earlier execution failed.
- Final Jenkins result is decided only in the last stage using flag files.
