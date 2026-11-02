"""FXDEVRUN engine: the single public entry ``run_dev_task``.

Autonomous dev loop over a throwaway-or-real project folder: Director
plan (or plain answer), Manager order, per-part worker turn loops,
real check commands in the folder, a fresh auditor over real files
and real outputs, in-code verdicts, budget and stop honoured at
every step, live rows on every agent change, and the run-end hook
the way the manager calls it. Yields the same RunEvent objects the
chat stream consumes; new data fields ride the run record HITS.md
lists (extra SSE keys are never invented here).
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import uuid
from typing import Any


class _Stopped(Exception):
    """The run was stopped: cancel flag or stop-all."""

    code: str = "DEVRUN_STOPPED"


class _BudgetOut(Exception):
    """The run spent past the hard limit."""

    code: str = "DEVRUN_BUDGET_STOP"


class _InstallHeld(Exception):
    """An install ask holds the run: status line plus terminal approval."""

    code: str = "DEVRUN_INSTALL_ASK_NEEDED"

    def __init__(self, tool_id: str, command: str) -> None:
        super().__init__(
            "run held: install permission needed for %s" % (tool_id,))
        self.tool_id = str(tool_id)
        self.command = str(command)


#: Extra worker attempts after the first, per F-VERDICT.
_EXTRA_ATTEMPTS = 2


def wants_devrun(request: Any, bound_provider: Any, app: Any) -> bool:
    """True when the chat entry should drive the dev engine."""
    try:
        project = str(getattr(request, "project", "") or "")
        folder = str(getattr(request, "folder", "") or "")
    except Exception:
        return False
    return bool(project and folder and bound_provider is not None
                and app is not None)


def _run_event(event: str, turn: int, subtask: str, detail: str,
               data: Any = None) -> Any:
    """One chat-consumable RunEvent (the manager's own class).

    The human detail rides both the record field and ``data.text``,
    the key the chat SSE mapper forwards as the event text. Status
    lines always end with a newline so the chat renders them whole;
    every terminal event repeats its delta text exactly.
    """
    from agent_si.runtime.manager import RunEvent

    text = str(detail)
    if text and not text.endswith("\n"):
        text = text + "\n"
    body = dict(data or {})
    body.setdefault("text", text)
    return RunEvent(event=event, turn=turn, subtask_id=str(subtask),
                    detail=text, data=body)


def _journal_event(project: str, kind: str, summary: str) -> None:
    """One devrun journal row; a journal failure never breaks the run."""
    try:
        from agent_si.watcher import journal as _journal_store

        _journal_store.append_event(
            str(project), "devrun", str(kind), str(summary),
            (str(project),))
    except Exception:
        pass


def _ledger_total_line(record: Any) -> str:
    """Total tokens plus cost from the record ledger.

    The cost is UNKNOWN when any call has no price, never 0.
    """
    try:
        from decimal import Decimal as _Dec

        rows = record.get("ledger", []) if isinstance(
            record, dict) else []
    except Exception:
        rows = []
    total_in = 0
    total_out = 0
    unknown = not rows
    priced = None
    try:
        from decimal import Decimal as _Dec

        for row in rows or []:
            tokens = row.get("tokens") or {}
            for key, name in (("input", "in"), ("output", "out")):
                try:
                    value = tokens.get(key)
                except Exception:
                    value = None
                if isinstance(value, int) and not isinstance(value, bool):
                    if name == "in":
                        total_in += value
                    else:
                        total_out += value
            cost = row.get("cost")
            if cost is None or (isinstance(cost, str) and cost in (
                    "UNKNOWN", "UNAVAILABLE")):
                unknown = True
                continue
            try:
                amount = _Dec(str(cost))
            except Exception:
                unknown = True
                continue
            priced = amount if priced is None else priced + amount
    except Exception:
        unknown = True
    cost_text = "UNKNOWN" if unknown or priced is None else str(priced)
    return ("Total: %d input + %d output = %d tokens; cost: %s"
            % (total_in, total_out, total_in + total_out, cost_text))


def _run_end_tests(*, project_id: str, run_id: str,
                   task_id: str) -> dict[str, Any]:
    """ONE helper calling run_local_tests_at_run_end like manager.py.

    Returns {"ok", ...}; any error rides the row (never the stream).
    """
    try:
        from agent_si.test_runners import run_end as _run_end
        outcome = _run_end.run_local_tests_at_run_end(
            project_id=str(project_id), run_id=str(run_id),
            task_id=str(task_id), data_root=None, gateway=None,
            timeout_s=60.0)
    except Exception as exc:
        return {"ok": False,
                "error": "%s: %s" % (type(exc).__name__, exc)}
    try:
        return {"ok": True, "outcome": json.loads(json.dumps(outcome,
                                                             default=str))}
    except Exception:
        return {"ok": True, "outcome": str(outcome)}


def run_dev_task(request: Any, *, provider_adapter: Any = None,
                 stream_state: Any = None, app: Any = None) -> Any:
    """Stream one autonomous dev run as RunEvents (F-ENTRY).

    A generator: start, human progress deltas, then exactly one
    terminal event (done, cancelled, budget_stop or approval).
    """
    from agent_si.runtime.devrun import actions as _actions
    from agent_si.runtime.devrun import protocol as _protocol
    from agent_si.runtime.devrun import records as _records
    from agent_si.runtime.devrun import roles as _roles

    turn = 0
    run_id = uuid.uuid4().hex
    project = str(getattr(request, "project", "") or "")
    folder = str(getattr(request, "folder", "") or "")
    task_id = str(getattr(request, "task", "") or "dev")
    message = str(getattr(request, "message", "") or "")
    state = stream_state if isinstance(stream_state, dict) else {}
    record = _records.new_run_record(run_id, project, task_id, folder)
    procs: list[Any] = []
    attached: set[str] = set()
    known_parts: list[str] = []
    run_agents: dict[str, dict[str, Any]] = {}

    def _publish() -> None:
        try:
            store = getattr(getattr(app, "state", None),
                            "devrun_runs", None)
            if store is None:
                store = {}
                app.state.devrun_runs = store
            store[str(project)] = record
        except Exception:
            pass

    def _journal(kind: str, summary: str) -> None:
        _journal_event(project, kind, summary)

    def _stop_seen() -> bool:
        try:
            if dict(state).get("cancelled"):
                return True
        except Exception:
            pass
        if attached:
            try:
                from agent_si.backend import stop_all as _stop_all
                live = set(_stop_all.attached(str(project)))
                return not (attached & live)
            except Exception:
                return False
        return False

    def _check_stop() -> None:
        if _stop_seen():
            raise _Stopped()

    def _live(role: str, model: str, part: Any, attempt: int,
              step: str, path: str, tokens: Any, cost: Any,
              waits: list) -> None:
        try:
            from agent_si.backend import agents_live as _live_mod
            row_tokens = tokens if isinstance(tokens, dict) else {}
            row_waits = [str(item) for item in waits]
            if part is None:
                # Plan-level agents (director, manager) are scoped to
                # the whole part set once the plan lands; before that
                # they stay off the per-project panel prefix.
                if known_parts:
                    scope = "fxdevrun:%s:%s:%s" % (
                        project, ",".join(known_parts), role)
                else:
                    scope = "fxdevrun:plan:%s" % (role,)
                key = "%s/run/%s" % (run_id, role)
                label = "plan"
            else:
                scope = "fxdevrun:%s:%s:%s" % (project, part, role)
                key = "%s/%s/%s/%s" % (run_id, part, role, attempt)
                label = str(part)
            _live_mod.record_live_row(key, {
                "agent": "%s-%s" % (role, label),
                "scope": scope,
                "deliverable": "artifact://run/%s/%s" % (run_id, label),
                "status": "RUNNING",
                "role": str(role),
                "model": str(model),
                "step": 0,
                "file": str(path or ""),
                "cost": "UNKNOWN" if cost is None else str(cost),
                "tokens": row_tokens,
                "context": "UNKNOWN",
                "errors": [],
                "waits": row_waits,
            })
            if part is None:
                run_agents[str(role)] = {
                    "model": str(model), "tokens": row_tokens,
                    "cost": cost, "waits": row_waits}
        except Exception:
            pass

    def _reveal_plan(parts: list) -> None:
        """Re-scope plan-level agents onto the landed part set."""
        known_parts.extend([str(part["part_id"]) for part in parts])
        for saved_role, saved in run_agents.items():
            _live(saved_role, saved["model"], None, 0, "plan", "",
                  saved["tokens"], saved["cost"], saved["waits"])

    def _call(role: str, resolution: dict[str, Any], adapter: Any,
              messages: list, part: Any, attempt: int,
              waits: list) -> Any:
        _check_stop()
        try:
            response, over = _roles.invoke(
                app, adapter, resolution, messages, record=record,
                project_id=project, run_id=run_id, part=part,
                attempt=attempt)
        except _roles._BudgetOut as exc:
            raise _BudgetOut(str(exc)) from None
        usage = getattr(response, "usage", {}) or {}
        tokens = dict(usage) if isinstance(usage, dict) else {}
        ledger = (record.get("ledger", []) or [])[-1] if record.get(
            "ledger") else {}
        _live(role, str(resolution["model"]), part, attempt,
              "invoke", "", tokens,
              (ledger or {}).get("cost"), waits)
        if over:
            raise _BudgetOut(
                "budget stop: call cost exceeds the remaining budget")
        return response

    _publish()
    yield _run_event("start", turn, task_id,
                     "devrun run started for %s" % (task_id,),
                     {"run_id": run_id, "project_id": project,
                      "task_id": task_id})
    turn += 1
    try:
        if not os.path.isdir(str(folder)):
            record["summary"] = (
                "run failed: project folder %r is not a directory"
                % (folder,))
            record["success"] = False
            yield _run_event("delta", turn, task_id, record["summary"],
                             {"run_id": run_id, "success": False})
            turn += 1
            yield _run_event("done", turn, task_id, record["summary"],
                             {"run_id": run_id, "success": False})
            return
        try:
            from agent_si.backend import project_defaults as _defs
            _defs.ensure_project_defaults(app, str(project))
        except Exception:
            pass
        try:
            from agent_si.backend.orchestration import steplimits as _limits
            turn_cap = _limits.limits_for("task", str(project))
        except Exception as exc:
            record["summary"] = (
                "run failed: no step limits for project %r (%s)"
                % (project, exc))
            record["success"] = False
            yield _run_event("done", turn, task_id, record["summary"],
                             {"run_id": run_id, "success": False})
            return
        try:
            director = _roles.resolve_role(app, project, "director")
            manager = _roles.resolve_role(app, project, "manager")
            worker = _roles.resolve_role(app, project, "worker")
            auditor = _roles.resolve_role(app, project, "auditor")
        except _roles.RoleUnbound as exc:
            record["summary"] = "run failed: %s" % (exc,)
            record["success"] = False
            yield _run_event("delta", turn, task_id, record["summary"],
                             {"run_id": run_id, "success": False})
            turn += 1
            yield _run_event("done", turn, task_id, record["summary"],
                             {"run_id": run_id, "success": False})
            return
        try:
            director_adapter = _roles.build_adapter(app, director)
            manager_adapter = _roles.build_adapter(app, manager)
            auditor_adapter = _roles.build_adapter(app, auditor)
        except _roles.RoleUnbound as exc:
            record["summary"] = "run failed: %s" % (exc,)
            record["success"] = False
            yield _run_event("delta", turn, task_id, record["summary"],
                             {"run_id": run_id, "success": False})
            turn += 1
            yield _run_event("done", turn, task_id, record["summary"],
                             {"run_id": run_id, "success": False})
            return
        for role_name, resolution in (
                ("director", director), ("manager", manager),
                ("worker", worker), ("auditor", auditor)):
            try:
                why = json.dumps(resolution.get("why", {}),
                                 sort_keys=True, default=str)
            except Exception:
                why = "{}"
            yield _run_event(
                "delta", turn, task_id,
                "Role %s: %s/%s (%s why: %s)"
                % (role_name, resolution.get("provider"),
                   resolution.get("model"),
                   resolution.get("mode"), why),
                {"run_id": run_id, "part_id": None})
            turn += 1
        _check_stop()
        director_text = _call(
            "director", director, director_adapter,
            [{"role": "user", "content": _director_prompt(message)}],
            None, 0, waits=["plan"])
        try:
            parsed = _protocol.parse_director_reply(
                director_text.output_text or "")
        except _protocol.PlanError as exc:
            _check_stop()
            repair = _call(
                "director", director, director_adapter,
                [{"role": "user",
                  "content": _director_prompt(message)},
                 {"role": "assistant",
                  "content": director_text.output_text or ""},
                 {"role": "user",
                  "content": ("Your previous reply was not valid: %s "
                              "Return ONLY the corrected JSON object, "
                              "no prose.") % (exc,)}],
                None, 0, waits=["plan repair"])
            try:
                parsed = _protocol.parse_director_reply(
                    repair.output_text or "")
            except _protocol.PlanError as exc2:
                record["summary"] = (
                    "run failed: director plan invalid: %s" % (exc2,))
                record["success"] = False
                yield _run_event("delta", turn, task_id,
                                 record["summary"],
                                 {"run_id": run_id, "success": False})
                turn += 1
                yield _run_event("done", turn, task_id,
                                 record["summary"],
                                 {"run_id": run_id, "success": False})
                return
        if "answer" in parsed:
            answer = parsed["answer"]
            record["success"] = True
            record["summary"] = "run answered: plain answer, no parts"
            yield _run_event("delta", turn, task_id, answer,
                             {"run_id": run_id})
            turn += 1
        else:
            parts = parsed["parts"]
            _reveal_plan(parts)
            record["plan"] = parts
            record["contract_hash"] = hashlib.sha256(
                json.dumps(parts, sort_keys=True).encode(
                    "utf-8")).hexdigest()
            try:
                plan_why = json.dumps(director.get("why", {}),
                                      sort_keys=True, default=str)
            except Exception:
                plan_why = "{}"
            _journal("DEVRUN_PLAN", "plan of %d parts: %s "
                     "(director %s/%s why %s)"
                     % (len(parts), ", ".join(
                         str(part["part_id"]) for part in parts),
                         director.get("provider"),
                         director.get("model"), plan_why))
            yield _run_event(
                "delta", turn, task_id,
                "Director: plan of %d parts" % (len(parts),),
                {"run_id": run_id, "parts": len(parts)})
            turn += 1
            for part in parts:
                yield _run_event(
                    "delta", turn, task_id,
                    "Part %s: %s [files: %s]"
                    % (part["part_id"], part["goal"],
                       ", ".join(part["files"])),
                    {"run_id": run_id,
                     "part_id": part["part_id"]})
                turn += 1
            order = _manager_order(
                record, manager, manager_adapter, parts, project,
                run_id, _call)
            turn = yield from _run_parts(
                record=record, app=app, parts=parts, order=order,
                director=director, manager=manager, worker=worker,
                auditor=auditor, auditor_adapter=auditor_adapter,
                folder=folder, project=project, task_id=task_id,
                run_id=run_id, turn=turn, turn_cap=turn_cap,
                state=state, attached=attached, procs=procs,
                message=message, contract_hash=record["contract_hash"],
                publish=_publish, check_stop=_check_stop,
                stop_seen=_stop_seen, live=_live, call=_call)
        if "answer" not in parsed:
            record["success"] = all(
                part.get("verdict") == "PASS"
                for part in record.get("parts", [])) and bool(
                    record.get("parts", []))
            record["summary"] = _records.format_summary(record)
        _publish()
        if not record.get("stopped"):
            record["run_end"] = _run_end_tests(
                project_id=project, run_id=run_id, task_id=task_id)
        _journal("DEVRUN_END", record.get("summary") or "run ended")
        yield _run_event("delta", turn, task_id,
                         _ledger_total_line(record),
                         {"run_id": run_id})
        turn += 1
        yield _run_event("delta", turn, task_id, record["summary"],
                         {"run_id": run_id,
                          "success": bool(record.get("success"))})
        turn += 1
        yield _run_event("done", turn, task_id, record["summary"],
                         {"run_id": run_id,
                          "success": bool(record.get("success"))})
    except _Stopped:
        record["stopped"] = True
        record["success"] = False
        record["summary"] = "run stopped: user stop"
        _publish()
        _journal("DEVRUN_END", record.get("summary") or "run ended")
        yield _run_event("delta", turn, task_id, record["summary"],
                         {"run_id": run_id})
        turn += 1
        yield _run_event("cancelled", turn, task_id, record["summary"],
                         {"run_id": run_id})
    except _BudgetOut as exc:
        record["success"] = False
        record["summary"] = "run failed: %s" % (exc,)
        _publish()
        _journal("DEVRUN_END", record.get("summary") or "run ended")
        stop_text = "budget stop: %s" % (exc,)
        yield _run_event("delta", turn, task_id, stop_text,
                         {"run_id": run_id})
        turn += 1
        yield _run_event("budget_stop", turn, task_id, stop_text,
                         {"run_id": run_id})
    except _InstallHeld as exc:
        record["success"] = False
        record["summary"] = ("run held: install permission needed for %s"
                             % (exc.tool_id,))
        _publish()
        if not record.get("stopped"):
            record["run_end"] = _run_end_tests(
                project_id=project, run_id=run_id, task_id=task_id)
        _journal("DEVRUN_END", record.get("summary") or "run ended")
        status = "Needs your permission to install: %s" % (exc.command,)
        yield _run_event("delta", turn, task_id, status,
                         {"run_id": run_id})
        turn += 1
        yield _run_event("delta", turn, task_id,
                         _ledger_total_line(record),
                         {"run_id": run_id})
        turn += 1
        yield _run_event("delta", turn, task_id, record["summary"],
                         {"run_id": run_id,
                          "success": bool(record.get("success"))})
        turn += 1
        yield _run_event("approval", turn, task_id, status,
                         {"run_id": run_id, "tool_id": exc.tool_id,
                          "reason": record["summary"]})
    except GeneratorExit:
        for proc in procs:
            with contextlib.suppress(Exception):
                _actions._kill(proc)
        record["summary"] = (
            "%s (client disconnect: children reaped)"
            % (record.get("summary") or "run ended"))
        _publish()
        raise
    except Exception as exc:
        record["success"] = False
        record["summary"] = "run failed: internal %s: %s" % (
            type(exc).__name__, exc)
        _publish()
        yield _run_event("done", turn, task_id, record["summary"],
                         {"run_id": run_id, "success": False})


def _director_prompt(message: str) -> str:
    """The Director brief: strict plan-or-answer JSON, no prose."""
    return (
        "You are the Director. Project task: %s\n\n"
        "Return ONLY one JSON object, no prose: either "
        "{\"answer\": \"...\"} for a plain question, or "
        "{\"parts\": [{\"part_id\": \"p1\", \"goal\": \"...\", "
        "\"files\": [\"rel/path\"], "
        "\"check_commands\": [[\"python\", \"-m\", \"pytest\", ...]], "
        "\"depends_on\": []}]}. Paths stay inside the project folder, "
        "file sets are disjoint, argv lists are word lists, depends_on "
        "names part ids without cycles." % (message or "(no task text)",))


def _manager_order(record: Any, manager: dict, adapter: Any,
                   parts: list, project: str, run_id: str,
                   call: Any) -> list[str]:
    """Ask the manager for the dispatch order; plan order on garbage."""
    prompt = ("You are the Manager. Plan: %s\n\n"
              "Return ONLY {\"order\": [...]} naming every part id "
              "exactly once, dependencies first." % (
                  json.dumps([{"part_id": part["part_id"],
                               "depends_on": part["depends_on"]}
                              for part in parts]),))
    try:
        response = call("manager", manager, adapter,
                        [{"role": "user", "content": prompt}],
                        None, 0, waits=["order"])
        data = json.loads(response.output_text or "")
        order = data.get("order")
        if (isinstance(order, list) and order
                and all(isinstance(item, str) for item in order)):
            known = [part["part_id"] for part in parts]
            ordered = [item for item in order if item in known]
            ordered.extend(
                [item for item in known if item not in ordered])
            record["manager_order"] = list(ordered)
            return ordered
    except Exception as exc:
        record["manager_note"] = (
            "manager order unusable, plan order kept: %s" % (exc,))
    return [part["part_id"] for part in parts]


def _run_parts(*, record: Any, app: Any, parts: list, order: list,
               director: dict, manager: dict, worker: dict,
               auditor: dict, auditor_adapter: Any, folder: str,
               project: str, task_id: str, run_id: str, turn: int,
               turn_cap: int, state: Any, attached: set, procs: list,
               message: str, contract_hash: str, publish: Any,
               check_stop: Any, stop_seen: Any, live: Any,
               call: Any) -> Any:
    """Dispatch every part; return the next turn number."""
    from agent_si.runtime.devrun import records as _records

    by_id = {part["part_id"]: part for part in parts}
    rows = {part["part_id"]: _records.part_add(
        record, part_id=part["part_id"], goal=part["goal"])
            for part in parts}
    for part in parts:
        rows[part["part_id"]]["auto_why"] = dict(worker.get("why", {}))
    pending = [part["part_id"] for part in parts
               if part["part_id"] in order]
    pending.extend(part["part_id"] for part in parts
                   if part["part_id"] not in pending)

    def _blocked(part_id: str, reason: str) -> None:
        rows[part_id]["verdict"] = "BLOCKED"
        rows[part_id]["reason"] = reason

    def _ready(part_id: str) -> bool:
        return all(rows[dep]["verdict"] == "PASS"
                   for dep in by_id[part_id]["depends_on"])

    def _failed_dep(part_id: str) -> str:
        for dep in by_id[part_id]["depends_on"]:
            if rows[dep]["verdict"] in ("FAIL", "FAILED", "BLOCKED"):
                return dep
        return ""

    settled: set[str] = set()
    while len(settled) < len(pending):
        progressed = False
        for part_id in order:
            if part_id in settled or part_id not in by_id:
                continue
            failed = _failed_dep(part_id)
            if failed:
                _blocked(part_id, "blocked: part %s %s" % (
                    failed, rows[failed]["verdict"]))
                settled.add(part_id)
                publish()
                _journal_event(
                    project, "DEVRUN_PART",
                    "part %s: BLOCKED (%s)" % (
                        part_id, rows[part_id]["reason"]))
                turn += 1
                yield _run_event(
                    "delta", turn, part_id,
                    "Part %s: BLOCKED (%s failed)" % (part_id, failed),
                    {"run_id": run_id, "part_id": part_id})
                progressed = True
                continue
            if not _ready(part_id):
                continue
            turn += 1
            yield _run_event("delta", turn, part_id,
                             "Part %s: attempt 1" % (part_id,),
                             {"run_id": run_id, "part_id": part_id,
                              "attempt": 1})
            _, turn = yield from _run_part(
                record=record, app=app, spec=by_id[part_id],
                row=rows[part_id], auditor_spec=auditor,
                auditor_adapter=auditor_adapter, folder=folder,
                project=project, task_id=task_id, run_id=run_id,
                turn=turn, turn_cap=turn_cap, state=state,
                attached=attached, procs=procs, message=message,
                contract_hash=contract_hash, publish=publish,
                check_stop=check_stop, stop_seen=stop_seen,
                live=live, call=call)
            settled.add(part_id)
            publish()
            _journal_event(
                project, "DEVRUN_PART",
                "part %s: %s (%s)" % (
                    part_id, rows[part_id]["verdict"],
                    rows[part_id].get("reason", "")))
            progressed = True
        if not progressed:
            for part_id in pending:
                if part_id not in settled:
                    _blocked(part_id,
                             "blocked: prerequisites never passed")
                    settled.add(part_id)
                    _journal_event(
                        project, "DEVRUN_PART",
                        "part %s: BLOCKED (%s)" % (
                            part_id, rows[part_id]["reason"]))
            publish()
    for part_id in pending:
        if part_id not in settled:
            _blocked(part_id, "blocked: prerequisites never passed")
            settled.add(part_id)
            _journal_event(
                project, "DEVRUN_PART",
                "part %s: BLOCKED (%s)" % (
                    part_id, rows[part_id]["reason"]))
    publish()
    return turn


def _run_part(*, record: Any, app: Any, spec: dict, row: dict,
              auditor_spec: dict, auditor_adapter: Any, folder: str,
              project: str, task_id: str, run_id: str, turn: int,
              turn_cap: int, state: Any, attached: set, procs: list,
              message: str, contract_hash: str, publish: Any,
              check_stop: Any, stop_seen: Any, live: Any,
              call: Any) -> Any:
    """Run one part through attempts; return (verdict, next turn)."""
    from agent_si.runtime.devrun import audit as _audit
    from agent_si.runtime.devrun import roles as _roles

    part_id = str(spec["part_id"])
    producer_base = "producer-%s-%s" % (run_id, part_id)
    auditor_ref = _roles.new_identity("auditor-%s-%s" % (run_id, part_id))
    before = _audit.snapshot_files(folder, spec["files"])
    failing: list[str] = []
    reasons: list[str] = []
    for attempt in range(1, _EXTRA_ATTEMPTS + 2):
        row["attempts"] = int(attempt)
        check_stop()
        worker_adapter = _roles.build_adapter(app, _resolve_worker(
            app, project))
        producer_ref = "%s-a%d" % (producer_base, attempt)
        turn += 1
        outcome = _agent_loop(
            record=record, app=app, spec=spec, row=row,
            adapter=worker_adapter, folder=folder, project=project,
            run_id=run_id, part_id=part_id, attempt=attempt,
            turn=turn, turn_cap=turn_cap, state=state, procs=procs,
            failing=failing, reasons=reasons, message=message,
            publish=publish, check_stop=check_stop, live=live,
            call=call, attached=attached, stop_seen=stop_seen)
        turn, attempt_ok = outcome
        if not attempt_ok:
            failing.append("agent loop failed")
        checks = _run_checks(
            record=record, spec=spec, row=row, folder=folder,
            project=project, run_id=run_id, part_id=part_id,
            attempt=attempt, turn=turn, state=state, attached=attached,
            procs=procs, publish=publish, check_stop=check_stop,
            stop_seen=stop_seen)
        turn, check_rows, checks_ok = checks
        for check in check_rows:
            command = " ".join(
                str(word) for word in (check.get("argv") or []))
            line = "Check %s $ %s -> exit %s" % (
                part_id, command, check.get("exit_code"))
            log_path = os.path.join(
                str(folder), str(check.get("output_file") or ""))
            if not os.path.exists(log_path):
                line += " (no log file)"
            elif not str(check.get("output_tail") or "").strip():
                line += " (no output)"
            turn += 1
            yield _run_event(
                "delta", turn, part_id, line,
                {"run_id": run_id, "part_id": part_id})
        after = _audit.snapshot_files(folder, spec["files"])
        files_diff = _audit.diff_text(before, after)
        entry = None
        if spec["check_commands"]:
            try:
                entry = _audit.judge(
                    app, _audit.fresh_coordinator(), auditor_adapter,
                    auditor_spec, record=record, project_id=project,
                    run_id=run_id, task_id=task_id, part_id=part_id,
                    attempt=attempt, producer_ref=producer_ref,
                    auditor_ref=auditor_ref, contract_hash=contract_hash,
                    goal=spec["goal"], files_diff=files_diff,
                    checks=check_rows,
                    artifact_refs=["%s/%s" % (part_id, path)
                                   for path in spec["files"]])
            except _roles._BudgetOut as exc:
                raise _BudgetOut(str(exc)) from None
            record.setdefault("audits", []).append({
                "producer_ref": entry["producer_ref"],
                "audit_ref": entry["audit_id"],
                "audit_session": entry["audit_session"],
                "result": entry["result"],
                "reasons": entry["reasons"],
                "part_id": part_id,
                "attempt": attempt,
            })
            first_reason = ((entry or {}).get("reasons", [])
                            or ["auditor gave no reason"])[0]
            turn += 1
            yield _run_event(
                "delta", turn, part_id,
                "Auditor for %s: %s (%s) [%s]"
                % (part_id, entry["result"], first_reason,
                   auditor_ref),
                {"run_id": run_id, "part_id": part_id})
            _journal_event(
                project, "DEVRUN_AUDIT",
                "audit %s attempt %d: %s (%s)"
                % (part_id, attempt, entry["result"],
                   "; ".join((entry or {}).get("reasons", [])
                             or ["auditor gave no reason"])))
            if entry.get("over_cap"):
                raise _BudgetOut(
                    "budget stop: auditor call spent past the cap")
        if not spec["check_commands"]:
            if spec.get("why"):
                row["verdict"] = "PASS"
                row["reason"] = "no check: director recorded why: %s" % (
                    spec["why"],)
                outcome_text = "Part %s: PASS (%s)" % (
                    part_id, row["reason"])
            else:
                row["verdict"] = "FAIL"
                row["reason"] = "no check: part has no check commands"
                outcome_text = "Part %s: FAILED (%s)" % (
                    part_id, row["reason"])
            turn += 1
            yield _run_event(
                "delta", turn, part_id, outcome_text,
                {"run_id": run_id, "part_id": part_id})
            publish()
            return row["verdict"], turn
        auditor_ok = entry is not None and entry["result"] == "PASS"
        if checks_ok and auditor_ok:
            row["verdict"] = "PASS"
            row["reason"] = "checks green, auditor PASS"
            turn += 1
            yield _run_event(
                "delta", turn, part_id,
                "Part %s: PASS (checks green, auditor PASS)" % (part_id,),
                {"run_id": run_id, "part_id": part_id})
            publish()
            return "PASS", turn
        failing = ["$ %s -> exit %s\n%s" % (
            " ".join(check.get("argv", [])), check.get("exit_code"),
            str(check.get("output_tail") or "")[:2000])
                   for check in check_rows]
        reasons = list((entry or {}).get("reasons", [])) or [
            "auditor gave no reason"]
        if attempt < _EXTRA_ATTEMPTS + 1:
            turn += 1
            yield _run_event(
                "delta", turn, part_id,
                "Part %s: checks red, attempt %d" % (
                    part_id, attempt + 1),
                {"run_id": run_id, "part_id": part_id,
                 "attempt": attempt + 1})
            publish()
            continue
        row["verdict"] = "FAIL"
        row["reason"] = "checks red: %s; auditor: %s" % (
            "; ".join(failing) or "no checks", "; ".join(reasons))
        turn += 1
        yield _run_event(
            "delta", turn, part_id,
            "Part %s: FAILED (%s)" % (part_id, row["reason"]),
            {"run_id": run_id, "part_id": part_id})
        publish()
        turn += 1
        yield _run_event(
            "delta", turn, part_id,
            "Needs you: %s: %s" % (part_id, row["reason"]),
            {"run_id": run_id, "part_id": part_id})
        return "FAIL", turn
    row["verdict"] = "FAIL"
    row["reason"] = "attempt budget exhausted"
    return "FAIL", turn


def _resolve_worker(app: Any, project: str) -> dict[str, Any]:
    """Fresh worker resolution per attempt (AUTO re-picks honestly)."""
    from agent_si.runtime.devrun import roles as _roles

    return _roles.resolve_role(app, project, "worker")


def _agent_loop(*, record: Any, app: Any, spec: dict, row: dict,
                adapter: Any, folder: str, project: str, run_id: str,
                part_id: str, attempt: int, turn: int, turn_cap: int,
                state: Any, procs: list, failing: list, reasons: list,
                message: str, publish: Any, check_stop: Any, live: Any,
                call: Any, attached: Any = None,
                stop_seen: Any = None) -> Any:
    """Worker turn loop; return (next turn, attempt usable)."""
    from agent_si.runtime.devrun import protocol as _protocol

    worker_spec = _resolve_worker(app, project)
    history: list[dict[str, str]] = [
        {"role": "user", "content": _worker_prompt(
            spec, message, attempt, failing, reasons)}]
    for _ in range(max(1, int(turn_cap))):
        check_stop()
        response = call("worker", worker_spec, adapter, history,
                        part_id, attempt,
                        waits=["agent:%s" % (part_id,)])
        try:
            parsed = _protocol.parse_agent_reply(
                response.output_text or "")
        except _protocol.AgentError as exc:
            history.append({"role": "assistant",
                            "content": response.output_text or ""})
            history.append({"role": "user", "content": (
                "Your last reply was not valid JSON: %s "
                "Return ONLY {\"actions\": [...], \"done\": bool}, "
                "no prose.") % (exc,)})
            check_stop()
            response = call("worker", worker_spec, adapter, history,
                            part_id, attempt,
                            waits=["agent:%s" % (part_id,)])
            try:
                parsed = _protocol.parse_agent_reply(
                    response.output_text or "")
            except _protocol.AgentError as exc2:
                row["reason"] = "agent output malformed twice: %s" % (
                    exc2,)
                return turn, False
        notes = _apply_actions(
            record=record, row=row, folder=folder, project=project,
            run_id=run_id, part_id=part_id, attempt=attempt,
            actions=parsed["actions"],
            spec=spec, state=state, procs=procs, live=live,
            worker_spec=worker_spec, check_stop=check_stop,
            attached=attached, stop_seen=stop_seen)
        history.append({"role": "assistant",
                        "content": response.output_text or ""})
        history.append({"role": "user", "content": notes})
        if parsed["done"]:
            return turn, True
    row["reason"] = "turn budget reached after %d turns" % (
        max(1, int(turn_cap)))
    return turn, False


def _worker_prompt(spec: dict, message: str, attempt: int,
                   failing: list, reasons: list) -> str:
    """Worker brief for one attempt: its part only, never other parts."""
    head = ("You are the worker for part %s (attempt %d). Goal: %s. "
            "Project task: %s. Files you may write: %s. "
            "Actions: read_file {path}, list_dir {path}, "
            "write_file {path, content}, run {argv}. Writes outside "
            "your files are refused. Inspect first, then create "
            "deliverables with write_file. Relative paths only. "
            "Return ONLY {\"actions\": [...], \"done\": bool}: done "
            "true only when the part is complete." % (
                spec["part_id"], attempt, spec["goal"],
                message or "(no task text)",
                ", ".join(spec["files"]),))
    if attempt > 1:
        head += (" This is a fresh attempt: previous checks failed: %s. "
                 "Auditor reasons: %s. Fix the part." % (
                     " | ".join(failing) or "no output",
                     " | ".join(reasons) or "no reason"))
    return head


def _apply_actions(*, record: Any, row: Any, folder: str, project: str,
                   run_id: str, part_id: str, attempt: int,
                   actions: list, spec: dict, state: Any, procs: list,
                   live: Any, worker_spec: dict, check_stop: Any,
                   attached: Any = None, stop_seen: Any = None) -> str:
    """Apply one worker turn; every refusal returns as text."""
    from agent_si.runtime.devrun import actions as _actions

    notes: list[str] = []
    refusals: list[str] = []
    for action in actions:
        check_stop()
        name = action.get("action")
        try:
            if name == "read_file":
                out = _actions.read_file(
                    folder, str(action.get("path", "")))
                notes.append("read_file %s: %s" % (
                    action.get("path"), out[:2000]))
            elif name == "list_dir":
                out = _actions.list_dir(
                    folder, str(action.get("path", ".") or "."))
                notes.append("list_dir %s: %s" % (
                    action.get("path", "."), out[:2000]))
            elif name == "write_file":
                entry = _actions.write_file(
                    folder, str(action.get("path", "")),
                    str(action.get("content", "")),
                    allowed=spec["files"], run_id=run_id,
                    part_id=part_id, attempt=attempt)
                record.setdefault("artifacts", []).append(entry)
                live("worker", str(worker_spec.get("model", "")),
                     part_id, attempt, "write_file",
                     str(entry["path"]), {}, "UNKNOWN",
                     ["agent:%s" % (part_id,)])
                notes.append("write_file %s: ok sha256 %s" % (
                    entry["path"], entry["sha256"][:16]))
            elif name == "run":
                argv = action.get("argv", [])
                if not isinstance(argv, list) or not argv or any(
                        not isinstance(word, str) for word in argv):
                    notes.append("run: refused: argv must be a word list")
                    continue
                notes.append(_run_agent_command(
                    record=record, folder=folder, project=project,
                    run_id="%s-%s-a%d-agent" % (
                        run_id, part_id, attempt),
                    argv=[str(word) for word in argv], state=state,
                    procs=procs, attached=attached,
                    stop_seen=stop_seen))
            else:
                notes.append("%s: refused: unknown action" % (name,))
        except _actions.ActionRefused as exc:
            notes.append("%s: %s" % (name, exc))
            refusals.append("%s: %s" % (name, exc))
        except PermissionError as exc:
            notes.append("%s: %s" % (name, exc))
            refusals.append("%s: %s" % (name, exc))
        except ValueError as exc:
            notes.append("%s: %s" % (name, exc))
            refusals.append("%s: %s" % (name, exc))
    if refusals:
        row.setdefault("refusals", []).extend(refusals)
    return "\n".join(notes) if notes else "(no actions)"


def _run_agent_command(*, record: Any, folder: str, project: str,
                       run_id: str, argv: list, state: Any,
                       procs: list, attached: Any = None,
                       stop_seen: Any = None) -> str:
    """Run one worker command; refusals and failures return as text.

    An install-class command with no recorded decision raises
    _InstallHeld (the run ends as held, never as run text).
    """
    from agent_si.runtime.devrun import actions as _actions

    log_dir = os.path.join(str(folder), ".devrun", "agent")
    with contextlib.suppress(OSError):
        os.makedirs(log_dir, exist_ok=True)
    stamp = uuid.uuid4().hex[:8]
    log_rel = os.path.join(".devrun", "agent",
                           "%s.log" % (stamp,)).replace("\\", "/")
    log_path = os.path.join(str(folder), ".devrun", "agent",
                            "%s.log" % (stamp,))
    try:
        spawn = _actions.spawn_checked(
            project, run_id, folder, argv, log_path, log_rel)
    except _actions.InstallAskNeeded as exc:
        raise _InstallHeld(exc.tool_id, " ".join(argv)) from None
    except (PermissionError, ValueError) as exc:
        return "run %s: %s" % (" ".join(argv), exc)
    proc = spawn.get("proc")
    procs.append(proc)
    if attached is not None:
        with contextlib.suppress(Exception):
            attached.add(run_id)

    def _watcher() -> bool:
        try:
            return bool(stop_seen()) if stop_seen is not None else False
        except Exception:
            return False

    kind = str(spawn.get("class") or "read-only")
    outcome = _actions.wait_proc(
        proc, _actions.class_timeout(kind), stream_state=state,
        stop_watcher=_watcher)
    if outcome == "exited" and _watcher():
        outcome = "stopped"
    if outcome == "stopped":
        _actions.ensure_dead(proc)
    try:
        exit_code = proc.poll()
    except Exception:
        exit_code = None
    tail = _actions.finalize_log(log_path)
    if outcome == "stopped":
        raise _Stopped()
    if outcome == "timeout":
        return "run %s: timeout after %ss (exit unknown)\n%s" % (
            " ".join(argv), _actions.class_timeout(kind), tail)
    return "run %s: exit %s\n%s" % (" ".join(argv), exit_code, tail)


def _run_checks(*, record: Any, spec: dict, row: dict, folder: str,
                project: str, run_id: str, part_id: str, attempt: int,
                turn: int, state: Any, attached: set, procs: list,
                publish: Any, check_stop: Any,
                stop_seen: Any) -> Any:
    """Run the part's check commands; return (turn, rows, all green)."""
    from agent_si.runtime.devrun import actions as _actions

    rows: list[dict[str, Any]] = []
    for index, command in enumerate(spec["check_commands"]):
        check_stop()
        check_id = "%s-%s-a%d-c%d" % (run_id, part_id, attempt, index)
        log_rel = os.path.join(
            ".devrun", "outputs",
            "%s-a%d-%d.log" % (part_id, attempt, index)).replace(
                "\\", "/")
        log_path = os.path.join(
            str(folder), ".devrun", "outputs",
            "%s-a%d-%d.log" % (part_id, attempt, index))
        if (not isinstance(command, list) or not command
                or any(not isinstance(word, str) or not word
                       for word in command)):
            rows.append({"argv": [], "exit_code": None,
                         "output_file": log_rel,
                         "output_tail": "check command must be an argv "
                                        "word list",
                         "pid": 0})
            continue
        try:
            spawn = _actions.spawn_checked(
                project, check_id, folder, [str(word) for word in command],
                log_path, log_rel)
        except (PermissionError, ValueError) as exc:
            rows.append({"argv": [str(word) for word in command],
                         "exit_code": None, "output_file": log_rel,
                         "output_tail": "refused: %s" % (exc,),
                         "pid": 0})
            continue
        proc = spawn.get("proc")
        pid = int(spawn.get("pid") or 0)
        procs.append(proc)
        attached.add(check_id)

        def _watcher() -> bool:
            return bool(stop_seen())

        record.setdefault("checks_started", []).append({
            "pid": pid, "argv": list(spawn.get("argv") or command),
            "check_run_id": check_id, "part_id": part_id,
            "attempt": attempt})
        publish()
        kind = str(spawn.get("class") or "read-only")
        outcome = _actions.wait_proc(
            proc, _actions.class_timeout(kind), stream_state=state,
            stop_watcher=_watcher)
        if outcome == "exited" and stop_seen():
            # The child died in the same instant as the stop: the
            # stop still wins, so the run ends "stopped".
            outcome = "stopped"
        if outcome == "stopped":
            _actions.ensure_dead(proc)
        try:
            exit_code = proc.poll()
        except Exception:
            exit_code = None
        tail = _actions.finalize_log(log_path)
        rows.append({"argv": list(spawn.get("argv") or command),
                     "exit_code": exit_code if outcome == "exited"
                     else None,
                     "output_file": log_rel,
                     "output_tail": tail
                     if outcome == "exited" else "%s\n%s" % (
                         outcome, tail),
                     "pid": pid})
        if outcome == "stopped":
            raise _Stopped()
        if outcome == "timeout":
            rows[-1]["output_tail"] = "timeout after %ss\n%s" % (
                _actions.class_timeout(kind), tail)
    row.setdefault("checks", []).extend(rows)
    green = bool(rows) and all(
        check.get("exit_code") == 0 for check in rows)
    return turn, rows, green
