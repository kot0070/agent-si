"""K03 FXCATALOG lane: versioned QA catalog v2 (loader, validator, derive, resolve, run).

Own-words catalog of 300 tests over 50 group prefixes. The loader
validates every load: row count, id shape plus per-group restart,
uniqueness, required fields, split targets, broken input refused,
unknown ids refused. Selection derives plans from a detected project
profile; execution runs CODE tests through the jailed host runner.
Stdlib only. No reference-pack reads at runtime.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time

from agent_si.backend.proc_tree import quiet_flags

CATALOG_VERSION = 2

CODE_KINDS = ("CODE-STATIC", "CODE-RUNTIME", "CODE-UI")
JUDGE_KINDS = ("AI", "HUMAN")
ALL_KINDS = CODE_KINDS + JUDGE_KINDS

PRIORITIES = ("P0", "P1", "P2")
PLAN_PROFILES = ("QUICK_SMOKE", "PR_CHANGE", "FULL_RELEASE")
PLAN_STATUSES = ("PLANNED", "NOT_SELECTED", "SKIP_NA")

ERROR_CODES = (
    "BROKEN_CATALOG",
    "UNKNOWN_TEST_ID",
    "UNKNOWN_PROFILE",
    "SPLIT_UNMET",
)

#: Set-A runners (served now) plus set-B ids (recognized, wired later).
SET_A_RUNNERS = (
    "suite_invoke", "static_lint", "secret_scan", "dep_audit",
    "build_check", "install_check", "policy_gate", "observability_lint",
    "i18n_parity", "a11y_scan", "contract_test", "db_check",
    "file_roundtrip", "perf_bench", "api_smoke", "net_probe", "link_check",
)
SET_B_RUNNERS = (
    "seo_probe", "auth_probe", "load_smoke", "cloud_probe",
    "vuln_probe_safe", "ui_automation", "visual_diff", "media_mock",
    "eval_harness", "notify_harness", "ledger_reconcile", "pay_sandbox",
    "offline_harness", "geo_mock", "game_harness", "chaos_safe",
    "rtc_harness",
)
KNOWN_RUNNERS = SET_A_RUNNERS + SET_B_RUNNERS

_REQUIRED_FIELDS = (
    "id", "group", "intent", "kind", "applicability", "priority",
    "oracle", "evidence", "runner", "why_not_code", "permissions_needed",
)

_MIN_TESTS = 300
_CODE_MIN_PCT = 80.0
_AI_LO_PCT = 4.0
_AI_HI_PCT = 6.0
_HUMAN_MAX_PCT = 10.0

_RESULT_KEYS = (
    "test_id", "runner_id", "status", "reason", "assertions",
    "evidence", "child_pid", "child_env_keys", "proxies_emptied",
)


class CatalogError(Exception):
    """Catalog failure carrying the frozen ``.code`` name."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _frozen_root() -> str | None:
    """Frozen bundle dir (sys._MEIPASS), or None outside a freeze."""
    meipass = getattr(sys, "_MEIPASS", None)
    if getattr(sys, "frozen", False) and meipass:
        return str(meipass)
    return None


def _catalog_path() -> str:
    root = _frozen_root()
    if root is not None:
        return os.path.join(root, "qa_catalog", "catalog_v2.json")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "catalog_v2.json")


def _runners_dir() -> str:
    root = _frozen_root()
    if root is not None:
        return os.path.join(root, "qa_catalog", "runners")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "runners")


def _host_path() -> str:
    return os.path.join(_runners_dir(), "host.py")


