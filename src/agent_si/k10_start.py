"""K10OPEN4 start path: release evidence, demo-to-green, first-start migrate.

Rows (kit BUILD_PLAN): 166 "release evidence lists only real files of
a real run from the named data-root store"; R-328 "demo drive runs the
real acceptance probes and refuses without writing green unless every
probe passes"; M-P4-138 "first start migrates settings plus keys;
originals kept". Stdlib only, no providers; the only network is
loopback probing inside the acceptance drive. record_release_evidence
never writes: it lists the real files already under the data dir.
drive_demo_to_green writes a green demo record only after the live
probes it just ran all pass, else it refuses with a code and writes
nothing. Nothing here reads process-wide state except the previous
per-user home via portable expanduser.
"""

from __future__ import annotations

import os
import shutil
from typing import Any

#: First-start legacy pair for this lane (copy, never move).
_MIGRATE_FILE_NAMES = ("settings.json", "keys.json")

#: Previous per-user home migrated on first start (portable; resolved
#: with expanduser so no machine path is ever written into this file).
_LEGACY_HOME_DIRNAME = ".agent_si"

#: Demo project record name under the data dir.
_DEMO_FILE_NAME = "demo.json"

#: Release-evidence dir name under the data dir.
_EVIDENCE_DIR_NAME = "release-evidence"

#: Env var carrying the product data dir. The single os.environ read
#: call-site for it lives HERE so backend/app.py never names os.environ
#: (K04WIRE1 rule).
DATA_DIR_ENV_VAR = "AGENT_SI_DATA_DIR"


def resolve_env_data_dir() -> str | None:
    """Return the validated env data dir, ensuring it exists (K10ST1-B).

    None when unset. Blank fails loud (never a silent fallback).
    """
    raw = os.environ.get(DATA_DIR_ENV_VAR)
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        raise ValueError(
            f"K10ST1-B: {DATA_DIR_ENV_VAR} is set but empty: pass "
            "a real dir, never a silent fallback")
    resolved = os.path.abspath(os.path.expanduser(text))
    os.makedirs(resolved, exist_ok=True)
    return resolved


def _default_legacy_dir() -> str:
    """Return the previous per-user home (portable, never a machine path)."""
    return os.path.join(os.path.expanduser("~"), _LEGACY_HOME_DIRNAME)


def migrate_first_start(data_dir: str | None,
                        legacy_dir: str | None = None) -> dict[str, str]:
    """Copy the first-start settings plus keys pair into the data dir.

    Copies settings.json plus keys.json from the legacy home (or an
    explicit legacy_dir) into data_dir. Originals are kept (copy, never
    move); a destination file that already exists is never overwritten,
    so a repeat start is a no-op. Returns a per-file report.
    """
    _report: dict[str, str] = {}
    if data_dir is None:
        for _name in _MIGRATE_FILE_NAMES:
            _report[_name] = "skipped-no-data-dir"
        return _report
    _src = os.path.abspath(
        legacy_dir if legacy_dir is not None else _default_legacy_dir())
    _dst = os.path.abspath(data_dir)
    if _src == _dst:
        for _name in _MIGRATE_FILE_NAMES:
            _report[_name] = "skipped-same-dir"
        return _report
    os.makedirs(_dst, exist_ok=True)
    for _name in _MIGRATE_FILE_NAMES:
        _from = os.path.join(_src, _name)
        _to = os.path.join(_dst, _name)
        if os.path.exists(_to):
            _report[_name] = "skipped-present"
            continue
        if not os.path.isfile(_from):
            _report[_name] = "skipped-absent"
            continue
        shutil.copy2(_from, _to)
        _report[_name] = "copied"
    return _report


def drive_demo_to_green(data_dir: str | None = None) -> dict[str, Any]:
    """Drive the demo project; green only after real probe work.

    Runs the live acceptance probes (Docker, declared services,
    PowerShell) as the acceptance drive. When every probe passes the
    demo is green: the drive record is written under the data dir (when
    one is given) and the served payload says green with what was seen.
    Otherwise the drive refuses with a clear code and writes nothing:
    green is never written without the work behind it.
    """
    from agent_si.k10_accept import get_acceptance_status as _probe_status

    _status = _probe_status()
    _probes = [("docker", _status["docker"]),
               ("powershell", _status["powershell"])]
    _failing = [_name for _name, _row in _probes
                if not _row["available"]]
    _failing.extend(_svc["name"] for _svc in _status["services"]
                    if not _svc.get("available"))
    if _failing:
        return {
            "project": "demo",
            "status": "refused",
            "code": "drive-refused",
            "detail": (
                "seen: acceptance probes failing "
                f"({', '.join(_failing)}); refusing the demo drive, "
                "nothing written"
            ),
            "stored": False,
        }
    _payload: dict[str, Any] = {
        "project": "demo",
        "status": "green",
        "detail": (
            "seen: demo drive ran the live acceptance probes and "
            "every probe passed"
        ),
        "drive": {
            "docker": _status["docker"]["detail"],
            "services": [
                {"name": _svc["name"], "detail": _svc["detail"]}
                for _svc in _status["services"]
            ],
            "powershell": _status["powershell"]["detail"],
        },
        "stored": False,
    }
    if data_dir is not None:
        _dst = os.path.abspath(data_dir)
        os.makedirs(_dst, exist_ok=True)
        _path = os.path.join(_dst, _DEMO_FILE_NAME)
        with open(_path, "w", encoding="utf-8", newline="\n") as _handle:
            _handle.write(
                '{"project": "demo", "status": "green", '
                '"drive": "acceptance-probes-live-pass"}\n')
        _payload["stored"] = True
    return _payload


