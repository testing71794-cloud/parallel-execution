# Kodak Smile Pipeline Execution and Email Guide

## Execution modes

### 1) same_machine_sequential
Use this when both phones are connected to one Windows machine.

Behavior:
- flow1 -> device1
- flow1 -> device2
- flow2 -> device1
- flow2 -> device2

Why:
- avoids same-machine parallel Maestro conflicts
- most stable option on one PC

### 2) multi_agent_parallel
Use this when you have one Jenkins agent per device.

Behavior:
- same flow runs on both agents in parallel
- next flow waits until both agents finish

Why:
- keeps speed
- avoids shared temp / screenshot / workspace conflicts

## Output structure

### Logs
reports/<suite>/<flow>/<device>/logs/

### Screenshots
.maestro/screenshots/<device>/<suite>/<flow>/

### Status files
status/
- nonprinting_flow1_DEVICEID.pass
- nonprinting_flow1_DEVICEID.fail

### Collected artifacts
collected-artifacts/

## Email summary
The pipeline sends an HTML summary generated from status files.

SEND_EMAIL_MODE values:
- failed_only
- always
- never

## AI analysis
AI analysis runs only when:
- AI_ANALYSIS = true
- pipeline_failed.flag exists

Script used:
scripts/run_ai_analysis.bat

## Recommended Jenkins labels
- built-in
- devices
- device-agent-1
- device-agent-2

## Troubleshooting

### App does not launch
- Ensure the Jenkins agent runs on the logged-in desktop session.
- Avoid Session 0 / service-only UI context.
- Confirm adb sees the phone.
- Confirm the app is installed.
- Confirm Maestro is callable.

### Device missing
Run:
adb devices

### Maestro missing
Run:
maestro --version

### Python missing
Run:
python --version

### Node missing
Run:
node --version
npm --version