def validate_catalog(doc) -> dict:
    """Validate a decoded catalog document; return per-kind counts.

    Raises CatalogError with code BROKEN_CATALOG or SPLIT_UNMET when the
    document is not loadable as-is.
    """
    if not isinstance(doc, dict):
        raise CatalogError("BROKEN_CATALOG", "catalog document must be an object")
    tests = doc.get("tests")
    if not isinstance(tests, list) or len(tests) < _MIN_TESTS:
        raise CatalogError(
            "BROKEN_CATALOG",
            "catalog needs at least %d tests, saw %s" % (_MIN_TESTS, len(tests) if isinstance(tests, list) else type(tests).__name__),
        )
    seen = set()
    per_group: dict = {}
    counts: dict = {}
    for pos, row in enumerate(tests):
        if not isinstance(row, dict):
            raise CatalogError("BROKEN_CATALOG", "row %d must be an object" % pos)
        for field in _REQUIRED_FIELDS:
            if field not in row:
                raise CatalogError("BROKEN_CATALOG", "row %d missing field %s" % (pos, field))
        test_id = row["id"]
        group = row["group"]
        if not isinstance(test_id, str) or not isinstance(group, str):
            raise CatalogError("BROKEN_CATALOG", "row %d id/group must be strings" % pos)
        if test_id in seen:
            raise CatalogError("BROKEN_CATALOG", "duplicate test id %r" % test_id)
        seen.add(test_id)
        per_group.setdefault(group, []).append(test_id)
        kind = row["kind"]
        if kind not in ALL_KINDS:
            raise CatalogError("BROKEN_CATALOG", "row %s carries unknown kind %r" % (test_id, kind))
        counts[kind] = counts.get(kind, 0) + 1
        if row["priority"] not in PRIORITIES:
            raise CatalogError("BROKEN_CATALOG", "row %s carries unknown priority %r" % (test_id, row["priority"]))
        app = row["applicability"]
        if not isinstance(app, dict) or not isinstance(app.get("platforms"), list) or not isinstance(app.get("features"), list):
            raise CatalogError("BROKEN_CATALOG", "row %s applicability must hold platforms plus features lists" % test_id)
        oracle = row["oracle"]
        if not isinstance(oracle, dict) or not oracle.get("compared") or not oracle.get("measurable"):
            raise CatalogError("BROKEN_CATALOG", "row %s oracle must hold compared plus measurable" % test_id)
        if not row.get("intent") or not row.get("evidence"):
            raise CatalogError("BROKEN_CATALOG", "row %s needs a non-empty intent plus evidence" % test_id)
        runner = row["runner"]
        if kind in CODE_KINDS:
            if runner not in KNOWN_RUNNERS:
                raise CatalogError("BROKEN_CATALOG", "row %s names unknown runner %r" % (test_id, runner))
            if row.get("why_not_code"):
                raise CatalogError("BROKEN_CATALOG", "row %s is CODE yet carries why_not_code" % test_id)
        else:
            if runner is not None:
                raise CatalogError("BROKEN_CATALOG", "row %s is %s yet names a runner" % (test_id, kind))
            if not row.get("why_not_code"):
                raise CatalogError("BROKEN_CATALOG", "row %s is %s yet lacks why_not_code" % (test_id, kind))
    for group in sorted(per_group):
        ids = per_group[group]
        want = ["%s-%03d" % (group, n) for n in range(1, len(ids) + 1)]
        if ids != want:
            raise CatalogError(
                "BROKEN_CATALOG",
                "group %s ids must restart at 001 and run compact, saw %r" % (group, ids[:3]),
            )
        for test_id in ids:
            stem, _, num = test_id.rpartition("-")
            if stem != group or not num.isdigit():
                raise CatalogError("BROKEN_CATALOG", "id %r does not match PREFIX-NNN" % test_id)
    total = len(tests)
    if sum(counts.values()) != total:
        raise CatalogError("BROKEN_CATALOG", "per-kind counts do not sum to the total")
    code_total = sum(counts.get(k, 0) for k in CODE_KINDS)
    ai_total = counts.get("AI", 0)
    human_total = counts.get("HUMAN", 0)
    code_pct = 100.0 * code_total / total
    ai_pct = 100.0 * ai_total / total
    human_pct = 100.0 * human_total / total
    if code_pct < _CODE_MIN_PCT:
        raise CatalogError("SPLIT_UNMET", "CODE share %.2f is below %.1f" % (code_pct, _CODE_MIN_PCT))
    if not (_AI_LO_PCT <= ai_pct <= _AI_HI_PCT):
        raise CatalogError("SPLIT_UNMET", "AI share %.2f is outside %.1f-%.1f" % (ai_pct, _AI_LO_PCT, _AI_HI_PCT))
    if human_pct > _HUMAN_MAX_PCT:
        raise CatalogError("SPLIT_UNMET", "HUMAN share %.2f is above %.1f" % (human_pct, _HUMAN_MAX_PCT))
    return dict(counts)


