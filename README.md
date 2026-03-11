# Kodak Smile Maestro Suite (Flows 1-10)

**ATP Reference:** Test cases and knowledge base in `docs/ATP_KNOWLEDGE_BASE.md` (from `testcases.xlsx`).

## Run all flows
```bash
maestro test . --format junit --output report.xml
```

## Run a single flow
```bash
maestro test tests/flow6.yaml
```

## Notes
- This suite uses only Maestro-supported YAML keywords.
- `executionOrder.continueOnFailure: true` is configured in `config.yaml` for suite runs.
- Selectors are primarily text-based and some coordinate taps are used for photo grid/camera shutter.
  Replace coordinate taps with `id:` selectors as you stabilize locators.

## ✅ One-command AI Doctor (Maestro + Cursor AI)

Run everything (tests + artifacts + ATP-based analysis):

```bash
# Install deps (only needed once)
cd ai-doctor && npm install && cd ..
npm install

# Run
./doctor.sh
# OR
npm run doctor
```

**Analysis modes (priority order):**
1. **Cursor Cloud Agents API** – Full AI analysis like Ollama/OpenAI. Set `CURSOR_API_KEY` + `CURSOR_GITHUB_REPO` in `ai-doctor/.env` (repo = your project on GitHub)
2. **ATP rules** – No API key. Uses `docs/ATP_KNOWLEDGE_BASE.md` (default when Cursor API not configured)
3. **Ollama/OpenAI** – Set `USE_CURSOR_AI=0` and configure `OPENAI_*` in `.env`

Outputs:
- `ai-doctor/artifacts/run-*/...` (junit, screenshots, logcat, dumpsys, yaml tree, patches)
- `ai-doctor/artifacts/latest-ai-report.json`
- `ai-doctor/artifacts/cursor-report.md` (paste into Cursor Chat for deeper analysis)
- `ai-doctor/failure_history.json` (learning DB)
