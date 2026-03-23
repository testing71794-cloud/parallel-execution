# Pipeline: flow-by-flow on all devices → Excel per flow → email when done

## What runs

1. **Flow 1** (`Non printing flows\flow1.yaml`) runs **in parallel on every connected device** (via `run_single_flow_parallel.bat`).
2. When **all devices** finish that flow → **`update_excel_after_flow.py`** appends rows to `reports\excel\nonprinting_execution.xlsx`.
3. Steps 1–2 repeat for **flow2 … flow7** (non-printing).
4. Same pattern for **Printing Flow** `flow1.yaml` … `flow11.yaml` → **`printing_execution.xlsx`**.
5. After **all** flows complete → **`send_execution_email.py`** sends **both** Excel files by email (if SMTP is configured).

JUnit XML is stored under:

- `reports\raw\nonprinting\flowN_<deviceTag>.xml`
- `reports\raw\printing\flowN_<deviceTag>.xml`

`<deviceTag>` is the ADB serial with `:` and `\` replaced so paths are valid on Windows (Maestro still uses the real serial via `-d`). Non-printing and printing suites never overwrite each other’s `flow1` reports.

**Execution order (CMD):** for each flow, `run_single_flow_parallel.bat` starts **one minimized `cmd` per device** (parallel), waits until **every** exit marker file exists, then returns — only then `run_all_flows_pipeline.bat` runs Excel for that flow and continues to the **next** flow.

**Jenkins / non-interactive agents:** the wait loop uses `ping 127.0.0.1` for delays, not `timeout`, because `timeout` requires a console stdin and fails with *Input redirection is not supported* under the Jenkins agent.

## One command (Windows)

```bat
scripts\run_all_flows_pipeline.bat
```

Or from repo root:

```bat
cd D:\path\to\kodak-Smile-with-OpenAI
scripts\run_all_flows_pipeline.bat
```

## Python dependencies

```bat
pip install -r scripts\requirements-python.txt
```

## Email (after all flows)

Set these **environment variables** (Jenkins: job → Configure → Build Environment → Inject, or system env on your PC):

| Variable     | Example              | Required |
|-------------|----------------------|----------|
| `MAIL_TO`   | `you@company.com`    | Yes, to send |
| `SMTP_HOST` | `smtp.gmail.com`     | Yes      |
| `SMTP_PORT` | `587`                | Optional (default 587) |
| `SMTP_USER` | `your@gmail.com`   | Yes      |
| `SMTP_PASS` | app password         | Yes      |
| `SMTP_FROM` | same as user         | Optional |
| `MAIL_SUBJECT` | custom subject    | Optional |

If **`MAIL_TO` is not set**, the email step is skipped and the build still **succeeds**.

## Jenkins

- Job runs `scripts\run_all_flows_pipeline.bat` on an agent with **devices** (see `Jenkinsfile.hybrid`).
- Add the same SMTP variables to the job so the final email runs inside the batch file.

Alternative: install **Email Extension Plugin** and add a post-build step with `attachmentsPattern: reports/excel/*.xlsx` (then you can remove the Python email call from the `.bat` if you prefer Jenkins-only mail).

## PowerShell entry points

`run_flows_non_printing.ps1` and `run_flows_printing.ps1` use the **same** `reports\raw\<suite>` layout and `update_excel_after_flow.py` as the `.bat` pipeline. They do **not** send the final email by default; use the full `run_all_flows_pipeline.bat` for email after both suites.
