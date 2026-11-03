# FXSTART boot log: one startup.log per boot from the real start path.
"""Record the boot in ``<data dir>/startup.log`` (rows 1107-1115).

Every boot of the product (``tools/start.py`` ``--smoke``/``--serve``
and the sidecar ``main``) writes this file through :func:`write_boot_log`
so the frozen TRIAL2 check can read one line per fact. Lines are plain
``key=value`` (UTF-8, ``\\n``), written atomically (temp file plus
rename). Values carry ids, hashes and pins only: never a key value,
never a token, never an absolute path.

Line order and meaning::

    product_version=<from pyproject.toml, else the sidecar constant>
    provider_ids=<sorted configured provider ids, comma separated>
    providers_double=<mock-flagged ids among them (TEST FIXTURES doubles)>
    providers_absent=<hosted preset ids with no configured instance>
    backend_locked=<sha256 of pyproject.toml> pins=<name==version,...>
    frontend_locked=<sha256 of package-lock.json> pins=<...> source=<...>
    migration_level=<settled settings/credentials/keys files in data dir>
    boot=OK | boot=FAILED reason=<code>
    health_self_check=<pass|FAILED ...> secret-store=... data-dir=...
    host=127.0.0.1
    host_blockers=<missing local permission;auditor provider;...|none>
    timestamp=<UTC boot time, for humans; tests compare without it>

Failure codes: ``missing-tarball`` (no cached frontend tarball),
``absent-wheel`` (a pinned backend wheel is absent, never substituted).
Stdlib only, no network beyond the loopback the caller already uses,
no process-wide state. Every helper is total: unreadable inputs become
an ``absent``/``unresolved`` value, only the final file write raises.
"""

from __future__ import annotations

import contextlib
import datetime
import hashlib
import json
import os
import re
import sys
import tempfile
import zipfile

STARTUP_LOG_NAME = "startup.log"

REQUIRED_KEYS = (
    "product_version",
    "provider_ids",
    "providers_double",
    "providers_absent",
    "backend_locked",
    "frontend_locked",
    "migration_level",
    "boot",
    "health_self_check",
    "host",
)

HOST = "127.0.0.1"

SETTLED_FILE_NAMES = ("settings.json", "credentials.json", "keys.json")

WHEELS_DIR_ENV = "AGENT_SI_WHEELS_DIR"
FRONTEND_TARBALL_ENV = "AGENT_SI_FRONTEND_TARBALL"

FAIL_MISSING_TARBALL = "missing-tarball"
FAIL_ABSENT_WHEEL = "absent-wheel"


def startup_log_path(data_dir: str) -> str:
    """Absolute path of the boot log under the product data dir."""
    return os.path.abspath(os.path.join(str(data_dir), STARTUP_LOG_NAME))


def repo_root() -> str:
    """Checkout root (frozen bundle dir when frozen)."""
    meipass = getattr(sys, "_MEIPASS", None)
    if getattr(sys, "frozen", False) and meipass:
        return os.path.abspath(str(meipass))
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(os.path.dirname(here))
    probe = os.path.join(root, "pyproject.toml")
    if os.path.isfile(probe):
        return os.path.abspath(root)
    return os.path.abspath(os.getcwd())


def _clean(value: object) -> str:
    text = str(value) if value is not None else ""
    text = text.replace("\r", " ").replace("\n", " ").strip()
    return re.sub(r"\s+", " ", text)


def _sha256_file(path: str) -> str | None:
    try:
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(65536), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def _load_toml(path: str) -> dict | None:
    try:
        import tomllib as _toml
    except ImportError:
        _toml = None  # type: ignore[assignment]
    if _toml is not None:
        try:
            with open(path, "rb") as handle:
                data = _toml.load(handle)
            return data if isinstance(data, dict) else None
        except (OSError, ValueError):
            return None
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except OSError:
        return None
    match = re.search(r"(?m)^version\s*=\s*[\"']([^\"']+)[\"']", text)
    if not match:
        return None
    return {"project": {"version": match.group(1),
                        "dependencies": re.findall(
                            r"(?m)^\s*[\"']([A-Za-z0-9_.\-]+==[^\"']+)[\"']",
                            text)}}