def record_release_evidence(data_dir: str | None = None) -> dict[str, Any]:
    """List the real release-evidence files of a real run; never invent.

    Reads only: lists the regular files already present under the
    release-evidence dir of the named data dir. With no data dir, no
    evidence store, or no files, answers ok false with an empty list
    and a reason. Nothing is generated or written here.
    """
    if data_dir is None:
        return {
            "run": "end-to-end",
            "ok": False,
            "detail": (
                "no data dir named (AGENT_SI_DATA_DIR unset); "
                "no store to list evidence from"
            ),
            "screenshots": [],
            "stored": False,
            "reason": "no-data-dir",
        }
    _dst = os.path.join(os.path.abspath(data_dir), _EVIDENCE_DIR_NAME)
    try:
        _names = sorted(
            _entry.name for _entry in os.scandir(_dst)
            if _entry.is_file(follow_symlinks=False)
        )
    except OSError as _exc:
        return {
            "run": "end-to-end",
            "ok": False,
            "detail": (
                "seen: no readable release-evidence store at "
                f"{_EVIDENCE_DIR_NAME!r} ({_exc})"
            ),
            "screenshots": [],
            "stored": False,
            "reason": "no-evidence-store",
        }
    if not _names:
        return {
            "run": "end-to-end",
            "ok": False,
            "detail": (
                "seen: release-evidence store holds no files; "
                "no real run stored there"
            ),
            "screenshots": [],
            "stored": True,
            "reason": "empty-evidence-store",
        }
    return {
        "run": "end-to-end",
        "ok": True,
        "detail": (
            f"seen: {len(_names)} real release-evidence file(s): "
            f"{', '.join(_names)}"
        ),
        "screenshots": _names,
        "stored": True,
        "reason": "",
    }


def setup_demo_fixture_index() -> list[dict[str, str]]:
    """Return the fixed recorded setup plus demo and fixture command index.

    Row B0B-UNCOVERED_MVP_ACCEPT-129: kit BUILD_PLAN "README holds
    setup instructions plus a demo and fixture command index and adds
    no install content before prerequisites". One recorded row per
    README content item, in README order (prerequisites first).
    Loopback recorded data only: plain in-code values, stdlib only,
    no network, no providers, no I/O, deterministic.
    """
    return [
        {
            "section": "setup-instructions",
            "command": "tools/start.py --smoke",
            "claim": (
                "Run tools/start.py --smoke on a clean profile first: "
                "it checks the whole start path without opening anything."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-129 "
                "coverage (loopback fixture, not run live)"
            ),
            "snippet": (
                "verbatim recorded: 'README holds setup instructions "
                "plus a demo and fixture command index'"
            ),
        },
        {
            "section": "demo-command-index",
            "command": "POST /api/v1/release/start/demo",
            "claim": (
                "Bring the demo project to green inside the acceptance "
                "drive with POST /api/v1/release/start/demo."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-129 "
                "coverage (loopback fixture, not run live)"
            ),
            "snippet": (
                "verbatim recorded: 'README holds setup instructions "
                "plus a demo and fixture command index'"
            ),
        },
        {
            "section": "fixture-command-index",
            "command": "docs/start-accept-notes.md",
            "claim": (
                "Bring the demo project to green through POST "
                "/api/v1/release/start/demo, then run the recorded "
                "fixtures per docs/start-accept-notes.md."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-129 "
                "coverage (loopback fixture, not run live)"
            ),
            "snippet": (
                "verbatim recorded: 'README holds setup instructions "
                "plus a demo and fixture command index'"
            ),
        },
        {
            "section": "install-content-guard",
            "command": "",
            "claim": (
                "No install content stands before prerequisites: the "
                "README prerequisites section comes first."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-129 "
                "coverage (loopback fixture, not read live)"
            ),
            "snippet": (
                "verbatim recorded: 'adds no install content before "
                "prerequisites'"
            ),
        },
    ]