def _load() -> tuple:
    path = _catalog_path()
    try:
        with open(path, "r", encoding="utf-8") as handle:
            doc = json.load(handle)
    except (OSError, ValueError) as exc:
        raise CatalogError("BROKEN_CATALOG", "catalog unreadable: %s" % exc)
    counts = validate_catalog(doc)
    by_id = {row["id"]: row for row in doc["tests"]}
    return doc, by_id, counts


_DOC, _BY_ID, _COUNTS = _load()


def kind_counts() -> dict:
    """Per-kind counts; they sum to the catalog total."""
    total = len(_DOC["tests"])
    if sum(_COUNTS.values()) != total:
        raise CatalogError("BROKEN_CATALOG", "per-kind counts do not sum to the total")
    return dict(_COUNTS)


def catalog_total() -> int:
    """Number of tests in the loaded catalog."""
    return len(_DOC["tests"])


def get_test(test_id: str) -> dict:
    """Return one catalog row; unknown ids are refused."""
    try:
        return _BY_ID[test_id]
    except KeyError:
        raise CatalogError("UNKNOWN_TEST_ID", "test id %r is not in catalog_v2" % (test_id,))


def split_summary() -> dict:
    """Percentage share per kind family for reports."""
    total = len(_DOC["tests"])
    code = sum(_COUNTS.get(k, 0) for k in CODE_KINDS)
    return {
        "total": total,
        "code": code,
        "ai": _COUNTS.get("AI", 0),
        "human": _COUNTS.get("HUMAN", 0),
        "code_pct": 100.0 * code / total,
        "ai_pct": 100.0 * _COUNTS.get("AI", 0) / total,
        "human_pct": 100.0 * _COUNTS.get("HUMAN", 0) / total,
    }


_SKIP_DIRS = (".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build")
_LOCALE_DIRS = ("locales", "locale", "lang", "i18n")
_LOOPBACK_FILE = "qa_loopback.json"


def _is_loopback_url(url: str) -> bool:
    lowered = (url or "").strip().lower()
    if lowered.startswith(("http://", "https://")):
        host = lowered.split("://", 1)[1].split("/", 1)[0].split("@")[-1]
        host = host.rsplit(":", 1)[0].strip("[]")
    else:
        host = lowered
    return host == "localhost" or host == "::1" or host.startswith("127.")


