"""Retry Manager — retry failed modules once (configurable)."""

from __future__ import annotations

import logging
from collections.abc import Callable

from models import ModulePlan, ModuleResult, TestStatus

logger = logging.getLogger("ai-agent.retry")


class RetryManager:
    def __init__(self, max_retries: int = 1) -> None:
        self.max_retries = max(0, int(max_retries))

    def run_with_retry(
        self,
        plan: ModulePlan,
        runner: Callable[[ModulePlan], ModuleResult],
    ) -> ModuleResult:
        result = runner(plan)
        if result.status == TestStatus.PASS or self.max_retries <= 0:
            return result

        for attempt in range(1, self.max_retries + 1):
            logger.warning(
                "retrying module=%s attempt=%s/%s prior_exit=%s",
                plan.name,
                attempt,
                self.max_retries,
                result.exit_code,
            )
            retry = runner(plan)
            retry.retried = True
            if retry.status == TestStatus.PASS:
                retry.status = TestStatus.RETRIED_PASS
                retry.notes = (retry.notes + f" | recovered after {attempt} retry").strip(" |")
                return retry
            result = retry
            result.status = TestStatus.RETRIED_FAIL
            result.notes = (result.notes + f" | still failing after {attempt} retry").strip(" |")
        return result
