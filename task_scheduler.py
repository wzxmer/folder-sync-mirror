#!/usr/bin/env python3
"""Task scheduling for sync and zzc jobs."""

from __future__ import annotations

from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock
from typing import Any, Callable


TaskRunner = Callable[["TaskDefinition"], bool]


@dataclass(frozen=True)
class TaskDefinition:
    id: str
    name: str
    enabled: bool
    source: Path
    target: Path
    include: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    target_protect: tuple[str, ...] = ()
    target_clean: tuple[str, ...] = ()
    delete_extra: bool = True
    interval_seconds: float = 0.0
    scheduled_tasks: object | None = None

    def write_paths(self) -> tuple[Path, ...]:
        paths = [self.target]
        if self.scheduled_tasks:
            dicts = getattr(self.scheduled_tasks, "zzc_target_dicts", ())
            for item in dicts:
                path = Path(item)
                if not path.is_absolute():
                    path = self.source / item
                paths.append(path)
        return tuple(_normalize_path(path) for path in paths if str(path).strip())


@dataclass
class ResourceLockManager:
    _locks: dict[str, Lock] = field(default_factory=dict)
    _guard: Lock = field(default_factory=Lock)

    def acquire(self, task: TaskDefinition) -> tuple[Lock, ...]:
        keys = _resource_keys(task.write_paths())
        with self._guard:
            locks = []
            for key in keys:
                lock = self._locks.get(key)
                if lock is None:
                    lock = Lock()
                    self._locks[key] = lock
                locks.append(lock)
        acquired: list[Lock] = []
        try:
            for lock in locks:
                lock.acquire()
                acquired.append(lock)
        except Exception:
            for lock in reversed(acquired):
                lock.release()
            raise
        return tuple(acquired)


@dataclass
class TaskScheduler:
    lock_manager: ResourceLockManager = field(default_factory=ResourceLockManager)

    def run(self, tasks: list[TaskDefinition] | tuple[TaskDefinition, ...], runner: TaskRunner) -> dict[str, bool]:
        results: dict[str, bool] = {}
        enabled_tasks = [task for task in tasks if task.enabled]
        for task in tasks:
            if not task.enabled:
                results[task.id] = False
        if not enabled_tasks:
            return results

        def run_one(task: TaskDefinition) -> tuple[str, bool]:
            locks = self.lock_manager.acquire(task)
            try:
                return task.id, bool(runner(task))
            finally:
                for lock in reversed(locks):
                    lock.release()

        with ThreadPoolExecutor(max_workers=len(enabled_tasks)) as executor:
            future_map = {executor.submit(run_one, task): task for task in enabled_tasks}
            for future in as_completed(future_map):
                task_id, ok = future.result()
                results[task_id] = ok
        return results


def _normalize_path(path: Path) -> Path:
    try:
        return path.resolve()
    except OSError:
        return path


def _resource_keys(paths: tuple[Path, ...]) -> tuple[str, ...]:
    keys: set[str] = set()
    for path in paths:
        resolved = _normalize_path(path)
        parts = resolved.parts
        current = Path(parts[0]) if parts else resolved
        for part in parts[1:]:
            current = current / part
            keys.add(str(current).replace("\\", "/").lower())
        keys.add(str(resolved).replace("\\", "/").lower())
    return tuple(sorted(keys))


def build_sync_task(config: Any) -> TaskDefinition:
    return TaskDefinition(
        id="sync",
        name="同步任务",
        enabled=True,
        source=config.source,
        target=config.target,
        include=config.include,
        exclude=config.exclude,
        target_protect=config.target_protect,
        target_clean=config.target_clean,
        delete_extra=config.delete_extra,
    )


def build_task_definition(task: Any) -> TaskDefinition:
    return TaskDefinition(
        id=task.id,
        name=task.name,
        enabled=task.enabled,
        source=task.source,
        target=task.target,
        include=task.include,
        exclude=task.exclude,
        target_protect=task.target_protect,
        target_clean=task.target_clean,
        delete_extra=task.delete_extra,
        interval_seconds=task.interval_seconds,
        scheduled_tasks=task.scheduled_tasks,
    )


def build_task_definitions(config: Any) -> tuple[TaskDefinition, ...]:
    tasks = config.tasks or ()
    if not tasks:
        return (build_sync_task(config),)
    return tuple(build_task_definition(task) for task in tasks)
