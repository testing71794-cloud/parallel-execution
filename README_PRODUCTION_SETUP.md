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
11. Archive Reports & Artifacts
12. Finalize Build Result

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