def detect_project_profile(folder: str) -> dict:
    """Detect language, tooling signals, platforms and features of a folder.

    Signals: python and node sources, pytest config, html pages, sql
    migrations, locale trees, compose descriptors, manifests, shell
    recipes and an optional loopback service marker file.
    """
    root = os.path.abspath(folder or ".")
    found = {
        "python": False, "node": False, "pytest": False, "html": False,
        "sql": False, "locales": False, "compose": False,
        "manifest": False, "shell": False, "text": False,
        "loopback": False,
    }
    marker_url = ""
    if os.path.isdir(root):
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [item for item in dirnames if item not in _SKIP_DIRS]
            for name in filenames:
                lower = name.lower()
                full = os.path.join(dirpath, name)
                rel = os.path.relpath(full, root)
                if len(rel) > 512:
                    continue
                if lower.endswith(".py"):
                    found["python"] = True
                    found["text"] = True
                elif lower in ("package.json",):
                    found["node"] = True
                    found["manifest"] = True
                    found["text"] = True
                elif lower in ("pyproject.toml", "setup.py", "setup.cfg", "requirements.txt", "requirements-dev.txt", "tox.ini"):
                    found["manifest"] = True
                    found["text"] = True
                    if lower in ("pytest.ini", "tox.ini"):
                        found["pytest"] = True
                elif lower == "pytest.ini":
                    found["pytest"] = True
                    found["text"] = True
                elif lower.endswith(".html") or lower.endswith(".htm"):
                    found["html"] = True
                    found["text"] = True
                elif lower.endswith(".sql"):
                    found["sql"] = True
                    found["text"] = True
                elif lower.endswith(".json") and lower != "package.json":
                    found["text"] = True
                    parts = os.path.relpath(dirpath, root).split(os.sep)
                    if parts[0].lower() in _LOCALE_DIRS:
                        found["locales"] = True
                elif lower.endswith((".yaml", ".yml")):
                    found["text"] = True
                    if lower in ("docker-compose.yaml", "docker-compose.yml", "compose.yaml", "compose.yml"):
                        found["compose"] = True
                elif lower in ("dockerfile", "makefile"):
                    found["text"] = True
                    found["shell"] = True
                elif lower == "dockerfile":
                    found["text"] = True
                elif lower.endswith((".sh", ".ps1", ".cmd", ".bat")):
                    found["shell"] = True
                    found["text"] = True
                elif lower.endswith((".js", ".ts", ".md", ".txt", ".xml", ".toml", ".cfg", ".ini")):
                    found["text"] = True
                if lower.endswith(".json") and os.path.basename(dirpath).lower() in _LOCALE_DIRS:
                    found["locales"] = True
                if name == _LOOPBACK_FILE:
                    try:
                        with open(full, "r", encoding="utf-8") as handle:
                            marker = json.load(handle)
                        candidate = marker.get("base_url", "") if isinstance(marker, dict) else ""
                        if _is_loopback_url(candidate):
                            found["loopback"] = True
                            marker_url = candidate
                    except (OSError, ValueError):
                        pass
            if os.path.basename(dirpath).lower() in _LOCALE_DIRS:
                try:
                    if any(item.lower().endswith(".json") for item in filenames):
                        found["locales"] = True
                except OSError:
                    pass
    if found["node"] or found["python"]:
        if found["python"] and found["node"]:
            language = "mixed"
        elif found["python"]:
            language = "python"
        else:
            language = "node"
    else:
        language = "unknown"
    if not found["pytest"] and found["python"] and os.path.isdir(root):
        for probe in ("pytest.ini", "setup.cfg", "tox.ini"):
            if os.path.isfile(os.path.join(root, probe)):
                found["pytest"] = True
                break
        else:
            tests_dir = os.path.join(root, "tests")
            try:
                if os.path.isdir(tests_dir) and any(
                    item.startswith("test_") and item.endswith(".py")
                    for item in os.listdir(tests_dir)
                ):
                    found["pytest"] = True
            except OSError:
                pass
    platforms = ["ALL"]
    if found["html"]:
        platforms += ["WEB", "PWA"]
    if found["sql"] or found["manifest"]:
        platforms += ["BACKEND"]
    if found["manifest"]:
        platforms += ["DESKTOP"]
    features = sorted(key for key, hit in found.items() if hit and key != "loopback")
    if found["loopback"]:
        features.append("loopback")
    features = sorted(features)
    return {
        "root": root,
        "language": language,
        "platforms": platforms,
        "features": features,
        "signals": dict(found),
        "loopback_url": marker_url,
    }


def _impact_groups(change_impact) -> list:
    if not isinstance(change_impact, dict):
        return []
    groups = change_impact.get("groups", [])
    if not isinstance(groups, list):
        return []
    return [item for item in groups if isinstance(item, str) and item]


