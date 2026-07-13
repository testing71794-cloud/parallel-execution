# Kodak Smile AI Agent — Installation

## Prerequisites

- Python 3.10+
- Android platform-tools (`adb` on PATH)
- Maestro CLI (`maestro.bat` / parallel home as used by ATP)
- Connected Android device(s) with USB debugging
- Kodak Smile APK installed **or** `APK_PATH` set

## Install

```bat
cd /d "D:\Projects-Meastro\Kodak Smile Android-true sync"
pip install -r ai-agent\requirements.txt
```

Optional AI enrichment (existing platform):

```bat
set OPENROUTER_API_KEY=your_key
```

## Single command — full regression

```bat
scripts\run_kodak_smile_full_regression.bat
```

Or:

```bat
scripts\run_ai_agent.bat assist
python ai-agent\main.py --repo . --mode assist --full-regression
```

### Modes

| Mode | Behavior |
|------|----------|
| `observe` | Discover devices/modules + write plan reports; no Maestro |
| `assist` | Run ATP via existing stage runner; retry once; AI classify failures |
| `autonomous` | Same execution path today; reserved for future ADB self-healing |

## Outputs

| Artifact | Path |
|----------|------|
| HTML | `ai-agent/reports/report.html` |
| PDF | `ai-agent/reports/report.pdf` |
| Markdown | `ai-agent/reports/summary.md` |
| JSON | `ai-agent/reports/report.json` |
| QA Sign-off | `ai-agent/reports/QA_SIGNOFF.md` |
| Screenshots | `artifacts/screenshots/` |
| Videos | `artifacts/videos/` |
| Logcat | `artifacts/logcat/` |

Existing ATP Excel / Jenkins email reports are **unchanged**.

## Module filter examples

```bat
python ai-agent\main.py --repo . --mode assist --module Onboarding --module Camera
python ai-agent\main.py --repo . --mode assist --module editing --module print
```

## Unit tests

```bat
pip install pytest
pytest ai-agent\tests -q
```
