#!/usr/bin/env python3
"""
Dynamic worker-pool scheduler for ATP Maestro runs.

Each USB device is an independent worker with a rotated (flow x device) task queue.
Workers run one Maestro subprocess at a time; devices execute concurrently.
Every flow runs exactly once per device (full matrix completion).
"""
from __future__ import annotations

import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class TaskOutcome:
    device_id: str
    exit_code: int


@dataclass(frozen=True)
class FlowDeviceTask:
    """One Maestro execution unit: single flow on single device."""

    flow: Path
    suite_id: str
    folder_name: str
    flow_base: str
    device_id: str

    @property
    def matrix_key(self) -> str:
        return f"{self.suite_id}::{self.flow_base}::{self.device_id}"


@dataclass
class SchedulerMetrics:
    wall_sec: float = 0.0
    tasks_total: int = 0
    tasks_ok: int = 0
    tasks_fail: int = 0
    per_device_sec: dict[str, float] = field(default_factory=dict)
    per_device_tasks: dict[str, int] = field(default_factory=dict)


def build_rotated_device_queues(
    *,
    flows: list[Path],
    devices: list[str],
    atp_root: Path,
    folder_name_fn: Callable[[Path, Path], str],
    suite_id_fn: Callable[[str], str],
) -> dict[str, list[FlowDeviceTask]]:
    """
  Build per-device task queues with rotated start index so round-1 spreads flows:
    Device0 -> Flow0, Device1 -> Flow1, ... then each worker continues its queue.
    """
    flow_rows: list[tuple[Path, str, str, str]] = []
    for flow in flows:
        folder = folder_name_fn(atp_root, flow)
        sid = suite_id_fn(folder)
        flow_rows.append((flow, sid, folder, flow.stem))

    n = len(flow_rows)
    queues: dict[str, list[FlowDeviceTask]] = {}
    for device_index, device_id in enumerate(devices):
        tasks: list[FlowDeviceTask] = []
        for offset in range(n):
            flow, sid, folder, fb = flow_rows[(device_index + offset) % n]
            tasks.append(
                FlowDeviceTask(
                    flow=flow,
                    suite_id=sid,
                    folder_name=folder,
                    flow_base=fb,
                    device_id=device_id,
                )
            )
        queues[device_id] = tasks
    return queues


