"""FXSTART boot log: real startup.log from the real start path.

Rows (kit BUILD_PLAN 1107-1115): startup log records provider set plus
mock doubles plus absent real providers; backend plus frontend locked
versions; missing cached tarball aborts FAILED; absent wheel aborts
FAILED with no substitution; offline install contacts nothing remote;
host blockers name missing permission, auditor provider, second
provider; idempotent repeat startup. Every test below boots the REAL
tools/start.py by subprocess (real entry, no recorded rows).
"""
import os
import re
import subprocess
import sys
import tarfile
import zipfile

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, ".."))
_START = os.path.join(_ROOT, "tools", "start.py")
_ENV_EXAMPLE = os.path.join(_ROOT, "env.example")

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

_CANARY = "fxstart-canary-no-key-9f2"


def _pins():
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib  # type: ignore[no-redef]
    with open(os.path.join(_ROOT, "pyproject.toml"), "rb") as handle:
        data = tomllib.load(handle)
    pins = []
    for dep in data["project"]["dependencies"]:
        name, _, version = dep.partition("==")
        pins.append((name.strip(), version.strip()))
    return pins


def _dist_filename(name):
    return re.sub(r"[-_.]+", "_", name).lower()


def _make_wheels(wheels_dir):
    os.makedirs(wheels_dir, exist_ok=True)
    for name, version in _pins():
        wheel = f"{_dist_filename(name)}-{version}-py3-none-any.whl"
        path = os.path.join(wheels_dir, wheel)
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("METADATA", f"Name: {name}\nVersion: {version}\n")


def _make_tarball(path):
    with tarfile.open(path, "w:gz") as archive:
        content = b"fxstart cached frontend tarball fixture\n"
        info = tarfile.TarInfo("package.json")
        info.size = len(content)
        import io
        archive.addfile(info, io.BytesIO(content))


def _base_env(home, data_dir, extra=None):
    env = dict(os.environ)
    env["HOME"] = home
    env["USERPROFILE"] = home
    env["AGENT_SI_DATA_DIR"] = data_dir
    env["AGENT_SI_SECRET_REF"] = _CANARY
    env.pop("AGENT_SI_WHEELS_DIR", None)
    env.pop("AGENT_SI_FRONTEND_TARBALL", None)
    if extra:
        env.update(extra)
    return env


def _run_boot(tmp_path, tag, extra=None):
    home = str(tmp_path / ("home-" + tag))
    os.makedirs(home, exist_ok=True)
    data_dir = str(tmp_path / ("data-" + tag))
    env = _base_env(home, data_dir, extra)
    proc = subprocess.run(
        [sys.executable, _START, "--smoke", "--tag", tag,
         "--data-dir", data_dir, "--env-example", _ENV_EXAMPLE],
        cwd=_ROOT, env=env, capture_output=True, text=True, timeout=280)
    return proc, data_dir


def _log_path_from_stdout(proc):
    for line in proc.stdout.splitlines():
        if line.startswith("startup_log="):
            return line[len("startup_log="):].strip()
    return None


def _read_log(data_dir):
    path = os.path.join(data_dir, "startup.log")
    assert os.path.isfile(path), f"no startup.log at {path}"
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    assert _CANARY not in text, "secret material leaked into startup.log"
    parsed = {}
    for line in text.splitlines():
        assert "=" in line, f"bad startup.log line: {line!r}"
        key, _, value = line.partition("=")
        parsed[key.strip()] = value
    return text, parsed


def _normalize(text, *paths):
    lines = [line for line in text.splitlines()
             if not line.startswith("timestamp=")]
    for path in sorted(set(paths), key=len, reverse=True):
        if path:
            lines = [line.replace(path, "<path>") for line in lines]
    lines = [re.sub(r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}\b",
                    "<time>", line) for line in lines]
    return "\n".join(lines) + "\n"


def _boot_ok(tmp_path, tag, extra=None):
    proc, data_dir = _run_boot(tmp_path, tag, extra)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    announced = _log_path_from_stdout(proc)
    assert announced, f"no startup_log= on stdout:\n{proc.stdout}"
    assert os.path.abspath(announced) == os.path.abspath(
        os.path.join(data_dir, "startup.log")), announced
    return proc, data_dir


