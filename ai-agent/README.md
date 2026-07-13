# Kodak Smile AI Agent

Autonomous QA orchestration layer for the Kodak Smile Android Maestro ATP framework.

**Isolation guarantee:** does not modify Maestro YAML, Jenkins pipelines, or the existing Excel/email reporting pipeline.

## Quick start

```bat
pip install -r ai-agent\requirements.txt
scripts\run_kodak_smile_full_regression.bat
```

Equivalent:

```bat
python ai-agent\main.py --repo . --mode assist --full-regression
```

## What it does

1. Detect healthy Android devices  
2. Optionally install APK  
3. Discover all ATP modules automatically  
4. Launch Maestro via existing ATP stage runner  
5. Capture screenshots, videos, logcat  
6. Retry flaky modules once  
7. AI-classify failures  
8. Generate HTML / PDF / Markdown / JSON reports  
9. Produce QA sign-off (`READY FOR RELEASE` / `NOT READY`)

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Installation](docs/INSTALLATION.md)
- [AI workflow](docs/AI_WORKFLOW.md)
- [Vision API guide](docs/VISION_API.md)

## Layout

```
ai-agent/
  main.py                 # CLI entry
  orchestrator.py         # composition root
  test_planner.py
  device_manager/
  maestro_runner.py
  screenshot_manager.py
  video_recorder.py
  logcat_collector.py
  log_analysis/
  ai_failure_analyzer.py
  retry_manager.py
  vision/
  reporting/
  agent_utils/            # adb + logging (avoids repo utils/ clash)
  docs/
  tests/
  reports/                # generated outputs
```
