Kodak Smile Advanced Pipeline Package

This package upgrades your Kodak Smile automation to a more advanced and stable Jenkins pipeline.

Included files
- Jenkinsfile
- scripts/precheck_environment.bat
- scripts/run_one_flow_on_device.bat
- scripts/run_suite_same_machine.bat
- scripts/generate_build_summary.py
- scripts/run_ai_analysis.bat
- docs/PIPELINE_EXECUTION_AND_EMAIL.md

What is improved
1. Clear separation between controller work and device work.
2. Same-machine sequential mode for stability on one Windows USB PC.
3. Multi-agent parallel mode for fast + stable production setup.
4. Common runner for both non-printing and printing.
5. Precheck stage for adb, maestro, node, npm, python, device presence, and session warning.
6. Per-device artifact isolation for logs, screenshots, and status files.
7. Exit-code based pass/fail markers.
8. Retry failed flows once before final failure.
9. Build summary generation in JSON + HTML.
10. Optional AI analysis at the end only when tests fail.
11. Email summary support.
12. Archived collected artifacts.

Recommended usage
- Immediate stable usage on one machine:
  RUN_MODE = same_machine_sequential
  DEVICES_AGENT = devices

- Best production usage:
  RUN_MODE = multi_agent_parallel
  DEVICE1_LABEL = device-agent-1
  DEVICE2_LABEL = device-agent-2
  DEVICE1_ID = 3C1625009Q500000
  DEVICE2_ID = RZCWA2B05RB

Required repo folders
- Non printing flows/
- Printing Flow/
- ai-doctor/   (optional, only for AI analysis)

Before first run
1. Replace EMAIL_TO default in Jenkins parameters or enter it at build time.
2. Confirm agent labels match your Jenkins setup.
3. Confirm device IDs match your phones.
4. Ensure adb, maestro, node, npm, and python are installed on the required agents.
5. Run device agents in a logged-in desktop session, not Session 0.

Important note
- Multi-agent mode is recommended for true parallel execution.
- Same-machine parallel is intentionally not used here because it is the main source of instability with Maestro on Windows.
