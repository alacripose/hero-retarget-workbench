"""Background work that never calls Blender from a worker thread.

Subprocess work (S2V inventory/extraction, resourcecompiler) runs in a daemon
thread. A Blender timer polls it on the main thread and updates the panel. The
weight solver is different: it needs Blender data, so it uses its own chunked
timer in ``weights.py``.
"""
from __future__ import annotations

import threading
import traceback
from typing import Callable

import bpy

_ACTIVE: "BackgroundJob | None" = None
_UNLOADING = False


class BackgroundJob:
    def __init__(self, settings, label: str, work: Callable, on_done: Callable, on_error: Callable):
        self.settings = settings
        self.label = label
        self.work = work
        self.on_done = on_done
        self.on_error = on_error
        self._lock = threading.Lock()
        self._progress = 0.0
        self._message = "starting"
        self._result = None
        self._error: BaseException | None = None
        self._finished = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True, name="dmf-background")
        self.settings.job_running = True
        self.settings.job_kind = "BACKGROUND"
        self.settings.job_label = label
        self.settings.job_message = "starting"
        self.settings.job_progress = 0.0
        self.settings.job_cancellable = False
        self._thread.start()
        self._timer = bpy.app.timers.register(self._tick, first_interval=0.1, persistent=True)

    def progress(self, value: float, message: str = "") -> None:
        with self._lock:
            self._progress = max(0.0, min(1.0, float(value)))
            if message:
                self._message = message

    def _run(self) -> None:
        try:
            self._result = self.work(self.progress)
        except BaseException as error:  # the timer needs the message, not a traceback dialog
            self._error = error
            traceback.print_exc()
        finally:
            self._finished.set()

    def _tick(self):
        global _ACTIVE
        if _UNLOADING:
            return None
        with self._lock:
            progress = self._progress
            message = self._message
        self.settings.job_progress = max(self.settings.job_progress, progress)
        if message:
            self.settings.job_message = message
        if not self._finished.is_set():
            return 0.1
        self.settings.job_running = False
        self.settings.job_progress = 1.0
        self.settings.job_message = ""
        _ACTIVE = None
        if self._error is not None:
            self.on_error(self._error)
        else:
            self.on_done(self._result)
        return None


def active() -> BackgroundJob | None:
    return _ACTIVE


def is_running() -> bool:
    return _ACTIVE is not None


def start(settings, label: str, work: Callable, on_done: Callable, on_error: Callable) -> str | None:
    global _ACTIVE
    if _ACTIVE is not None:
        return "another background job is already running"
    _ACTIVE = BackgroundJob(settings, label, work, on_done, on_error)
    return None


def unregister() -> None:
    global _UNLOADING, _ACTIVE
    _UNLOADING = True
    if _ACTIVE is not None:
        try:
            bpy.app.timers.unregister(_ACTIVE._tick)
        except Exception:
            pass
        _ACTIVE = None
