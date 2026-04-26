What changed:
- Runs each flow on all detected devices in parallel
- Uses detected_devices.txt first to avoid device detection mismatch
- Falls back to `adb devices` if detected_devices.txt is missing
- Writes per-device result CSVs and merged summaries
- Retries failed flow/device pairs once
- Forces Java 25 and Maestro from %USERPROFILE%\maestro\maestro\bin

Replace the matching files in your scripts folder, then push and rerun Jenkins.
