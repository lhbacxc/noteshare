from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal


class TaskSignals(QObject):
    started = Signal()
    finished = Signal()
    result = Signal(object)
    error = Signal(Exception)
    progress = Signal(object)


class BackgroundTask(QRunnable):
    def __init__(
        self,
        task: Callable[..., Any],
        *,
        task_accepts_progress: bool = False,
    ) -> None:
        super().__init__()
        self.task = task
        self.task_accepts_progress = task_accepts_progress
        self.signals = TaskSignals()
        self.setAutoDelete(False)

    def run(self) -> None:
        self._safe_emit(self.signals.started)
        try:
            if self.task_accepts_progress:
                result = self.task(self._emit_progress)
            else:
                result = self.task()
        except Exception as exc:  # noqa: BLE001
            self._safe_emit(self.signals.error, exc)
        else:
            self._safe_emit(self.signals.result, result)
        finally:
            self._safe_emit(self.signals.finished)

    def _emit_progress(self, payload: object) -> None:
        self._safe_emit(self.signals.progress, payload)

    def _safe_emit(self, signal, *args: Any) -> None:
        try:
            signal.emit(*args)
        except RuntimeError:
            return


class TaskRunner:
    def __init__(self) -> None:
        self._pool = QThreadPool.globalInstance()
        self._active_tasks: list[BackgroundTask] = []

    def start(
        self,
        task: Callable[..., Any],
        on_started: Callable[[], None] | None = None,
        on_result: Callable[[Any], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
        on_finished: Callable[[], None] | None = None,
        on_progress: Callable[[Any], None] | None = None,
        task_accepts_progress: bool = False,
    ) -> None:
        runnable = BackgroundTask(task, task_accepts_progress=task_accepts_progress)
        self._active_tasks.append(runnable)
        if on_started is not None:
            runnable.signals.started.connect(on_started)
        if on_result is not None:
            runnable.signals.result.connect(on_result)
        if on_error is not None:
            runnable.signals.error.connect(on_error)
        if on_progress is not None:
            runnable.signals.progress.connect(on_progress)
        def cleanup() -> None:
            if runnable in self._active_tasks:
                self._active_tasks.remove(runnable)
        if on_finished is not None:
            runnable.signals.finished.connect(on_finished)
        runnable.signals.finished.connect(cleanup)
        self._pool.start(runnable)
