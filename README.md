# Kodak Smile Maestro Suite (Flows 1-10)

**Maestro — every time:** Any change to flows, `config.yaml`, or Maestro scripts must follow **[Maestro documentation](https://docs.maestro.dev/)** (see `AGENTS.md` and `docs/MAESTRO_OFFICIAL_REFERENCE.md`). **Every time** you edit those files, verify CLI and YAML against the official docs — do not invent flags or syntax.

**ATP Reference:** Test cases and knowledge base in `docs/ATP_KNOWLEDGE_BASE.md` (from `testcases.xlsx`).

## Run all flows (uses `config.yaml` in repo root)

```bash
maestro test . --format junit --output report.xml
```

## Run a single flow

```bash
maestro test "Non printing flows/flow6.yaml"
```

## Run on one device (official CLI)

Global `--device` before `test` — see [Maestro CLI commands and options](https://docs.maestro.dev/maestro-cli/maestro-cli-commands-and-options):

```bash
maestro --device <SERIAL> test "Non printing flows/flow1.yaml" --format junit --output report.xml
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
