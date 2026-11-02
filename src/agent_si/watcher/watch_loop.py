"""Watcher background loop: live ticks plus declared-service probes.

Row WATCHGAP: the seam had no background loop, so live runs recorded no
WATCH_DECISION rows and declared-service outages stayed invisible without
a manual POST. One asyncio task per app lifespan closes the gap: each
pass probes every declared non-container service through
``service_status.run_check`` (declared http/tcp hosts only, never any
undeclared host), notifies through ``service_watch.tick`` so SERVICE_STATE
rows land, signals the existing outage path on a transition to DOWN so
OUTAGE_SIGNAL rows land, and ticks ``engine.tick`` for projects with a
live run or chat stream so WATCH_DECISION rows land. Probe and tick
errors are logged and never kill the loop or block a request; the loop
itself never stops (no auto-stop hides an outage).
"""

from __future__ import annotations

import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from agent_si.automation import runner as _runner_home
from agent_si.automation import service_status as _status_home
from agent_si.automation import service_watch as _service_watch_home
from agent_si.watcher import engine as _engine_home
from agent_si.watcher import journal as _journal_home
from agent_si.watcher import outage as _outage_home

#: Dotted name of the frozen automation contract module. Product code
#: keeps no static import of it; the module object is resolved late at
#: call time, so the bound journal reference is the same object the
#: contract tests use.
_IFACE_MODULE = "agent_si.automation.interface"


def _auto_iface():
    """Return the frozen automation contract module object."""
    try:
        return sys.modules[_IFACE_MODULE]
    except KeyError:
        raise RuntimeError(
            "frozen contract %r is not imported" % (_IFACE_MODULE,)
        )

__all__ = (
    "INTERVAL_S",
    "is_running",
    "lifespan",
    "start",
    "stop",
    "tick_once",
)

log = logging.getLogger(__name__)

#: Product pass interval in seconds. The product loop always uses this
#: value; tests shorten it through the start()/lifespan() parameter only.
INTERVAL_S = 30.0

#: Live automation run states: a run in one of these keeps its project live.
_LIVE_RUN_STATES = ("RUNNING", "PENDING")

#: Attached background pass task, or None when no loop is running.
_TASK: Optional[asyncio.Task] = None

#: Interval the attached task sleeps between passes.
_INTERVAL_S = INTERVAL_S

#: App the attached task ticks (chat-stream live check needs it).
_APP: Any = None


def is_running() -> bool:
    """True while the background pass task is attached and not done."""
    task = _TASK
    return task is not None and not task.done()


def _ensure_journal_hook() -> None:
    """Bind the watcher-owned automation journal reference (once).

    The frozen automation contract carries ``journal_append_event`` as
    an unbound reference owned by the watcher lane, and the served app
    leaves it unbound while contract suites bind their own doubles.
    The loop binds the real watcher ``journal.append_event`` only while
    the reference is still that pristine unbound reference (never over
    a double), so service probes and notify ticks journal real rows
    wherever the loop runs. A failure here never stops the loop; the
    pass logs it.
    """
    try:
        module = _auto_iface()
        current = getattr(module, "journal_append_event", None)
        if getattr(current, "__module__", "") == module.__name__:
            module.journal_append_event = _journal_home.append_event
    except Exception as err:
        log.warning("watch loop journal hook check failed: %s", err)


def _candidate_projects() -> List[str]:
    """Projects one pass may tick: declared services plus journal facts.

    Journal projects come from the stored-rows registry (the same
    stored-fact read the automation lane uses for its own registry, so
    a project with facts but no declared service still gets watched).
    A scan failure degrades to the other source, never to an empty loop.
    """
    found: List[str] = []

    def _add(project_id: object) -> None:
        text = str(project_id or "")
        if text and text not in found:
            found.append(text)

    try:
        for project_id, _service_id, _kind in (
                _status_home.declared_probe_targets()):
            _add(project_id)
    except Exception as err:
        log.warning("watch loop service scan failed: %s", err)
    try:
        rows = getattr(_journal_home, "_ROWS", {})
        if isinstance(rows, dict):
            for project_id in rows:
                _add(project_id)
    except Exception as err:
        log.warning("watch loop journal scan failed: %s", err)
    return found


def _runner_live(project_id: str) -> bool:
    """True while the automation registry holds a live run for the project."""
    try:
        for run in _runner_home.list_runs(project_id):
            if str(getattr(run, "state", "")) in _LIVE_RUN_STATES:
                return True
    except Exception as err:
        log.warning(
            "watch loop live-run check failed for %s: %s", project_id, err)
    return False


