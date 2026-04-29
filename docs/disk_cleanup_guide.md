# Disk cleanup guide (local Jenkins + Maestro automation)

This guide explains why the **C:** drive can fill during Jenkins runs, which folders grow, what is safe to clean, and how to verify space **without** changing Maestro YAML, flows, or test logic.

## Why the C: drive fills

| Cause | What grows |
|--------|------------|
| **Jenkins archived builds** | Under `%JENKINS_HOME%\jobs\...\builds\...\archive\`: Excel, `execution_logs.zip`, screenshots, etc. |
| **Stash storage** | Controller keeps compressed copies of stashed workspace snapshots. |
| **Workspace during a run** | `reports/`, `status/`, `build-summary/`, `.maestro/`, logs, zips. |
| **Maestro user profile** | `%USERPROFILE%\.maestro` (e.g. tests, screenshots). |
| **npm / pip** | `%LOCALAPPDATA%\npm-cache`, `%LOCALAPPDATA%\pip\Cache`. |
| **TEMP** | `%TEMP%` — transient tools and installers. |

Pipeline behavior (Maestro commands, YAML, Printing/Non-printing separation) is unchanged by cleanup tooling; only **retention**, **stash excludes**, and **workspace deletes** are tuned.

## What the repo provides

| Script | Purpose |
|--------|---------|
| `scripts/safe_disk_cleanup.bat` | **PRE** / **POST** / **REPORT** entry point; delegates runtime deletes to `cleanup_c_drive_generated_files.bat`. **REPORT** also runs `check_disk_usage.ps1`. |
| `scripts/cleanup_c_drive_generated_files.bat` | Deletes **generated** paths only (reports, status, build-summary, workspace `.maestro`, temp dirs, flags, Maestro profile tests/screenshots on PRE). |
| `scripts/check_disk_usage.ps1` | Read-only sizes: workspace, Jenkins home / jobs / builds, npm, pip, `.maestro`, TEMP. |
| `scripts/safe_cache_cleanup_report.bat` | Lightweight batch-only size lines + commented `npm`/`pip` hints (no deletes). |

## Jenkins retention (already optimized in `Jenkinsfile`)

- **Stash** excludes `.git`, `node_modules`, `.maestro`, generated dirs, and `**/*.zip` so agents get sources without bloating the controller stash.
- **`preserveStashes`** and **`artifactNumToKeepStr`** are reduced to limit duplicate archived Excel/logs/zips/screenshots while keeping recent history.

To tighten further: adjust **`artifactNumToKeepStr`** / **`numToKeepStr`** in `Jenkinsfile` → `options` → `buildDiscarder` (safety over aggression — keep enough builds for your audit needs).

## What is safe to clean

**Safe (automated PRE/POST):**

- Workspace `reports/`, `status/`, `build-summary/`, `.maestro/`, `logs/`, `test-results/`, `maestro-report/`, `temp/`, `collected-artifacts/`, `ai-doctor/artifacts/`, root `*.zip` / flags — **after** Jenkins has archived artifacts on POST, or **before** a fresh run on PRE.
- On PRE only: `%USERPROFILE%\.maestro\tests` and `\screenshots` (Maestro runtime noise).

**Do not delete**

- Any **Maestro YAML**, **flows/**, **elements/**, **ATP TestCase Flows/**, **Printing** / **Non printing** flow trees.
- **Source scripts**, **`package.json`**, **`Jenkinsfile`**.
- **Jenkins archived builds** until you have copied what you need — remove via Jenkins UI / discard settings, not by guessing paths.

## How to run cleanup safely

From repo root (adjust path if needed):

```bat
REM Sizes only — no deletes
scripts\safe_disk_cleanup.bat REPORT
scripts\safe_disk_cleanup.bat REPORT "%WORKSPACE%"

REM Before local/Jenkins run (after checkout)
scripts\safe_disk_cleanup.bat PRE "%WORKSPACE%"

REM After archiveArtifacts (Jenkins already calls this pattern)
scripts\safe_disk_cleanup.bat POST "%WORKSPACE%"
```

Optional **npm/pip cache** trim (refetch cost on next install):

```bat
set SAFE_DISK_CLEANUP_CONFIRM_CACHE=YES
scripts\safe_disk_cleanup.bat PRE "%WORKSPACE%" CACHE
```

## How to verify space usage

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\check_disk_usage.ps1
```

With explicit workspace:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\check_disk_usage.ps1 -Workspace "C:\JenkinsAgent\workspace\YourJob"
```

On the **Jenkins controller**, set `JENKINS_HOME` in the environment (or run PowerShell from a session where it is set) so `check_disk_usage.ps1` can measure `jobs` and `jobs/*/builds`.

**Manual Jenkins cleanup:** Job → **Configure** → **Discard old builds**, or delete individual builds from **Build History** after confirming artifacts are no longer needed.

## Also see

- `docs/local_jenkins_disk_cleanup.md` — stash/archive-focused notes  
- [Maestro CLI](https://docs.maestro.dev/maestro-cli/maestro-cli-commands-and-options) — reference for runners (flows unchanged by cleanup docs)
