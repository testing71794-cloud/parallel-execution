# Local Jenkins — C: drive usage and cleanup

**Primary guide:** [disk_cleanup_guide.md](disk_cleanup_guide.md) — cleanup scripts, verification, and safety boundaries.

This document explains why local Jenkins runs filled the C: drive, what was changed in the pipeline and scripts to control disk growth, and what is safe to clean manually.

## Why the C: drive was filling

1. **Stash on the Jenkins controller** — The pipeline stashed the repo for agents. A full tree (`**/*` with default excludes off) included **`.git`**, which is large and unnecessary on agents.
2. **Many stash copies** — `preserveStashes` kept several full snapshots.
3. **Archived artifacts** — Each retained build stored `final_execution_report.xlsx`, `execution_logs.zip`, `.maestro/screenshots/**`, and `detected_devices.txt` under Jenkins job directories.
4. **npm / pip caches** — Every install adds to `%LocalAppData%\npm-cache` and pip’s cache; these are outside the job workspace.
5. **Maestro user profile** — `%USERPROFILE%\.maestro` (tests, screenshots) grows during runs.

## What was fixed (safe, no test/YAML changes)

| Area | Change |
|------|--------|
| **Stash** | Exclude `.git`, `node_modules`, `.maestro`, `reports`, `build-summary`, `status`, `logs`, `collected-artifacts`, `test-results`, `maestro-report`, and `**/*.zip`. Agents still get sources; dependencies are installed by `npm ci` / `pip install` on the agent. |
| **Stash retention** | `preserveStashes` reduced from **5** to **2**. |
| **Artifact retention** | `artifactNumToKeepStr` reduced from **5** to **3** — fewer duplicate copies of logs/zips/screenshots/Excel on disk; latest builds still archived. |
| **Workspace cleanup** | `scripts/safe_disk_cleanup.bat` calls `cleanup_c_drive_generated_files.bat` for **PRE**, **POST**, and **REPORT**; POST runs after `archiveArtifacts`. |
| **Reporting** | After POST cleanup, Jenkins runs **REPORT** (includes `check_disk_usage.ps1`). |

**Not changed:** Maestro YAML flows, device execution, printing/non-printing logic, `generate_excel_report.py` / `execution_logs.zip` generation, or `archiveArtifacts` file list (still includes Excel, zip, screenshots, `detected_devices.txt`).

## What is safe to clean

- **On the agent workspace** after a successful archive: `reports/`, `status/`, `build-summary/`, `.maestro/` under the repo, temp dirs — handled by **POST** mode (after Jenkins has archived artifacts).
- **Before a new run**: same generated dirs — **PRE** mode (plus trimming Maestro `tests`/`screenshots` under the user profile used by the agent).
- **npm / pip caches**: Safe to trim periodically with `npm cache clean --force` and `pip cache purge` when you accept slower next installs (see `scripts/safe_cache_cleanup_report.bat` — comments only).
- **Old Jenkins builds**: Use the Jenkins UI to discard old builds or tighten job **Discard old builds** settings.

## What you should not delete

- **Git-tracked sources**: `flows/`, `elements/`, `ATP TestCase Flows/`, `Non printing flows/`, `Printing Flow`, `scripts/` (except generated logs if any), `Jenkinsfile`, `package.json`, YAML flows.
- **Jenkins archived artifacts** until you have copied what you need — they live under `%JENKINS_HOME%\jobs\...\builds\...\archive\`.
- **Latest needed reports** — Keep final Excel / zip per your policy before deleting old **build** folders in Jenkins.

## How to run REPORT mode

From repo root (or pass workspace path):

```bat
scripts\cleanup_c_drive_generated_files.bat REPORT
scripts\cleanup_c_drive_generated_files.bat REPORT "C:\JenkinsAgent\workspace\<job>"
```

Optional cache-only sizes:

```bat
scripts\safe_cache_cleanup_report.bat
```

## How to clear old Jenkins builds from the UI

1. Open the job → **Build History**.
2. Hover a build → drop-down → **Delete this build** (or use **Manage Jenkins** → **Manage Old Data** / job **Configure** → **Discard old builds** with stricter days or counts).
3. To shrink **archived** artifacts specifically, reduce **“Max # of builds to keep with artifacts”** (or the artifact-only equivalent) in the job or global properties.

## Verification commands (before / after)

**Workspace / folders (PowerShell):**

```powershell
Get-ChildItem $env:WORKSPACE -Directory -ErrorAction SilentlyContinue | ForEach-Object {
  $s = (Get-ChildItem $_.FullName -Recurse -File -EA SilentlyContinue | Measure-Object Length -Sum).Sum
  [PSCustomObject]@{ Path = $_.Name; MB = [math]::Round($s/1MB, 2) }
}
```

**This repo’s cleanup scripts:**

```bat
scripts\cleanup_c_drive_generated_files.bat REPORT "%WORKSPACE%"
scripts\safe_cache_cleanup_report.bat
```

## References

- [Maestro CLI](https://docs.maestro.dev/maestro-cli/maestro-cli-commands-and-options) — verify flags when changing runners only (this doc does not change flows).