def backend_pins(root: str) -> list[tuple[str, str]]:
    """Pinned ``(name, version)`` backend deps from pyproject.toml."""
    data = _load_toml(os.path.join(str(root), "pyproject.toml"))
    if not data:
        return []
    try:
        deps = data.get("project", {}).get("dependencies", [])
    except AttributeError:
        return []
    pins: list[tuple[str, str]] = []
    if isinstance(deps, list):
        for dep in deps:
            name, sep, version = str(dep).partition("==")
            if sep and name.strip() and version.strip():
                pins.append((name.strip(), version.strip()))
    return pins


def product_version(root: str | None = None) -> str:
    """Product version: pyproject.toml, else the sidecar constant."""
    base = str(root) if root is not None else repo_root()
    data = _load_toml(os.path.join(base, "pyproject.toml"))
    try:
        version = data.get("project", {}).get("version") if data else None
    except AttributeError:
        version = None
    if isinstance(version, str) and version.strip():
        return _clean(version)
    try:
        from agent_si.sidecar import VERSION as _sidecar_version
    except Exception:
        return "unknown"
    if isinstance(_sidecar_version, str) and _sidecar_version.strip():
        return _clean(_sidecar_version)
    return "unknown"


def backend_locked(root: str | None = None) -> str:
    """Backend lock state: hash plus pinned list of pyproject.toml."""
    base = str(root) if root is not None else repo_root()
    path = os.path.join(base, "pyproject.toml")
    digest = _sha256_file(path)
    if digest is None:
        return "absent"
    pins = ",".join(f"{name}=={version}"
                    for name, version in backend_pins(base))
    return _clean(f"sha256:{digest} pins:{pins or 'none'}")


def _frontend_lock_pins(lock_path: str) -> list[tuple[str, str]]:
    try:
        with open(lock_path, encoding="utf-8") as handle:
            lock = json.load(handle)
    except (OSError, ValueError):
        return []
    if not isinstance(lock, dict):
        return []
    try:
        packages = lock.get("packages", {})
        top = packages.get("", {})
        deps: dict = {}
        for key in ("dependencies", "devDependencies"):
            group = top.get(key, {})
            if isinstance(group, dict):
                deps.update(group)
    except AttributeError:
        return []
    return [(str(name), str(version))
            for name, version in sorted(deps.items())
            if isinstance(version, str) and version.strip()]


def _frontend_root_pins(root: str) -> list[tuple[str, str]]:
    return _frontend_lock_pins(
        os.path.join(str(root), "frontend", "package-lock.json"))


def frontend_locked(root: str | None = None) -> str:
    """Frontend lock state: hash plus pins of package-lock.json.

    Frozen bundle without the lockfile falls back to the hash of the
    staged ``frontend/dist/index.html`` (marked ``bundled-dist``).
    """
    base = str(root) if root is not None else repo_root()
    path = os.path.join(base, "frontend", "package-lock.json")
    digest = _sha256_file(path)
    source = "checkout"
    if digest is None and getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            bundled = os.path.join(str(meipass), "frontend",
                                   "package-lock.json")
            digest = _sha256_file(bundled)
            if digest is not None:
                source = "bundled"
                path = bundled
    if digest is None and getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            staged = os.path.join(str(meipass), "frontend", "dist",
                                  "index.html")
            staged_digest = _sha256_file(staged)
            if staged_digest is not None:
                return _clean("bundled-dist "
                              f"sha256:{staged_digest} source=bundled-dist")
    if digest is None:
        return "absent"
    pins = ",".join(f"{name}=={version}"
                    for name, version in _frontend_lock_pins(path))
    if not pins:
        pins = "none"
    return _clean(f"sha256:{digest} pins:{pins} source={source}")


def _configured_records(data_dir: str) -> list:
    try:
        from agent_si.providers.registry import (
            provider_store as _store,
        )
    except Exception:
        return []
    try:
        records = _store.load_connections(str(data_dir))
    except Exception:
        return []
    return [rec for rec in records if isinstance(rec, dict)]


