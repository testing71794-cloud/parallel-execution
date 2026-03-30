# Kodak Smile Maestro automation

Windows Jenkins agent runs Maestro flows on connected Android devices, generates Excel under `reports\`, and optionally emails results.

## Documentation

| Doc | Purpose |
|-----|---------|
| [README_PRODUCTION_SETUP.md](README_PRODUCTION_SETUP.md) | Agent, job, and infra setup |
| [docs/PIPELINE_EXECUTION_AND_EMAIL.md](docs/PIPELINE_EXECUTION_AND_EMAIL.md) | Pipeline stages, Excel, SMTP, troubleshooting |
| [docs/MAESTRO_OFFICIAL_REFERENCE.md](docs/MAESTRO_OFFICIAL_REFERENCE.md) | Maestro CLI alignment |
| [AGENTS.md](AGENTS.md) | Rules for editing flows and scripts |

## Quick checks (local)

```bat
cd /d <repo-root>
call scripts\precheck_environment.bat "" com.kodaksmile
call scripts\list_devices.bat
call scripts\run_suite_parallel_same_machine.bat nonprinting "Non printing flows" "" com.kodaksmile true ""
```

## Jenkins

- **Script Path:** `Jenkinsfile`
- **Parameters:** Enable **Send Final Email** if you want mail; set SMTP env vars on the agent (see `docs/PIPELINE_EXECUTION_AND_EMAIL.md`).
- **Maestro:** Set job parameter **MAESTRO_CMD** to `maestro.cmd` if the agent user is not the user who installed Maestro.

## AI Doctor (optional)

From repo root (requires Node; `npm run doctor` may need Git Bash on Windows):

```bat
npm install
npm run doctor
```