class DynamicDeviceScheduler:
    """Thread-safe dynamic scheduler: one worker thread per device."""

    def __init__(
        self,
        *,
        repo: Path,
        devices: list[str],
        device_queues: dict[str, list[FlowDeviceTask]],
        execute_task: Callable[..., TaskOutcome],
        report_outcome: Callable[..., bool],
        write_flow_section: Callable[[FlowDeviceTask], None],
        worker_stagger_sec_fn: Callable[[int], float],
    ) -> None:
        self._repo = repo
        self._devices = list(devices)
        self._queues = device_queues
        self._execute_task = execute_task
        self._report_outcome = report_outcome
        self._write_flow_section = write_flow_section
        self._worker_stagger_sec_fn = worker_stagger_sec_fn
        self._lock = threading.Lock()
        self._completed: dict[str, TaskOutcome] = {}
        self._sections_seen: set[str] = set()
        self._metrics = SchedulerMetrics()
        self._queue_log_interval = int(os.environ.get("ATP_SCHEDULER_QUEUE_LOG_EVERY", "0") or "0")

    @property
    def metrics(self) -> SchedulerMetrics:
        return self._metrics

    def _log_queue_status(self, device_id: str, pending: int, label: str) -> None:
        if self._queue_log_interval <= 0 and label != "worker_done":
            return
        total_pending = sum(len(q) for q in self._queues.values())
        with self._lock:
            done = len(self._completed)
        print(
            f"[ATP] scheduler_queue device={device_id} event={label} "
            f"device_pending={pending} matrix_done={done}/{self._metrics.tasks_total} "
            f"global_pending≈{total_pending}",
            flush=True,
        )

    def _section_once(self, task: FlowDeviceTask) -> None:
        key = f"{task.suite_id}::{task.flow_base}"
        with self._lock:
            if key in self._sections_seen:
                return
            self._sections_seen.add(key)
        self._write_flow_section(task)

    def _device_worker(self, device_id: str, device_index: int) -> list[TaskOutcome]:
        tasks = list(self._queues.get(device_id, []))
        outcomes: list[TaskOutcome] = []
        stagger = self._worker_stagger_sec_fn(device_index)
        if stagger > 0:
            print(
                f"[ATP] worker_stagger device={device_id} worker_index={device_index} sleep_sec={stagger:.1f}",
                flush=True,
            )
            time.sleep(stagger)

        worker_t0 = time.time()
        print(
            f"[ATP] worker_start device={device_id} tasks={len(tasks)} ts={worker_t0:.3f}",
            flush=True,
        )
        self._log_queue_status(device_id, len(tasks), "worker_start")

        for task_idx, task in enumerate(tasks):
            pending_after = len(tasks) - task_idx - 1
            self._section_once(task)
            print(
                f"[ATP] task_pull device={device_id} flow={task.flow_base} "
                f"task={task_idx + 1}/{len(tasks)} pending_on_device={pending_after}",
                flush=True,
            )
            self._log_queue_status(device_id, pending_after, "task_start")
            try:
                outcome = self._execute_task(
                    task=task,
                    device_index=device_index,
                    worker_startup=(task_idx == 0),
                )
            except Exception as exc:
                print(
                    f"[ATP] task_error device={device_id} flow={task.flow_base} error={exc}",
                    flush=True,
                )
                outcome = TaskOutcome(device_id=device_id, exit_code=1)

            with self._lock:
                self._completed[task.matrix_key] = outcome
                if outcome.exit_code == 0:
                    self._metrics.tasks_ok += 1
                else:
                    self._metrics.tasks_fail += 1

            self._report_outcome(task, outcome)
            outcomes.append(outcome)
            self._log_queue_status(device_id, pending_after, "task_done")

        worker_elapsed = time.time() - worker_t0
        with self._lock:
            self._metrics.per_device_sec[device_id] = worker_elapsed
            self._metrics.per_device_tasks[device_id] = len(tasks)
        print(
            f"[ATP] worker_done device={device_id} tasks={len(tasks)} elapsed_sec={worker_elapsed:.1f}",
            flush=True,
        )
        self._log_queue_status(device_id, 0, "worker_done")
        return outcomes

    def run(self) -> tuple[list[TaskOutcome], bool]:
        """Run all device workers; return (all outcomes, matrix_complete)."""
        all_tasks = [t for q in self._queues.values() for t in q]
        self._metrics.tasks_total = len(all_tasks)
        run_t0 = time.time()

        print(
            f"[ATP] scheduler_start model=dynamic_worker_pool devices={len(self._devices)} "
            f"flows_matrix={self._metrics.tasks_total} "
            f"({len(all_tasks) // max(1, len(self._devices))} flows x {len(self._devices)} devices)",
            flush=True,
        )
        for di, dev in enumerate(self._devices):
            q = self._queues.get(dev, [])
            preview = ", ".join(t.flow_base for t in q[:4])
            if len(q) > 4:
                preview += ", ..."
            print(f"[ATP] worker_queue device={dev} order=[{preview}]", flush=True)

        all_outcomes: list[TaskOutcome] = []
        executor = ThreadPoolExecutor(max_workers=len(self._devices), thread_name_prefix="atp-dev")
        try:
            futures = {
                executor.submit(self._device_worker, dev, idx): dev
                for idx, dev in enumerate(self._devices)
            }
            for fut in as_completed(futures):
                dev = futures[fut]
                try:
                    all_outcomes.extend(fut.result())
                except Exception as exc:
                    print(f"[ATP] worker_crashed device={dev} error={exc}", flush=True)
        finally:
            executor.shutdown(wait=True, cancel_futures=False)

        self._metrics.wall_sec = time.time() - run_t0
        matrix_ok = self._validate_matrix(all_tasks)
        self._print_summary()
        overall_failed = self._metrics.tasks_fail > 0 or not matrix_ok
        return all_outcomes, overall_failed

    def _validate_matrix(self, expected_tasks: list[FlowDeviceTask]) -> bool:
        expected = {t.matrix_key for t in expected_tasks}
        with self._lock:
            got = set(self._completed.keys())
        missing = expected - got
        extra = got - expected
        if missing:
            print(f"[ATP] scheduler_matrix_incomplete missing={len(missing)}", flush=True)
            for k in sorted(missing)[:20]:
                print(f"  [ATP] missing_task {k}", flush=True)
        if extra:
            print(f"[ATP] scheduler_matrix_warn unexpected={len(extra)}", flush=True)
        complete = not missing
        print(
            f"[ATP] scheduler_matrix complete={complete} "
            f"expected={len(expected)} recorded={len(got)}",
            flush=True,
        )
        return complete

    def _print_summary(self) -> None:
        m = self._metrics
        util_lines = []
        for dev in self._devices:
            sec = m.per_device_sec.get(dev, 0.0)
            cnt = m.per_device_tasks.get(dev, 0)
            util_lines.append(f"{dev}:{cnt}tasks/{sec:.0f}s")
        print(
            f"[ATP] scheduler_summary wall_sec={m.wall_sec:.1f} "
            f"tasks={m.tasks_total} ok={m.tasks_ok} fail={m.tasks_fail}",
            flush=True,
        )
        print(f"[ATP] scheduler_utilization {' | '.join(util_lines)}", flush=True)
        if m.tasks_total > 0 and len(self._devices) > 1:
            # Rough sequential baseline: sum of per-device work if one device did everything.
            seq_estimate = sum(m.per_device_sec.values()) / len(self._devices)
            if seq_estimate > 0:
                speedup = seq_estimate / max(m.wall_sec, 0.1)
                print(
                    f"[ATP] scheduler_vs_sequential_estimate speedup≈{speedup:.2f}x "
                    f"(wall {m.wall_sec:.0f}s vs ~{seq_estimate:.0f}s per-device-work/ndev)",
                    flush=True,
                )