def derive_plan(project_profile: dict, change_impact=None, profile_name: str = "FULL_RELEASE") -> dict:
    """Derive a plan: every catalog test with PLANNED, NOT_SELECTED or SKIP_NA.

    QUICK_SMOKE keeps release blockers that run without live services;
    PR_CHANGE keeps P0 plus P1 inside the change impact; FULL_RELEASE
    keeps every applicable test. Platform or signal mismatches take
    SKIP_NA with a reason; scope exclusions take NOT_SELECTED.
    """
    if profile_name not in PLAN_PROFILES:
        raise CatalogError("UNKNOWN_PROFILE", "unknown plan profile %r" % (profile_name,))
    if not isinstance(project_profile, dict):
        raise CatalogError("BROKEN_CATALOG", "project_profile must be an object")
    platforms = set(project_profile.get("platforms", ["ALL"]))
    features = set(project_profile.get("features", []))
    impact = _impact_groups(change_impact)
    rows = []
    for row in _DOC["tests"]:
        test_id = row["id"]
        plats = row["applicability"]["platforms"]
        feats = row["applicability"]["features"]
        if "ALL" not in plats and not (set(plats) & platforms):
            rows.append({"id": test_id, "status": "SKIP_NA", "reason": "no_matching_platform"})
            continue
        missing = [feat for feat in feats if feat not in features]
        if missing:
            rows.append({"id": test_id, "status": "SKIP_NA", "reason": "missing_project_signal:%s" % missing[0]})
            continue
        if impact and row["group"] not in impact and profile_name in ("QUICK_SMOKE", "PR_CHANGE"):
            rows.append({"id": test_id, "status": "NOT_SELECTED", "reason": "outside_change_impact"})
            continue
        needs_live = row.get("runner") in ("api_smoke", "net_probe", "link_check")
        if profile_name == "QUICK_SMOKE":
            if needs_live:
                rows.append({"id": test_id, "status": "NOT_SELECTED", "reason": "needs_loopback_service_outside_smoke"})
            elif row["kind"] in JUDGE_KINDS:
                rows.append({"id": test_id, "status": "NOT_SELECTED", "reason": "needs_judge_or_operator_outside_smoke"})
            elif row["priority"] == "P0":
                rows.append({"id": test_id, "status": "PLANNED", "reason": "smoke_priority"})
            else:
                rows.append({"id": test_id, "status": "NOT_SELECTED", "reason": "outside_quick_smoke_scope"})
        elif profile_name == "PR_CHANGE":
            if row["priority"] == "P2":
                rows.append({"id": test_id, "status": "NOT_SELECTED", "reason": "p2_outside_change_scope"})
            elif needs_live and "loopback" not in features:
                rows.append({"id": test_id, "status": "NOT_SELECTED", "reason": "needs_loopback_service"})
            else:
                rows.append({"id": test_id, "status": "PLANNED", "reason": "change_priority"})
        else:
            if needs_live and "loopback" not in features:
                rows.append({"id": test_id, "status": "NOT_SELECTED", "reason": "needs_loopback_service"})
            else:
                rows.append({"id": test_id, "status": "PLANNED", "reason": "release_applicable"})
    planned = sum(1 for item in rows if item["status"] == "PLANNED")
    return {"profile": profile_name, "plan": rows, "planned": planned, "total": len(rows)}


#: Runner -> project signal it needs (resolve returns UNSUPPORTED without it).
_RUNNER_NEEDS_SIGNAL = {
    "static_lint": "text",
    "secret_scan": "text",
    "dep_audit": "manifest",
    "build_check": "manifest",
    "install_check": "manifest",
    "policy_gate": "shell",
    "observability_lint": "python",
    "i18n_parity": "locales",
    "a11y_scan": "html",
    "db_check": "sql",
    "suite_invoke": None,
    "contract_test": None,
    "file_roundtrip": None,
    "perf_bench": None,
    "api_smoke": "loopback",
    "net_probe": "loopback",
    "link_check": "loopback",
    "seo_probe": "loopback",
    "auth_probe": "loopback",
    "load_smoke": "loopback",
    "cloud_probe": "loopback",
    "vuln_probe_safe": "loopback",
    "rtc_harness": "loopback",
    "ui_automation": "html",
    "visual_diff": "html",
    "media_mock": "text",
    "eval_harness": "text",
    "notify_harness": None,
    "offline_harness": None,
    "ledger_reconcile": None,
    "pay_sandbox": None,
    "geo_mock": None,
    "game_harness": None,
    "chaos_safe": None,
}

_MISSING_LABEL = {
    "text": "checkable_sources",
    "manifest": "manifests",
    "shell": "shell_files",
    "python": "python_files",
    "locales": "locales_dir",
    "html": "html_files",
    "sql": "migrations_dir",
    "loopback": "loopback_service",
}


def _as_row(test) -> dict:
    if isinstance(test, dict) and "id" in test:
        return test
    return get_test(test)