def test_fxstart_boot_repeatable_and_lines(tmp_path):
    """3 boots (A, B, A again): same log minus timestamps/paths."""
    wheels = str(tmp_path / "wheels")
    _make_wheels(wheels)
    tarball = str(tmp_path / "frontend.tgz")
    _make_tarball(tarball)
    extra = {"AGENT_SI_WHEELS_DIR": wheels,
             "AGENT_SI_FRONTEND_TARBALL": tarball}
    _, data_a = _boot_ok(tmp_path, "fxstart-a", extra)
    _, data_b = _boot_ok(tmp_path, "fxstart-b", extra)
    _, data_a2 = _boot_ok(tmp_path, "fxstart-a", extra)
    assert data_a2 == data_a, (data_a2, data_a)
    text_a, log_a = _read_log(data_a)
    text_b, _ = _read_log(data_b)
    text_a2, _ = _read_log(data_a2)
    for key in REQUIRED_KEYS:
        assert key in log_a, (key, sorted(log_a))
    assert log_a["boot"] == "OK", log_a
    assert log_a["host"] == "127.0.0.1", log_a
    assert log_a["provider_ids"] == "", log_a
    assert log_a["providers_double"] == "", log_a
    for provider in ("meta", "openai", "groq"):
        assert provider in log_a["providers_absent"], log_a
    assert "fastapi==0.162.0" in log_a["backend_locked"], log_a
    assert "react==19.3.1" in log_a["frontend_locked"], log_a
    assert log_a["migration_level"] == "0", log_a
    assert log_a["health_self_check"].startswith("pass"), log_a
    assert "auditor provider" in log_a["host_blockers"], log_a
    assert "second real provider" in log_a["host_blockers"], log_a
    assert "missing local permission" not in log_a["host_blockers"], log_a
    norm_a = _normalize(text_a, data_a, data_b, wheels, tarball)
    norm_b = _normalize(text_b, data_a, data_b, wheels, tarball)
    norm_a2 = _normalize(text_a2, data_a, data_b, wheels, tarball)
    assert norm_a == norm_b, (norm_a, norm_b)
    assert norm_a == norm_a2, (norm_a, norm_a2)
    for key in ("product_version", "provider_ids", "providers_double",
                "providers_absent", "backend_locked", "frontend_locked",
                "migration_level", "health_self_check"):
        assert log_a[key] == _read_log(data_b)[1][key], key


def test_fxstart_missing_tarball_aborts(tmp_path):
    """Removed cached tarball: FAILED reason=missing-tarball, non-zero."""
    wheels = str(tmp_path / "wheels")
    _make_wheels(wheels)
    tarball = str(tmp_path / "frontend.tgz")
    _make_tarball(tarball)
    os.unlink(tarball)
    proc, data_dir = _run_boot(
        tmp_path, "fxstart-no-tar",
        {"AGENT_SI_WHEELS_DIR": wheels,
         "AGENT_SI_FRONTEND_TARBALL": tarball})
    assert proc.returncode != 0, proc.stdout + proc.stderr
    assert _log_path_from_stdout(proc), proc.stdout
    _, log = _read_log(data_dir)
    assert log["boot"].startswith("FAILED"), log
    assert "reason=missing-tarball" in log["boot"], log


def test_fxstart_absent_wheel_aborts(tmp_path):
    """Removed wheel: FAILED reason=absent-wheel, non-zero, no swap."""
    wheels = str(tmp_path / "wheels")
    _make_wheels(wheels)
    names = sorted(os.listdir(wheels))
    assert names, "no fixture wheels"
    os.unlink(os.path.join(wheels, names[0]))
    tarball = str(tmp_path / "frontend.tgz")
    _make_tarball(tarball)
    proc, data_dir = _run_boot(
        tmp_path, "fxstart-no-wheel",
        {"AGENT_SI_WHEELS_DIR": wheels,
         "AGENT_SI_FRONTEND_TARBALL": tarball})
    assert proc.returncode != 0, proc.stdout + proc.stderr
    _, log = _read_log(data_dir)
    assert log["boot"].startswith("FAILED"), log
    assert "reason=absent-wheel" in log["boot"], log


def _sitecustomize_blocking(non_loopback_dir):
    os.makedirs(non_loopback_dir, exist_ok=True)
    with open(os.path.join(non_loopback_dir, "sitecustomize.py"),
              "w", encoding="utf-8", newline="\n") as handle:
        handle.write(
            "import socket as _fx_socket\n"
            "_fx_orig_connect = _fx_socket.socket.connect\n"
            "def _fx_connect(self, address):\n"
            "    host = address[0] if isinstance(address, tuple) else address\n"
            "    if host not in ('127.0.0.1', 'localhost', '::1'):\n"
            "        raise OSError('fxstart offline: remote contact blocked')\n"
            "    return _fx_orig_connect(self, address)\n"
            "_fx_socket.socket.connect = _fx_connect\n")


def test_fxstart_offline_same_result(tmp_path):
    """Blocked sockets plus dead index env: same OK log, nothing remote."""
    wheels = str(tmp_path / "wheels")
    _make_wheels(wheels)
    tarball = str(tmp_path / "frontend.tgz")
    _make_tarball(tarball)
    extra = {"AGENT_SI_WHEELS_DIR": wheels,
             "AGENT_SI_FRONTEND_TARBALL": tarball}
    proc_plain, data_plain = _run_boot(tmp_path, "fxstart-plain", extra)
    assert proc_plain.returncode == 0, proc_plain.stdout + proc_plain.stderr
    shim = str(tmp_path / "shim")
    _sitecustomize_blocking(shim)
    offline = dict(extra)
    offline["PYTHONPATH"] = shim + os.pathsep + offline.get("PYTHONPATH", "")
    offline["PIP_INDEX_URL"] = "http://127.0.0.1:9/simple"
    offline["PIP_NO_INDEX"] = "1"
    offline["NPM_CONFIG_REGISTRY"] = "http://127.0.0.1:9/"
    proc_off, data_off = _run_boot(tmp_path, "fxstart-offline", offline)
    assert proc_off.returncode == 0, proc_off.stdout + proc_off.stderr
    text_plain, _ = _read_log(data_plain)
    text_off, log_off = _read_log(data_off)
    assert log_off["boot"] == "OK", log_off
    assert _normalize(text_plain, data_plain, data_off, wheels, tarball,
                      shim) == _normalize(text_off, data_plain, data_off,
                                         wheels, tarball, shim)