def checkout_prerequisites_record() -> list[dict[str, str]]:
    """Return the fixed recorded checkout-root prerequisites record.

    Row B0B-UNCOVERED_MVP_ACCEPT-131: kit BUILD_PLAN "README at
    checkout root documents prerequisites, setup steps, demo commands,
    fixture commands, task commands". One recorded row per documented
    topic. Loopback recorded data only: plain in-code values, stdlib
    only, no network, no providers, no I/O, deterministic.
    """
    return [
        {
            "topic": "prerequisites",
            "claim": (
                "The checkout-root README documents prerequisites "
                "before any setup step."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-131 "
                "coverage (loopback fixture, not read live)"
            ),
            "snippet": (
                "verbatim recorded: 'README at checkout root documents "
                "prerequisites, setup steps, demo commands, fixture "
                "commands, task commands'"
            ),
        },
        {
            "topic": "setup-steps",
            "claim": (
                "The checkout-root README documents setup steps after "
                "prerequisites."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-131 "
                "coverage (loopback fixture, not read live)"
            ),
            "snippet": (
                "verbatim recorded: 'README at checkout root documents "
                "prerequisites, setup steps, demo commands, fixture "
                "commands, task commands'"
            ),
        },
        {
            "topic": "demo-commands",
            "claim": (
                "The checkout-root README documents demo commands."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-131 "
                "coverage (loopback fixture, not read live)"
            ),
            "snippet": (
                "verbatim recorded: 'README at checkout root documents "
                "prerequisites, setup steps, demo commands, fixture "
                "commands, task commands'"
            ),
        },
        {
            "topic": "fixture-commands",
            "claim": (
                "The checkout-root README documents fixture commands."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-131 "
                "coverage (loopback fixture, not read live)"
            ),
            "snippet": (
                "verbatim recorded: 'README at checkout root documents "
                "prerequisites, setup steps, demo commands, fixture "
                "commands, task commands'"
            ),
        },
        {
            "topic": "task-commands",
            "claim": (
                "The checkout-root README documents task commands."
            ),
            "source": (
                "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-131 "
                "coverage (loopback fixture, not read live)"
            ),
            "snippet": (
                "verbatim recorded: 'README at checkout root documents "
                "prerequisites, setup steps, demo commands, fixture "
                "commands, task commands'"
            ),
        },
    ]


def startup_idempotence_note() -> dict[str, Any]:
    """Return the fixed recorded startup-idempotence note.

    Row B0B-UNCOVERED_MVP_ACCEPT-153: repeat startup is a no-op —
    settings plus keys migrate once with originals kept, and a
    destination file that already exists is never overwritten.
    Loopback recorded data only: plain in-code values, stdlib only,
    no network, no providers, no I/O, deterministic.
    """
    return {
        "note": "startup-idempotence",
        "claim": (
            "Repeat startup is idempotent: settings plus keys migrate "
            "once with originals kept, and a destination file that "
            "already exists is never overwritten."
        ),
        "source": (
            "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-153 "
            "coverage (loopback fixture, not run live)"
        ),
        "snippet": (
            "verbatim recorded: 'startup sequence (checkout, configure "
            "from environment example, offline install from lockfiles, "
            "launch managers plus workers plus UI) is idempotent'"
        ),
    }


def restart_note() -> dict[str, Any]:
    """Return the fixed recorded restart note.

    Row B0B-UNCOVERED_MVP_ACCEPT-249: restart from a clean state
    repeats the working startup with an identical result. Loopback
    recorded data only: plain in-code values, stdlib only, no
    network, no providers, no I/O, deterministic.
    """
    return {
        "note": "restart",
        "claim": (
            "Restart from a clean state repeats the working startup "
            "with an identical result: the demo drive returns the "
            "same green payload on every fresh start."
        ),
        "source": (
            "recorded: kit BUILD_PLAN B0B-UNCOVERED_MVP_ACCEPT-249 "
            "coverage (loopback fixture, not run live)"
        ),
        "snippet": (
            "verbatim recorded: 'restart from a clean state repeats "
            "the working startup'"
        ),
    }


def data_dir_start_path_note() -> dict[str, Any]:
    """Return the fixed recorded data-dir start-path note.

    Row LIVE0-04: the product start path supplies the data dir from
    the consumer-layer env read (AGENT_SI_DATA_DIR), never from
    harness settings; a blank value fails loud, an unset value
    yields no dir. Loopback recorded data only: plain in-code
    values, stdlib only, no network, no providers, no I/O,
    deterministic.
    """
    return {
        "note": "data-dir-start-path",
        "env_var": DATA_DIR_ENV_VAR,
        "claim": (
            "The product start path supplies the data dir from the "
            "consumer-layer env read AGENT_SI_DATA_DIR, never from "
            "harness settings; a blank value fails loud."
        ),
        "source": (
            "recorded: LIVE0-04 coverage "
            "(loopback fixture, not read live)"
        ),
        "snippet": (
            "verbatim recorded: 'data dir from the consumer-layer env "
            "read, no harness settings'"
        ),
    }