def resolve(test, project_profile: dict) -> dict:
    """Map a catalog test to a runner plus input, or UNSUPPORTED.

    Returns SUPPORTED with runner and params when the project gives the
    runner its required input, else UNSUPPORTED naming what is missing.
    """
    row = _as_row(test)
    test_id = row["id"]
    kind = row.get("kind", "")
    if kind in JUDGE_KINDS:
        if kind == "AI":
            return {"test_id": test_id, "status": "UNSUPPORTED", "reason": "needs_judge_gateway", "missing": ["judge_gateway"]}
        return {"test_id": test_id, "status": "UNSUPPORTED", "reason": "needs_operator_signoff", "missing": ["operator_signoff"]}
    runner = row.get("runner")
    if runner not in KNOWN_RUNNERS:
        return {"test_id": test_id, "status": "UNSUPPORTED", "reason": "runner_not_served_phase1", "missing": [runner or "runner"]}
    if not isinstance(project_profile, dict):
        return {"test_id": test_id, "status": "UNSUPPORTED", "reason": "bad_project_profile", "missing": ["project_profile"]}
    signals = project_profile.get("signals", {})
    features = set(project_profile.get("features", []))
    need = _RUNNER_NEEDS_SIGNAL.get(runner)
    if need is not None and not signals.get(need) and need not in features:
        return {
            "test_id": test_id,
            "status": "UNSUPPORTED",
            "reason": "no_runner_input:%s" % _MISSING_LABEL.get(need, need),
            "missing": [_MISSING_LABEL.get(need, need)],
        }
    if runner == "suite_invoke":
        params = dict(row.get("params") or {})
        tool = params.get("tool", "")
        _hit3 = shutil.which(tool) if isinstance(tool, str) and tool else None
        _stub3 = False
        if _hit3 is not None:
            try:
                _stub3 = ("windowsapps" in str(_hit3).lower())
            except Exception:
                _stub3 = False
            if not _stub3:
                try:
                    if os.path.isfile(_hit3) and os.path.getsize(_hit3) == 0:
                        _stub3 = True
                except OSError:
                    _stub3 = False
        if not tool or _hit3 is None or _stub3:
            return {
                "test_id": test_id,
                "status": "UNSUPPORTED",
                "reason": "tool_not_installed:%s" % (tool or "none"),
                "missing": [tool or "tool"],
            }
        return {"test_id": test_id, "status": "SUPPORTED", "runner": runner, "params": params}
    params = dict(row.get("params") or {})
    if runner in ("api_smoke", "link_check") and project_profile.get("loopback_url"):
        params = dict(params)
        params.setdefault("base_url", project_profile["loopback_url"])
    return {"test_id": test_id, "status": "SUPPORTED", "runner": runner, "params": params}


def _refusal(test_id: str, runner_id: str, status: str, reason: str) -> dict:
    return {
        "test_id": test_id,
        "runner_id": runner_id,
        "status": status,
        "reason": reason,
        "assertions": 0,
        "evidence": [],
        "child_pid": 0,
        "child_env_keys": [],
        "proxies_emptied": False,
    }


def _cancelled(cancel) -> bool:
    if cancel is None:
        return False
    if hasattr(cancel, "is_set"):
        try:
            return bool(cancel.is_set())
        except Exception:
            return False
    if callable(cancel):
        try:
            return bool(cancel())
        except Exception:
            return False
    return False


def _kill_tree(proc) -> None:
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                capture_output=True,
                timeout=10,
                creationflags=quiet_flags(),
            )
        else:
            import signal

            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except Exception:
        pass
    try:
        proc.kill()
    except Exception:
        pass


def _coerce_envelope(test_id: str, runner_id: str, payload) -> dict:
    if not isinstance(payload, dict):
        return _refusal(test_id, runner_id, "BLOCKED", "child_bad_json")
    status = payload.get("status")
    if status not in ("PASS", "FAIL", "BLOCKED", "UNSUPPORTED"):
        return _refusal(test_id, runner_id, "BLOCKED", "child_bad_status")
    if payload.get("runner_id") != runner_id:
        return _refusal(test_id, runner_id, "BLOCKED", "child_id_mismatch")
    result = {key: payload.get(key) for key in _RESULT_KEYS}
    result["test_id"] = test_id or result.get("test_id") or ""
    result["runner_id"] = runner_id
    if not isinstance(result.get("reason"), str) or not result["reason"]:
        result["reason"] = "child gave no reason"
    if not isinstance(result.get("assertions"), int) or isinstance(result.get("assertions"), bool):
        result["assertions"] = 0
    if not isinstance(result.get("evidence"), list):
        result["evidence"] = []
    if not isinstance(result.get("child_pid"), int):
        result["child_pid"] = 0
    if not isinstance(result.get("child_env_keys"), list):
        result["child_env_keys"] = []
    result["proxies_emptied"] = bool(result.get("proxies_emptied"))
    if result["status"] == "PASS" and result["assertions"] < 1:
        result["status"] = "BLOCKED"
        result["reason"] = "zero_assertions"
    return result