def _hosted_preset_ids() -> list[str]:
    try:
        from agent_si.providers.registry import contracts as _contracts
        from agent_si.providers.registry import presets as _presets
    except Exception:
        return []
    try:
        hosted = {_contracts.TRANSPORT_OPENAI_COMPATIBLE,
                  _contracts.TRANSPORT_LITELLM_BACKED}
        ids = [str(key) for key, preset in _presets.PRESETS.items()
               if isinstance(preset, dict)
               and preset.get("transport") in hosted]
    except Exception:
        return []
    return ids


def provider_snapshot(data_dir: str) -> tuple[str, str, str]:
    """Configured ids, mock-flagged doubles, absent hosted presets.

    Ids only, never key material: the connections file stores refs,
    and only ``provider_id`` plus the ``mock`` flag are read here.
    """
    records = _configured_records(data_dir)
    ids: set[str] = set()
    doubles: set[str] = set()
    real: set[str] = set()
    for record in records:
        pid = record.get("provider_id")
        if not isinstance(pid, str) or not pid.strip():
            continue
        pid = pid.strip()
        ids.add(pid)
        if record.get("mock"):
            doubles.add(pid)
        else:
            real.add(pid)
    absent = [pid for pid in _hosted_preset_ids() if pid not in real]
    return (",".join(sorted(ids)), ",".join(sorted(doubles)),
            ",".join(absent))


def migration_level(data_dir: str) -> int:
    """Settled first-start files in the data dir (0-3, pure read)."""
    try:
        base = os.path.abspath(str(data_dir))
    except Exception:
        return 0
    level = 0
    for name in SETTLED_FILE_NAMES:
        try:
            if os.path.isfile(os.path.join(base, name)):
                level += 1
        except OSError:
            continue
    return level


def health_self_check(data_dir: str) -> str:
    """Loopback-free self check: secret store readable, data dir writable."""
    try:
        base = os.path.abspath(str(data_dir))
    except Exception:
        base = ""
    if not base or not os.path.isdir(base):
        data_state = "data-dir=missing"
    elif not os.access(base, os.W_OK | os.X_OK):
        data_state = "data-dir=read-only"
    else:
        data_state = "data-dir=writable"
    try:
        from agent_si.providers.registry import facades as _facades
        _api, _store, _sink = _facades.memory_stack()
        readable = _store.has("fxstart-health-probe-absent") is False
    except Exception as exc:
        code = type(exc).__name__
        return _clean("FAILED reason=secret-store-unreadable "
                      f"secret-store=unavailable:{code} {data_state}")
    if not readable:
        return _clean("FAILED reason=secret-store-unreadable "
                      f"secret-store=denied {data_state}")
    return _clean(f"pass secret-store=readable {data_state}")


def _host_blocker_names() -> tuple[str, str, str]:
    try:
        from agent_si import k10_accept as _accept
        return (_accept.HOST_BLOCKER_MISSING_LOCAL_PERMISSION,
                _accept.HOST_BLOCKER_MISSING_AUDITOR_PROVIDER,
                _accept.HOST_BLOCKER_MISSING_SECOND_REAL_PROVIDER)
    except Exception:
        return ("missing local permission", "auditor provider",
                "second real provider")


def host_blockers(data_dir: str, real_ids: list[str] | set[str]) -> str:
    """Host shortfall names: local permission, auditor, second provider."""
    missing_perm, auditor, second = _host_blocker_names()
    blockers: list[str] = []
    try:
        writable = os.access(os.path.abspath(str(data_dir)),
                             os.W_OK | os.X_OK)
    except Exception:
        writable = False
    if not writable:
        blockers.append(missing_perm)
    real = sorted({str(pid) for pid in real_ids if str(pid).strip()})
    if len(real) < 1:
        blockers.append(auditor)
    if len(real) < 2:
        blockers.append(second)
    return ";".join(blockers) if blockers else "none"


def _dist_filename(name: str) -> str:
    return re.sub(r"[-_.]+", "_", str(name)).lower()


