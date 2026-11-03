"""FXNOWIN: no console window from any product child process.

The exe has no console, so every console child spawned without
CREATE_NO_WINDOW opens its own window and takes focus. Every
subprocess.Popen/run/call/check_output/check_call and asyncio
create_subprocess_* under src/agent_si must pass ``creationflags``
referencing ``agent_si.backend.proc_tree.quiet_flags`` (which is
CREATE_NO_WINDOW on Windows, 0 elsewhere), except:

- the Popen inside ``proc_tree.spawn`` itself (the enforcement point:
  spawn ORs quiet_flags into creationflags on Windows);
- calls inside provably non-Windows branches (the else leg of an
  ``os.name == "nt"`` / ``sys.platform == "win32"`` check, or the body
  of a darwin/posix-only check);
- ALLOWLIST: short named non-Windows fallthroughs below.

A new bare call FAILS this test. os.startfile is user-asked and out
of scope (sidecar opens folders on user request).
"""
import ast
import os
import sys

import pytest

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WS not in sys.path:
    sys.path.insert(0, _WS)
_SRC = os.path.join(_WS, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

_SRC_AGENT_SI = os.path.join(_SRC, "agent_si")

#: (relpath, enclosing func, first argv literal): non-Windows
#: fallthroughs that cannot take a flag (darwin `open` is covered by
#: the structural darwin-branch rule instead).
ALLOWLIST = {
    ("src/agent_si/sidecar.py", "_open_native_folder", "xdg-open"),
}

_SPAWN_ATTRS = ("Popen", "run", "call", "check_output", "check_call")
_ASYNC_SPAWN_ATTRS = ("create_subprocess_shell", "create_subprocess_exec")


def _mentions_platform(test) -> bool:
    dump = ast.dump(test)
    return "id='os'" in dump or "id='sys'" in dump


def _is_windows_body(test) -> bool:
    dump = ast.dump(test)
    return (
        _mentions_platform(test)
        and "Eq()" in dump
        and ("'nt'" in dump or "'win32'" in dump)
    )


def _is_nonwin_body(test) -> bool:
    dump = ast.dump(test)
    if not _mentions_platform(test):
        return False
    if "NotEq()" in dump and ("'nt'" in dump or "'win32'" in dump):
        return True
    if "Eq()" in dump and (
        "'posix'" in dump or "'darwin'" in dump or "'linux'" in dump
    ):
        return True
    if "startswith" in dump and "'linux'" in dump:
        return True
    return False


def _iter_calls(tree):
    """Yield (node, exempt_by_branch) for every spawn call."""
    stack = []

    def visit(node, exempt):
        if isinstance(node, ast.If):
            if _is_windows_body(node.test):
                for child in node.body:
                    yield from visit(child, exempt)
                for child in node.orelse:
                    yield from visit(child, True)
                return
            if _is_nonwin_body(node.test):
                for child in node.body:
                    yield from visit(child, True)
                for child in node.orelse:
                    yield from visit(child, exempt)
                return
        if isinstance(node, ast.Call) and _is_spawn_call(node):
            yield node, exempt
        for child in ast.iter_child_nodes(node):
            yield from visit(child, exempt)

    yield from visit(tree, False)


def _is_spawn_call(node) -> bool:
    fn = node.func
    if isinstance(fn, ast.Attribute):
        if isinstance(fn.value, ast.Name) and fn.value.id in (
            "subprocess",
            "_sp",
            "_subprocess",
        ):
            return fn.attr in _SPAWN_ATTRS
        if isinstance(fn.value, ast.Name) and fn.value.id == "asyncio":
            return fn.attr in _ASYNC_SPAWN_ATTRS
    if isinstance(fn, ast.Name) and fn.id in _ASYNC_SPAWN_ATTRS:
        return True
    return False


def _first_argv_literal(node):
    if not node.args:
        return None
    first = node.args[0]
    if isinstance(first, (ast.List, ast.Tuple)) and first.elts:
        head = first.elts[0]
        if isinstance(head, ast.Constant):
            return head.value
    return None


def _enclosing_func(tree, lineno):
    best = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.lineno <= lineno and (
                best is None or node.lineno > best.lineno
            ):
                best = node
    return best.name if best is not None else ""


def _scan():
    violations = []
    helper_defs = []
    for root, _dirs, files in os.walk(_SRC_AGENT_SI):
        for name in sorted(files):
            if not name.endswith(".py"):
                continue
            path = os.path.join(root, name)
            rel = os.path.relpath(path, _WS).replace(os.sep, "/")
            with open(path, encoding="utf-8") as handle:
                try:
                    tree = ast.parse(handle.read(), filename=path)
                except SyntaxError as exc:
                    violations.append("%s: unparsable: %s" % (rel, exc))
                    continue
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef,
                                     ast.AsyncFunctionDef)):
                    if node.name == "quiet_flags":
                        helper_defs.append(rel)
            for node, exempt in _iter_calls(tree):
                if exempt:
                    continue
                rel_here = rel
                if rel_here == "src/agent_si/backend/proc_tree.py":
                    func = _enclosing_func(tree, node.lineno)
                    if func == "spawn":
                        continue  # enforcement point (see test below)
                kws = [k for k in node.keywords if k.arg == "creationflags"]
                if kws and any(
                    "quiet_flags" in ast.dump(k.value) for k in kws
                ):
                    continue
                if (rel_here, _enclosing_func(tree, node.lineno),
                        _first_argv_literal(node)) in ALLOWLIST:
                    continue
                fn = node.func
                callee = getattr(fn, "attr", getattr(fn, "id", "?"))
                violations.append(
                    "%s:%d bare %s (no creationflags from quiet_flags)"
                    % (rel_here, node.lineno, callee)
                )
    return violations, helper_defs


def test_quiet_flags_helper_shape():
    from agent_si.backend import proc_tree as _proc_tree

    assert callable(_proc_tree.quiet_flags)
    value = _proc_tree.quiet_flags()
    assert isinstance(value, int), type(value)
    if os.name == "nt":
        import subprocess as _subprocess

        assert value == int(
            getattr(_subprocess, "CREATE_NO_WINDOW", 0))
        assert value != 0


def test_spawn_enforces_quiet_flags():
    path = os.path.join(_SRC_AGENT_SI, "backend", "proc_tree.py")
    with open(path, encoding="utf-8") as handle:
        tree = ast.parse(handle.read(), filename=path)
    spawn = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "spawn"
    )
    assert "quiet_flags" in ast.dump(spawn), (
        "proc_tree.spawn must OR quiet_flags into creationflags")


def test_no_bare_console_children():
    violations, helper_defs = _scan()
    assert not violations, (
        "bare console children without quiet_flags:\n"
        + "\n".join(violations))
    assert helper_defs == sorted(helper_defs)
    assert set(helper_defs) <= {
        "src/agent_si/backend/proc_tree.py",
        "src/agent_si/qa_catalog/runners/host.py",
        "src/agent_si/qa_catalog/runners/suite_invoke.py",
    }, helper_defs
    assert "src/agent_si/backend/proc_tree.py" in helper_defs


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