def _chat_live(app: Any) -> bool:
    """True while a chat stream or manager live row is open.

    The bridge live registry is global (stream ids carry no project),
    so one open stream marks the pass live for every candidate project;
    engine.tick itself stays per-project and journals only that
    project's rows. Manager live rows are read from the recorded store
    only (never the parts-register overlay, which also lists idle rows).
    """
    try:
        bridge = getattr(getattr(app, "state", None),
                         "chat_stream_bridge", None)
        live = getattr(bridge, "_live", None) if bridge is not None else None
        if isinstance(live, dict) and len(live) > 0:
            return True
    except Exception as err:
        log.warning("watch loop chat-stream check failed: %s", err)
    try:
        from agent_si.backend import agents_live as _live_home
        store = getattr(_live_home, "_LIVE_ROWS", {})
        if isinstance(store, dict) and len(store) > 0:
            return True
    except Exception as err:
        log.warning("watch loop live-rows check failed: %s", err)
    return False


def _tick_services(project_id: str) -> int:
    """Probe one project's declared services; tick; signal DOWN outages.

    Returns the count of probed services. A refused or failed probe
    (protected rows, undeclared ids, socket errors) is logged and
    skipped; service_watch.tick still runs so stored changes notify.
    A fresh observation of DOWN after any other state calls the
    existing outage path once (its own dedupe replays repeats).
    """
    checked = 0
    for target_project, service_id, kind in (
            _status_home.declared_probe_targets()):
        if target_project != project_id:
            continue
        try:
            previous = str(_status_home.get(service_id).state)
        except Exception as err:
            log.warning(
                "watch loop status read failed for %s: %s", service_id, err)
            continue
        try:
            observed = _status_home.run_check(service_id, kind)
        except Exception as err:
            log.warning(
                "watch loop probe failed for %s: %s", service_id, err)
            continue
        checked += 1
        if str(observed.state) == "DOWN" and previous != "DOWN":
            try:
                _outage_home.signal_outage(
                    project_id, service_id, "service DOWN: %s" % service_id)
            except Exception as err:
                log.warning(
                    "watch loop outage signal failed for %s: %s",
                    service_id, err)
    try:
        _service_watch_home.tick(project_id)
    except Exception as err:
        log.warning(
            "watch loop service tick failed for %s: %s", project_id, err)
    return checked


def tick_once(app: Any = None) -> Dict[str, Any]:
    """Run one loop pass now (synchronous; the background task calls this).

    Every candidate project gets its service probes plus its notify
    tick; projects with a live run or an open chat stream additionally
    get an engine tick. Per-project failures are logged and skipped,
    never abort the pass.
    """
    _ensure_journal_hook()
    target = app if app is not None else _APP
    chat = _chat_live(target) if target is not None else False
    services_checked = 0
    watched: List[str] = []
    for project_id in _candidate_projects():
        try:
            services_checked += _tick_services(project_id)
        except Exception as err:
            log.warning(
                "watch loop service pass failed for %s: %s", project_id, err)
            continue
        try:
            if _runner_live(project_id) or chat:
                _engine_home.tick(project_id)
                watched.append(project_id)
        except Exception as err:
            log.warning(
                "watch loop watch pass failed for %s: %s", project_id, err)
    return {"services_checked": services_checked, "watched": watched}


async def _run() -> None:
    """Pass forever until cancelled; a pass failure never stops the loop.

    The pass runs off the event loop (to_thread): service probes and
    engine ticks are synchronous blocking work, and inline execution
    stalled every request for the whole pass (~10 s per 30 s pass with
    slow declared services). Off-loop passes never stall a request.
    """
    while True:
        try:
            await asyncio.to_thread(tick_once, _APP)
        except Exception as err:
            log.warning("watch loop pass failed: %s", err)
        await asyncio.sleep(_INTERVAL_S)


def start(app: Any = None, interval_s: float = INTERVAL_S) -> asyncio.Task:
    """Attach one background pass task (idempotent; needs a running loop).

    Product callers pass the app and keep the default interval; tests
    shorten the interval through ``interval_s`` only. Returns the
    attached task; a live task is returned unchanged (never doubled).
    """
    global _TASK, _INTERVAL_S, _APP
    task = _TASK
    if task is not None and not task.done():
        return task
    try:
        wait = float(interval_s)
    except (TypeError, ValueError):
        wait = INTERVAL_S
    if wait <= 0:
        wait = INTERVAL_S
    _INTERVAL_S = wait
    if app is not None:
        _APP = app
    _ensure_journal_hook()
    loop = asyncio.get_running_loop()
    _TASK = loop.create_task(_run(), name="fxwatchloop")
    return _TASK


async def stop() -> None:
    """Cancel the background pass task; a missing task is a no-op."""
    global _TASK
    task = _TASK
    _TASK = None
    if task is None:
        return
    if not task.done():
        task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    except Exception as err:
        log.warning("watch loop stop failed: %s", err)


@asynccontextmanager
async def lifespan(app: Any, interval_s: float = INTERVAL_S):
    """Lifespan wrapper: start on entry, cancelled on exit (never raises)."""
    start(app, interval_s=interval_s)
    try:
        yield app
    finally:
        await stop()
