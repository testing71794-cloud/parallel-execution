# Pipeline, Excel, and email (current `Jenkinsfile`)

## How a successful run works

1. **Checkout** is unstashed on the Windows agent; every `cd` uses **`${env.WORKSPACE}`** for that job (never a hardcoded path).
2. **Execute Non Printing / Printing** runs `scripts\run_suite_parallel_same_machine.bat`. For **each** YAML in order (`flow1`, `flow2`, …), Maestro runs that **same** flow on **all connected devices at once**; when **every** device has finished that flow, the next flow starts the same way (parallel per flow, sequential across flows).
3. Maestro writes logs under `reports\<suite>\logs\`; each run updates `status\<suite>__<flow>__<device>.txt`.
4. **Generate Excel** runs `python scripts\generate_excel_report.py status reports\<suite>_summary <suite>` → `reports\<suite>_summary\summary.xlsx` (and CSVs).
5. **Send Final Email** runs only if the job parameter **`SEND_FINAL_EMAIL`** is **enabled** and SMTP env vars are set on the agent (see below).

## Critical: workspace path

All batch steps use **`cd /d "${env.WORKSPACE}"`** on the device agent. A previously hardcoded path (or running scripts manually from the wrong directory) points at an **empty or wrong folder** → no flows, no `status/*.txt`, empty or missing Excel.

## Critical: Maestro CLI

`run_one_flow_on_device.bat` invokes Maestro as **`maestro --device <serial> test <flow>`** (global `--device` **before** `test`).  
Wrong order can prevent runs from targeting devices correctly. Optional `--config config.yaml` is used when present at repo root.

## Email not received

1. In the job, enable **`SEND_FINAL_EMAIL`** (Build with Parameters). That only *runs* the script; it does **not** inject SMTP settings.
2. **Define SMTP on the Windows agent that runs the job** (the node with label `devices`). If these variables are not set in that process, mail is never sent. Typical places:
   - **Manage Jenkins → Nodes → (your agent) → Configure → Environment variables**
   - **Job → Configure → Build Environment** (e.g. *Inject environment variables* plugin)
   - **Credentials** as *Secret text* / *Username with password*, bound in the Pipeline to env vars (recommended for passwords)

3. Required names (aliases in parentheses):

| Role | Primary | Aliases |
|------|---------|---------|
| SMTP host | `SMTP_SERVER` | `SMTP_HOST` |
| Port | `SMTP_PORT` (default **587**) | — |
| From / login | `SENDER_EMAIL` | `SMTP_USER` |
| Password | `SENDER_PASSWORD` | `SMTP_PASS` |
| To | `RECEIVER_EMAIL` | `MAIL_TO` |

4. **Gmail:** use an [App Password](https://support.google.com/accounts/answer/185833), not your normal password. Often use **`SMTP_SSL=1`**, **`SMTP_PORT=465`**, or port **587** with STARTTLS (default in script).

5. After the next run, open the **Send Final Email** stage log. If configuration is incomplete, the script now **fails the stage** and prints which variables are **MISSING** (so you are not left with a green build and no mail).

6. If the **Send Final Email** stage is **skipped** entirely, `SEND_FINAL_EMAIL` was false for that build.

## Excel looks empty

- `generate_excel_report.py` reads **`status/*.txt`**. If execution stages failed before writing status files, or the suite name filter does not match, totals can be zero.
- Confirm **`status\`** exists after a run and contains `nonprinting__*` / `printing__*` files.

## Flows still do not run

- **ADB / devices:** Precheck and list stages require at least one `adb devices` **device**.
- **Maestro on PATH or `MAESTRO_CMD`:** Job parameter **MAESTRO_CMD** can point to `maestro.cmd` if the agent user differs from the install user.
- **`ANDROID_HOME`:** Set on the agent so `scripts\run_suite_parallel_same_machine.bat` and `run_one_flow_on_device.bat` can prepend `platform-tools` to `PATH` (Maestro uses adb).
- **Parallel runs:** `run_suite_parallel_same_machine.ps1` uses **`Start-Process`** (not `Start-Job`) so each device run inherits the same PATH and session as the Jenkins PowerShell process.

## Excel / email attachments

- Email (when **Send Final Email** is enabled) attaches **`summary.xlsx`** from non-printing and printing report folders and **`final_execution_report.xlsx`** from `build-summary` when those files exist.
