"""Maestro Runner — invokes existing ATP stage runner (no YAML changes)."""

from __future__ import annotations

import logging
import subprocess
import sys
import time
from pathlib import Path

from models import ModulePlan, ModuleResult, TestStatus

logger = logging.getLogger("ai-agent.maestro")


class MaestroRunner:
    """
    Thin wrapper around ``scripts/jenkins_atp_stage.py all <Folder> ...``.

    This keeps Maestro execution identical to Jenkins ATP stages.
    """

    def __init__(
        self,
        repo_root: Path,
        *,
        app_package: str,
        maestro_cmd: str,
        clear_state: str = "true",
    ) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.app_package = app_package
        self.maestro_cmd = maestro_cmd
        self.clear_state = clear_state
        self.stage_script = self.repo_root / "scripts" / "jenkins_atp_stage.py"

    def run_module(self, plan: ModulePlan, *, device_hint: str | None = None) -> ModuleResult:
        t0 = time.time()
        env = None
        import os

        env = os.environ.copy()
        if device_hint:
            # Prefer this device when orchestrator reads ATP_ORCH_DEVICES / detected list.
            env["ATP_ORCH_DEVICES"] = device_hint
            env["ANDROID_SERIAL"] = device_hint

        if not self.stage_script.is_file():
            return ModuleResult(
                module=plan.name,
                status=TestStatus.FAIL,
                duration_sec=0,
                exit_code=1,
                notes="jenkins_atp_stage.py missing",
                device_serial=device_hint or "",
            )

        cmd = [
            sys.executable,
            str(self.stage_script),
            "all",
            plan.folder,
            self.app_package,
            self.clear_state,
            self.maestro_cmd,
        ]
        logger.info("running module=%s cmd=%s", plan.name, " ".join(cmd))
        proc = subprocess.run(
            cmd,
            cwd=str(self.repo_root),
            env=env,
            check=False,
        )
        elapsed = time.time() - t0
        status = TestStatus.PASS if proc.returncode == 0 else TestStatus.FAIL
        # Approximate counts from flow list; ATP Excel remains source of truth for details.
        passed = plan.flow_count if status == TestStatus.PASS else 0
        failed = 0 if status == TestStatus.PASS else plan.flow_count
        return ModuleResult(
            module=plan.name,
            status=status,
            device_serial=device_hint or "",
            duration_sec=round(elapsed, 2),
            passed=passed,
            failed=failed,
            skipped=0,
            exit_code=proc.returncode,
            notes=f"via jenkins_atp_stage exit={proc.returncode}",
        )