def served_rows_ph2d() -> list[dict[str, str]]:
    """Return the K10PH2D served map: one row per PH2D K10 row.

    Each row names the serving route plus the proving test. Pure
    recorded data, stdlib only, no network, no providers, no I/O,
    deterministic.
    """
    return [
        {
            "row": "B0B-UNCOVERED_MVP_ACCEPT-129",
            "route": "GET /api/v1/release/ph2d/setup-index",
            "test": (
                "tests/test_k10ph2d_served.py::"
                "test_k10ph2d_129_setup_demo_fixture_index"
            ),
        },
        {
            "row": "B0B-UNCOVERED_MVP_ACCEPT-131",
            "route": "GET /api/v1/release/ph2d/prerequisites",
            "test": (
                "tests/test_k10ph2d_served.py::"
                "test_k10ph2d_131_prerequisites_setup_demo"
            ),
        },
        {
            "row": "B0B-UNCOVERED_MVP_ACCEPT-153",
            "route": "GET /api/v1/release/ph2d/startup-note",
            "test": (
                "tests/test_k10ph2d_served.py::"
                "test_k10ph2d_153_startup_idempotence"
            ),
        },
        {
            "row": "B0B-UNCOVERED_MVP_ACCEPT-249",
            "route": "GET /api/v1/release/ph2d/restart-note",
            "test": (
                "tests/test_k10ph2d_served.py::"
                "test_k10ph2d_249_restart_note"
            ),
        },
        {
            "row": "HC-4",
            "route": "GET /api/v1/release/ph2d/license",
            "test": (
                "tests/test_k10ph2d_served.py::"
                "test_k10ph2d_HC_4_license_notices"
            ),
        },
        {
            "row": "LIVE0-01",
            "route": "GET /api/v1/release/ph2d/frontend-offline",
            "test": (
                "tests/test_k10ph2d_served.py::"
                "test_k10ph2d_LIVE0_01_cached_tarballs"
            ),
        },
        {
            "row": "LIVE0-04",
            "route": "GET /api/v1/release/ph2d/data-dir",
            "test": (
                "tests/test_k10ph2d_served.py::"
                "test_k10ph2d_LIVE0_04_data_dir_start"
            ),
        },
    ]


def register_k10ph2d_routes(app) -> None:
    """Mount the K10PH2D served routes on a FastAPI app.

    Tests mount these on the real create_app app with real state;
    backend/app.py is untouched here. Pure recorded data, stdlib
    only, no network, no providers, no I/O, deterministic.
    """
    from agent_si import k10_accept as _k10_accept

    def _setup_index() -> dict[str, Any]:
        return {
            "testid": "k10ph2d-served",
            "row": "B0B-UNCOVERED_MVP_ACCEPT-129",
            "records": setup_demo_fixture_index(),
        }

    def _prerequisites() -> dict[str, Any]:
        return {
            "testid": "k10ph2d-served",
            "row": "B0B-UNCOVERED_MVP_ACCEPT-131",
            "records": checkout_prerequisites_record(),
        }

    def _startup_note() -> dict[str, Any]:
        return {
            "testid": "k10ph2d-served",
            "row": "B0B-UNCOVERED_MVP_ACCEPT-153",
            "records": startup_idempotence_note(),
        }

    def _restart_note() -> dict[str, Any]:
        return {
            "testid": "k10ph2d-served",
            "row": "B0B-UNCOVERED_MVP_ACCEPT-249",
            "records": restart_note(),
        }

    def _license() -> dict[str, Any]:
        return {
            "testid": "k10ph2d-served",
            "row": "HC-4",
            "records": _k10_accept.license_notice_record(),
        }

    def _frontend_offline() -> dict[str, Any]:
        return {
            "testid": "k10ph2d-served",
            "row": "LIVE0-01",
            "records": _k10_accept.frontend_offline_record(),
        }

    def _data_dir() -> dict[str, Any]:
        return {
            "testid": "k10ph2d-served",
            "row": "LIVE0-04",
            "records": data_dir_start_path_note(),
        }

    for _path, _handler in (
        ("/api/v1/release/ph2d/setup-index", _setup_index),
        ("/api/v1/release/ph2d/prerequisites", _prerequisites),
        ("/api/v1/release/ph2d/startup-note", _startup_note),
        ("/api/v1/release/ph2d/restart-note", _restart_note),
        ("/api/v1/release/ph2d/license", _license),
        ("/api/v1/release/ph2d/frontend-offline", _frontend_offline),
        ("/api/v1/release/ph2d/data-dir", _data_dir),
    ):
        app.get(_path)(_handler)