def backend_wheel_missing(root: str,
                          wheels_dir: str | None) -> list[str]:
    """Pinned backend wheels absent from the offline cache.

    With a wheels dir in play (``AGENT_SI_WHEELS_DIR`` or ``<root>/wheels``)
    every pin needs a matching ``*.whl`` there (a corrupt archive counts
    as missing). Without one, every pin must hold an installed dist at
    the pinned version. No network in either path; no substitution.
    """
    pins = backend_pins(str(root))
    missing: list[str] = []
    if wheels_dir:
        try:
            names = set(os.listdir(str(wheels_dir)))
        except OSError:
            names = set()
        for name, version in pins:
            prefix = f"{_dist_filename(name)}-{version}-"
            hits = [entry for entry in names
                    if entry.lower().startswith(prefix)
                    and entry.lower().endswith(".whl")]
            good = False
            for entry in hits:
                try:
                    good = zipfile.is_zipfile(
                        os.path.join(str(wheels_dir), entry))
                except OSError:
                    good = False
                if good:
                    break
            if not good:
                missing.append(f"wheel:{name}")
        return missing
    try:
        from importlib import metadata as _metadata
    except ImportError:
        return [f"wheel:{name}" for name, _ in pins]
    for name, version in pins:
        try:
            installed = _metadata.version(name)
        except Exception:
            missing.append(f"wheel:{name}")
            continue
        if str(installed).strip() != version:
            missing.append(f"wheel:{name}")
    return missing


def frontend_tarball_missing(root: str,
                             tarball_path: str | None) -> list[str]:
    """Cached frontend tarball absent from the offline install input.

    With ``AGENT_SI_FRONTEND_TARBALL`` set, that file must exist and be
    non-empty. Without it, the materialized ``frontend/node_modules``
    tree must carry every root-lockfile pin at its pinned version.
    """
    if tarball_path:
        try:
            ok = (os.path.isfile(str(tarball_path))
                  and os.path.getsize(str(tarball_path)) > 0)
        except OSError:
            ok = False
        return [] if ok else ["tarball:frontend"]
    pins = _frontend_root_pins(str(root))
    if not pins:
        return ["tarball:frontend"]
    missing: list[str] = []
    for name, version in pins:
        pkg_path = os.path.join(str(root), "frontend", "node_modules",
                                *str(name).split("/"), "package.json")
        try:
            with open(pkg_path, encoding="utf-8") as handle:
                pkg = json.load(handle)
            installed = pkg.get("version")
        except (OSError, ValueError):
            installed = None
        if not isinstance(installed, str) or installed.strip() != version:
            missing.append(f"tarball:{name}")
    return missing


def write_boot_log(data_dir: str, root: str | None = None, *,
                   boot: str = "OK", reason: str | None = None) -> str:
    """Write ``<data dir>/startup.log``; return its absolute path."""
    base = os.path.abspath(str(data_dir))
    os.makedirs(base, exist_ok=True)
    root_arg = str(root) if root is not None else repo_root()
    ids, doubles, absent = provider_snapshot(base)
    double_set = set(doubles.split(",")) if doubles else set()
    real_ids = [pid for pid in ids.split(",") if pid and pid not in double_set]
    status = "OK" if str(boot).upper() == "OK" else "FAILED"
    clean_reason = _clean(reason) if reason else "start-failed"
    boot_line = "OK" if status == "OK" else f"FAILED reason={clean_reason}"
    boot_time = datetime.datetime.now(datetime.UTC).replace(
        microsecond=0).isoformat()
    lines = [
        f"product_version={product_version(root_arg)}",
        f"provider_ids={_clean(ids)}",
        f"providers_double={_clean(doubles)}",
        f"providers_absent={_clean(absent)}",
        f"backend_locked={backend_locked(root_arg)}",
        f"frontend_locked={frontend_locked(root_arg)}",
        f"migration_level={migration_level(base)}",
        f"boot={boot_line}",
        f"health_self_check={health_self_check(base)}",
        f"host={HOST}",
        f"host_blockers={_clean(host_blockers(base, real_ids))}",
        f"timestamp={boot_time}",
    ]
    path = os.path.join(base, STARTUP_LOG_NAME)
    fd, tmp = tempfile.mkstemp(dir=base, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write("\n".join(lines) + "\n")
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise
    for key in REQUIRED_KEYS:
        assert any(line.startswith(key + "=") for line in lines), key
    return path
