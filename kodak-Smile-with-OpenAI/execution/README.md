# Parallel device orchestration (Maestro)

Runs **one thread per device**, **flows sequentially** on that device. After each flow: JUnit + log, optional **OpenRouter** AI row, **thread-safe** append to `build-summary/final_execution_report.xlsx`.

**Before each run** (default): `execution/cleanup_previous_run.py` logic removes `logs/` and `build-summary/`, then a **fresh** Excel is primed with headers only (no rows from prior runs). Use `--no-clean` to skip deletion.

## Requirements

- `adb`, Maestro on `PATH` (or pass full path via `--maestro`)
- Repo root `config.yaml` for `--config`
- OpenRouter: `OPENROUTER_API_KEY` (or Jenkins credential) when AI is enabled
- Email (optional): `SMTP_HOST`, `SMTP_USER`, `SMTP_PASS`, `MAIL_TO` / `RECEIVER_EMAIL`

## Layout

| Path | Role |
|------|------|
| `execution/run_parallel_devices.py` | Entry |
| `execution/cleanup_previous_run.py` | Standalone cleanup (also invoked by default from runner) |
| `execution/default_flows.txt` | Ordered flow list |
| `ai/run_ai_analysis.py` | JUnit summary + OpenRouter (429: 5s, max 3 tries) |
| `excel/update_excel.py` | Thread-safe Excel append |
| `mailout/send_email.py` | Final email (**not** `email/` — avoids Python stdlib shadowing) |
| `logs/<device>/` | Per-device JUnit + logs |

## Commands

From repo root:

```bat
python execution\run_parallel_devices.py
```

With email:

```bat
python execution\run_parallel_devices.py --send-email
```

Skip AI (faster / offline):

```bat
python execution\run_parallel_devices.py --no-ai
```

Custom flows file:

```bat
python execution\run_parallel_devices.py --flows-file execution\my_flows.txt
```

Specific devices only:

```bat
python execution\run_parallel_devices.py --devices emulator-5554 R58M123ABC
```

Cleanup only:

```bat
python execution\cleanup_previous_run.py
```

## Maestro invocation

Uses: `maestro --device <serial> test "<flow>" --config config.yaml --format junit --output "<path>"`  
(Aligned with `docs/MAESTRO_OFFICIAL_REFERENCE.md`.)

## Excel columns

`Timestamp`, `Device Name`, `Flow Name`, `Status`, `Failure Message`, `AI Analysis`, `Duration`

Pass rows show **AI Analysis** = `N/A — passed`. Failures use OpenRouter when a key is set; otherwise `AI Analysis Failed (no API key)`.
