from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal


class TaskSignals(QObject):
    started = Signal()
    finished = Signal()
    result = Signal(object)
    error = Signal(Exception)


class BackgroundTask(QRunnable):
    def __init__(self, task: Callable[[], Any]) -> None:
        super().__init__()
        self.task = task
        self.signals = TaskSignals()
        self.setAutoDelete(False)

    def run(self) -> None:
        self.signals.started.emit()
        try:
            result = self.task()
        except Exception as exc:  # noqa: BLE001
            self.signals.error.emit(exc)
        else:
            self.signals.result.emit(result)
        finally:
            self.signals.finished.emit()


class TaskRunner:
    def __init__(self) -> None:
        self._pool = QThreadPool.globalInstance()
        self._active_tasks: list[BackgroundTask] = []

    def start(
        self,
        task: Callable[[], Any],
        on_started: Callable[[], None] | None = None,
        on_result: Callable[[Any], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
        on_finished: Callable[[], None] | None = None,
    ) -> None:
        runnable = BackgroundTask(task)
        self._active_tasks.append(runnable)
        if on_started is not None:
            runnable.signals.started.connect(on_started)
        if on_result is not None:
            runnable.signals.result.connect(on_result)
        if on_error is not None:
            runnable.signals.error.connect(on_error)
        def cleanup() -> None:
            if runnable in self._active_tasks:
                self._active_tasks.remove(runnable)
        if on_finished is not None:
            runnable.signals.finished.connect(on_finished)
        runnable.signals.finished.connect(cleanup)
        self._pool.start(runnable)