def run_code_test(test_id: str, project_root: str, evidence_dir: str, budgets=None, cancel=None) -> dict:
    """Run one CODE catalog test through the jailed host; return the envelope.

    AI and HUMAN tests are refused with BLOCKED (they need a judge or an
    operator, never a subprocess PASS). Unknown ids raise. Cancel may be
    None, a threading.Event or a zero-argument callable.
    """
    row = get_test(test_id)
    kind = row.get("kind", "")
    runner = row.get("runner") or ""
    if kind in JUDGE_KINDS or runner not in KNOWN_RUNNERS:
        return _refusal(test_id, runner if runner in KNOWN_RUNNERS else "", "BLOCKED", "non_code_needs_judge_or_operator")
    if _cancelled(cancel):
        return _refusal(test_id, runner, "BLOCKED", "cancelled")
    root = os.path.abspath(project_root or ".")
    if not os.path.isdir(root):
        return _refusal(test_id, runner, "BLOCKED", "bad_project_root")
    profile = detect_project_profile(root)
    decision = resolve(row, profile)
    if decision["status"] != "SUPPORTED":
        return _refusal(test_id, runner, "UNSUPPORTED", decision.get("reason") or "no_runner_input")
    budgets = dict(budgets or {})
    try:
        timeout_s = float(budgets.get("timeout_s", 60.0))
    except (TypeError, ValueError):
        timeout_s = 60.0
    if not timeout_s > 0:
        timeout_s = 60.0
    timeout_s = min(timeout_s, 300.0)
    evidence = os.path.abspath(budgets.get("evidence_dir") or evidence_dir or os.path.join(root, "qa_evidence"))
    try:
        os.makedirs(evidence, exist_ok=True)
    except OSError:
        return _refusal(test_id, runner, "BLOCKED", "bad_evidence_dir")
    host = _host_path()
    if not os.path.isfile(host):
        return _refusal(test_id, runner, "BLOCKED", "host_missing")
    request = {
        "project_root": root,
        "test_id": test_id,
        "params": decision.get("params") or {},
        "budgets": {"timeout_s": timeout_s, "evidence_dir": evidence},
    }
    try:
        if getattr(sys, "frozen", False):
            # Frozen exe: sys.executable is the app itself, so spawning
            # [exe, host, runner] would start a second full app (window
            # + single-instance lock + folder picker). Route through the
            # sidecar flag instead: main() handles --qa-runner before
            # any window, lock, port pick or server start. The literal
            # must stay equal to agent_si.sidecar._QA_RUNNER_FLAG
            # (pinned by test; literal here keeps catalog_v2 stdlib-only
            # with no sidecar import).
            argv = [sys.executable, "--qa-runner", runner]
        else:
            argv = [sys.executable, host, runner]
        proc = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=root,
            creationflags=quiet_flags(),
        )
    except Exception as exc:
        return _refusal(test_id, runner, "BLOCKED", "host_spawn_failed: %s" % exc)
    try:
        proc.stdin.write(json.dumps(request).encode("utf-8"))
        proc.stdin.close()
    except (BrokenPipeError, OSError):
        pass
    deadline = time.monotonic() + timeout_s + 15.0
    while proc.poll() is None:
        if _cancelled(cancel):
            _kill_tree(proc)
            try:
                proc.wait(timeout=5)
            except Exception:
                pass
            return _refusal(test_id, runner, "BLOCKED", "cancelled")
        if time.monotonic() >= deadline:
            _kill_tree(proc)
            try:
                proc.wait(timeout=5)
            except Exception:
                pass
            return _refusal(test_id, runner, "BLOCKED", "host_timeout")
        time.sleep(0.2)
    try:
        out, _ = proc.communicate(timeout=10)
    except Exception:
        out = b""
    if proc.returncode != 0:
        return _refusal(test_id, runner, "BLOCKED", "host_exit_%s" % proc.returncode)
    if not (out or b"").strip():
        return _refusal(test_id, runner, "BLOCKED", "host_empty")
    try:
        payload = json.loads((out or b"").decode("utf-8"))
    except ValueError:
        return _refusal(test_id, runner, "BLOCKED", "child_bad_json")
    return _coerce_envelope(test_id, runner, payload)
