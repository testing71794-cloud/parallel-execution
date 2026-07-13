# AI workflow

1. **Plan** — scan `ATP TestCase Flows` (auto-discovers new folders).
2. **Devices** — `adb devices`; skip offline / not-booted.
3. **APK** — verify `com.kodaksmile`; install from `APK_PATH` if missing.
4. **Execute** — for each module call existing `jenkins_atp_stage.py all <Folder>`.
5. **Artifacts** — before/after screenshots, module video, logcat dump.
6. **Retry** — one automatic retry on module failure.
7. **Analyze** — rule classifier + optional `intelligent_platform` LLM.
8. **Vision** — optional provider hook (default null).
9. **Report** — HTML, PDF, Markdown, JSON under `ai-agent/reports/`.
10. **Sign-off** — `READY FOR RELEASE` or `NOT READY`.

All Maestro flows remain the source of truth for UI steps.
