# Copyright (c) 2026 Ivan Soprun
"""Rotating UTF-8 file log under the product data dir (FXLOG).

The shipped exe has no console, so stderr-only logging loses every
backend error. This module owns ``<data>/logs/agent-si.log``
(rotating 5 MB x 3, UTF-8, created at start, frozen exe and source
alike): the logging root at INFO (uvicorn errors land here, access
logging stays off), unhandled exceptions with tracebacks
(sys.excepthook, threading.excepthook, every new asyncio loop via a
policy hook, plus the FastAPI 500 handler registered by
backend.app.create_app), engine plus chat-stream terminal failures
with run id, provider 4xx/5xx with status only, and the app
start/stop/version/port lines.

Redaction reuses ``agent_si.runtime.devrun.actions.redact_text`` on
every formatted record: no key/token patterns ever reach the file.
Request/response bodies, prompts and the UI session token are never
logged by construction (only run ids, class names, statuses and
redacted tracebacks travel here).
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import threading
import traceback
from logging.handlers import RotatingFileHandler
from typing import Any, Optional

LOG_DIR_NAME = "logs"
LOG_FILE_NAME = "agent-si.log"
LOG_MAX_BYTES = 5 * 1024 * 1024
LOG_BACKUPS = 3

#: Cap on distinct installed log files per process (test suites build
#: many apps on throwaway dirs; the oldest file handler is evicted).
_MAX_INSTALLED_FILES = 16

_install_lock = threading.Lock()
_installed_for: list = []
_hooks_installed = False


def log_dir_for(data_root: Any) -> Optional[str]:
    """Log dir under the data root; None when the root is unusable."""
    if not data_root:
        return None
    try:
        return os.path.join(os.path.abspath(str(data_root)),
                            LOG_DIR_NAME)
    except (TypeError, ValueError):
        return None


def log_file_for(data_root: Any) -> Optional[str]:
    """Full log file path for a data root; None when unusable."""
    directory = log_dir_for(data_root)
    if directory is None:
        return None
    return os.path.join(directory, LOG_FILE_NAME)


def _redact_text(text: str) -> str:
    """Redact secret patterns; never raises, never returns non-str."""
    try:
        from agent_si.runtime.devrun import actions as _actions

        return str(_actions.redact_text(str(text)))
    except Exception:
        return str(text)


class _RedactingFormatter(logging.Formatter):
    """Formatter scrubbing secret patterns from the rendered record."""

    def format(self, record: logging.LogRecord) -> str:
        return _redact_text(super().format(record))


def _handle_asyncio_exception(loop: Any, context: Any) -> None:
    """asyncio loop handler: log the loop failure, keep the loop alive."""
    try:
        message = str((context or {}).get("exception", None)
                      or (context or {}).get("message", "asyncio failure"))
    except Exception:
        message = "asyncio failure"
    try:
        logging.getLogger("agent_si.asyncio").error(
            "asyncio loop failure: %s", message)
    except Exception:
        pass
    default = getattr(loop, "default_exception_handler", None)
    if callable(default):
        try:
            default(context)
        except Exception:
            pass


class _FileLogPolicy(asyncio.DefaultEventLoopPolicy):
    """Loop policy attaching the file-log asyncio handler to new loops."""

    def new_event_loop(self) -> Any:
        loop = super().new_event_loop()
        try:
            loop.set_exception_handler(_handle_asyncio_exception)
        except Exception:
            pass
        return loop


def _install_hooks() -> None:
    """Process-wide unhandled-failure hooks; installed once."""
    global _hooks_installed
    if _hooks_installed:
        return
    _hooks_installed = True

    def _excepthook(exc_type: Any, exc: Any, tb: Any) -> None:
        try:
            logging.getLogger("agent_si.unhandled").error(
                "unhandled exception: %s: %s",
                getattr(exc_type, "__name__", type(exc).__name__), exc,
                exc_info=(exc_type, exc, tb))
        except Exception:
            pass

    def _thread_hook(args: Any) -> None:
        try:
            logging.getLogger("agent_si.unhandled").error(
                "unhandled thread exception in %s: %s: %s",
                getattr(args, "thread", None),
                getattr(getattr(args, "exc_type", None),
                        "__name__", "?"),
                getattr(args, "exc_value", None),
                exc_info=(getattr(args, "exc_type", None),
                          getattr(args, "exc_value", None),
                          getattr(args, "exc_traceback", None)))
        except Exception:
            pass

    try:
        sys.excepthook = _excepthook  # type: ignore[assignment]
    except Exception:
        pass
    try:
        threading.excepthook = _thread_hook  # type: ignore[assignment]
    except Exception:
        pass
    try:
        asyncio.set_event_loop_policy(_FileLogPolicy())
    except Exception:
        pass


def install(data_root: Any, *, version: str = "",
            max_bytes: int = LOG_MAX_BYTES,
            backups: int = LOG_BACKUPS) -> Optional[str]:
    """Attach the rotating file log for a data root; idempotent.

    Creates ``<root>/logs`` and adds one RotatingFileHandler (UTF-8,
    INFO) to the logging root plus the process-wide unhandled-failure
    hooks. Returns the log file path, or None when the root is
    unusable. Re-installing the same file is a no-op; each distinct
    file stays open (evicting the oldest past the cap).
    """
    directory = log_dir_for(data_root)
    if directory is None:
        return None
    try:
        os.makedirs(directory, exist_ok=True)
    except OSError:
        return None
    path = os.path.join(directory, LOG_FILE_NAME)
    with _install_lock:
        if path in _installed_for:
            _install_hooks()
            return path
        try:
            handler = RotatingFileHandler(
                path, maxBytes=int(max_bytes),
                backupCount=int(backups), encoding="utf-8")
        except (OSError, ValueError, OverflowError):
            return None
        handler.setLevel(logging.INFO)
        handler.setFormatter(_RedactingFormatter(
            "%(asctime)s %(levelname)s %(name)s: %(message)s"))
        logging.getLogger().setLevel(logging.INFO)
        logging.getLogger().addHandler(handler)
        _installed_for.append(path)
        while len(_installed_for) > _MAX_INSTALLED_FILES:
            oldest = _installed_for.pop(0)
            for existing in list(logging.getLogger().handlers):
                try:
                    if (isinstance(existing, RotatingFileHandler)
                            and os.path.abspath(
                                str(getattr(existing, "baseFilename",
                                            ""))) == oldest):
                        logging.getLogger().removeHandler(existing)
                        try:
                            existing.close()
                        except Exception:
                            pass
                except Exception:
                    pass
        _install_hooks()
    if version:
        try:
            logging.getLogger("agent_si.filelog").info(
                "agent-si %s file log ready at %s", str(version), path)
        except Exception:
            pass
    return path


def log_exception(tag: str, run_id: Any, exc: BaseException) -> None:
    """Log a terminal failure with run id, class and traceback.

    ``tag`` names the failing lane (engine, chat-stream, request);
    ``run_id`` travels so the UI-side code names the same run. The
    rendered traceback passes the secret redactor before it is stored.
    """
    try:
        text = "".join(traceback.format_exception(
            type(exc), exc, getattr(exc, "__traceback__", None)))
    except Exception:
        try:
            text = "%s: %s" % (type(exc).__name__, exc)
        except Exception:
            text = "unprintable failure"
    try:
        logging.getLogger("agent_si.run").error(
            "run %s %s terminal failure: %s: %s",
            run_id, tag, type(exc).__name__, _redact_text(text))
    except Exception:
        pass
