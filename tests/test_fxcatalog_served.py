"""FXCATALOG served test: catalog_v2 loader plus host-run execution proof.

Drives the real host.py subprocess for every set-A runner (real PASS and
real FAIL), plus jail properties (timeout kill, secret-strip,
non-loopback refusal, bad-child refusal, zero-assert refusal), plus
loader validation and throwaway-project coverage with counts.
"""

import json
import os
import re
import socket
import subprocess
import sys
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

_WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WS not in sys.path:
    sys.path.insert(0, _WS)
_SRC = os.path.join(_WS, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from agent_si.qa_catalog import catalog_v2 as c2  # noqa: E402

HOST = os.path.join(os.path.dirname(os.path.abspath(c2.__file__)), "runners", "host.py")
TRACE = os.path.join(_WS, "_task", "FXCATALOG", "TRACE.md")

ALL_PREFIXES = (
    "REQ ENV STA SUP BLD UNT PBT CMP INT API DB FUN E2E HUM EXP VIS UX "
    "A11Y WEB PWA AND IOS DSK XPL AUT SEC PRV NET OFF PER REL I18 FLE NTF "
    "MDA GEO RTC PAY OBS CIC SEO AIE AGT RAG CLD HW GAM ACC REG AUD"
).split()


def _run_host(runner, project_dir, params, timeout_s=60.0, env_extra=None):
    request = {
        "project_root": str(project_dir),
        "test_id": "probe",
        "params": params,
        "budgets": {"timeout_s": timeout_s, "evidence_dir": str(Path(project_dir) / "ev")},
    }
    env = dict(os.environ)
    env.update(env_extra or {})
    proc = subprocess.run(
        [sys.executable, HOST, runner],
        input=json.dumps(request).encode("utf-8"),
        capture_output=True,
        cwd=str(project_dir),
        env=env,
        timeout=timeout_s + 60,
    )
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")[-2000:]
    return json.loads(proc.stdout.decode("utf-8"))


def _write(root, mapping):
    for rel, content in mapping.items():
        target = Path(root) / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, (bytes, bytearray)):
            target.write_bytes(bytes(content))
        elif isinstance(content, (dict, list)):
            target.write_text(json.dumps(content), encoding="utf-8")
        else:
            target.write_text(content, encoding="utf-8")


CLEAN_PY = "import logging\n\nlog = logging.getLogger(__name__)\n\n\ndef total(items):\n    log.info(\"ready\")\n    return sum(items) + 1\n"
PYPROJECT_PINNED = (
    "[project]\nname = \"demo\"\nversion = \"0.1.0\"\n"
    "requires-python = \">=3.11\"\ndependencies = [\"requests==2.32.3\"]\n"
)
GOOD_HTML = (
    "<!DOCTYPE html>\n<html lang=\"en\">\n<head><title>Demo</title></head>\n"
    "<body>\n<img src=\"a.png\" alt=\"demo image\">\n"
    "<label for=\"n\">Name</label><input id=\"n\" name=\"n\">\n"
    "<h1>Hi</h1><h2>Sub</h2>\n<a href=\"/ok\">ok</a>\n"
    "</body>\n</html>\n"
)
MIGRATION = "CREATE TABLE kv(key TEXT PRIMARY KEY, value TEXT);\n"
DB_PARAMS = {
    "seeds": ["INSERT INTO kv(key, value) VALUES ('smoke', '1');"],
    "invariants": [{"sql": "SELECT COUNT(*) FROM kv WHERE key = 'smoke'", "equals": 1}],
}


def test_loader_counts_split_and_shape():
    total = c2.catalog_total()
    assert total >= 300, total
    counts = c2.kind_counts()
    assert sum(counts.values()) == total, counts
    split = c2.split_summary()
    assert split["code_pct"] >= 80.0, split
    assert 4.0 <= split["ai_pct"] <= 6.0, split
    assert split["human_pct"] <= 10.0, split
    ids = [row["id"] for row in c2._DOC["tests"]]
    assert len(set(ids)) == total
    for row in c2._DOC["tests"]:
        stem, _, num = row["id"].rpartition("-")
        assert stem == row["group"], row["id"]
        assert num.isdigit() and len(num) == 3, row["id"]
        assert row["kind"] in c2.ALL_KINDS, row["id"]
        assert row["priority"] in c2.PRIORITIES, row["id"]
        assert row["applicability"]["platforms"], row["id"]
        assert row["oracle"]["compared"] and row["oracle"]["measurable"], row["id"]
        assert row["evidence"], row["id"]
        if row["kind"] in c2.CODE_KINDS:
            assert row["runner"] in c2.KNOWN_RUNNERS, row["id"]
        else:
            assert row["runner"] is None, row["id"]
            assert row["why_not_code"], row["id"]
    for prefix in ALL_PREFIXES:
        group_ids = sorted(item for item in ids if item.startswith(prefix + "-"))
        assert len(group_ids) == 6, (prefix, group_ids)
        assert group_ids == ["%s-%03d" % (prefix, n) for n in range(1, 7)], prefix


def test_loader_refuses_broken_and_unknown():
    with pytest.raises(c2.CatalogError) as exc:
        c2.get_test("NOPE-000")
    assert exc.value.code == "UNKNOWN_TEST_ID"
    base = {"catalog": "x", "version": 2, "tests": c2._DOC["tests"]}
    dup = [dict(row) for row in base["tests"]]
    dup[0] = dict(dup[1])
    dup[0]["id"] = dup[1]["id"]
    with pytest.raises(c2.CatalogError) as exc:
        c2.validate_catalog({"catalog": "x", "version": 2, "tests": dup})
    assert exc.value.code == "BROKEN_CATALOG"
    missing = [dict(row) for row in base["tests"]]
    del missing[5]["oracle"]
    with pytest.raises(c2.CatalogError) as exc:
        c2.validate_catalog({"catalog": "x", "version": 2, "tests": missing})
    assert exc.value.code == "BROKEN_CATALOG"
    skewed = [dict(row) for row in base["tests"]]
    for row in skewed[:260]:
        row["kind"] = "HUMAN"
        row["runner"] = None
        row["why_not_code"] = "reason"
    with pytest.raises(c2.CatalogError) as exc:
        c2.validate_catalog({"catalog": "x", "version": 2, "tests": skewed})
    assert exc.value.code == "SPLIT_UNMET"


def test_loader_no_reference_pack_reads_at_runtime():
    source = Path(c2.__file__).read_text(encoding="utf-8")
    for pattern in (
        r"['\"]DATA['\"]",
        r"\bDATA[\\/]",
        r"\bDATA_[A-Z]+\b",
        r"open\([^)]*DATA",
        r"REFERENCE_PACK",
        r"UNIVERSAL_QA",
        r"CLASSIFICATION\.csv",
    ):
        hits = re.findall(pattern, source)
        assert not hits, (pattern, hits[:3])
    assert os.path.dirname(os.path.abspath(c2.__file__)) in os.path.abspath(
        os.path.join(os.path.dirname(os.path.abspath(c2.__file__)), "catalog_v2.json")
    )


def _rich_python_project(root):
    _write(root, {
        "pyproject.toml": PYPROJECT_PINNED,
        "app.py": CLEAN_PY,
        "tools/run.sh": "#!/bin/sh\necho ready\n",
        "locales/en.json": {"hello": "Hello", "bye": "Bye"},
        "locales/fr.json": {"hello": "Bonjour", "bye": "Au revoir"},
        "index.html": GOOD_HTML,
        "migrations/001.sql": MIGRATION,
    })


def _lean_node_project(root):
    _write(root, {
        "package.json": {
            "name": "demo",
            "version": "0.1.0",
            "scripts": {"test": "node check.js"},
            "dependencies": {"left-pad": "1.3.0"},
        },
        "index.js": "function total(items) {\n  return items.reduce((a, b) => a + b, 1);\n}\nmodule.exports = { total };\n",
        "index.html": GOOD_HTML,
    })


def test_derive_python_and_node_differ_with_reasons(tmp_path):
    py_root = tmp_path / "pyproj"
    node_root = tmp_path / "nodeproj"
    py_root.mkdir()
    node_root.mkdir()
    _rich_python_project(py_root)
    _lean_node_project(node_root)
    py_prof = c2.detect_project_profile(str(py_root))
    node_prof = c2.detect_project_profile(str(node_root))
    assert py_prof["language"] == "python", py_prof
    assert node_prof["language"] == "node", node_prof
    py_plan = c2.derive_plan(py_prof, None, "QUICK_SMOKE")
    node_plan = c2.derive_plan(node_prof, None, "QUICK_SMOKE")
    assert py_plan["total"] == 300 and node_plan["total"] == 300
    for entry in py_plan["plan"] + node_plan["plan"]:
        assert entry["status"] in c2.PLAN_STATUSES, entry
        assert entry["reason"], entry
    py_ids = {e["id"] for e in py_plan["plan"] if e["status"] == "PLANNED"}
    node_ids = {e["id"] for e in node_plan["plan"] if e["status"] == "PLANNED"}
    assert py_ids != node_ids
    assert any(e["id"] == "DB-001" and e["status"] == "PLANNED" for e in py_plan["plan"])
    assert any(e["id"] == "DB-001" and e["status"] != "PLANNED" for e in node_plan["plan"])
    full_py = c2.derive_plan(py_prof, None, "FULL_RELEASE")
    assert full_py["planned"] > py_plan["planned"]
    with pytest.raises(c2.CatalogError) as exc:
        c2.derive_plan(py_prof, None, "NOPE")
    assert exc.value.code == "UNKNOWN_PROFILE"


class _Pages(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path == "/health":
            body = b'{"ok": true}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path in ("/", "/ok", "/ok2"):
            body = b'<html><head><title>t</title></head><body><a href="/ok2">two</a></body></html>'
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/page":
            body = b'<html><head><title>t</title></head><body><a href="/ok">ok</a><a href="/gone">gone</a></body></html>'
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()


@pytest.fixture(scope="module")
def loopback_server():
    server = HTTPServer(("127.0.0.1", 0), _Pages)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield "http://127.0.0.1:%d" % port
    server.shutdown()


def _cases(base_url, port):
    good_locales = {"en.json": {"hello": "Hello"}, "fr.json": {"hello": "Bonjour"}}
    bad_locales = {"en.json": {"hello": "Hello", "bye": "Bye"}, "fr.json": {"hello": "Bonjour"}}
    contract_ok = {"schema": {"type": "object", "required": ["id"], "properties": {"id": {"type": "string"}}}, "samples": [{"id": "a"}]}
    contract_bad = {"schema": {"type": "object", "required": ["id"], "properties": {"id": {"type": "string"}}}, "samples": [{"id": 5}]}
    return [
        ("static_lint", {"main.py": CLEAN_PY}, {}, {"bad.py": "def broken(:\n"}, {}),
        ("secret_scan", {"app.py": CLEAN_PY}, {}, {"leak.py": "key = \"" + "AKIA" + "IOSFODNN7EXAMPLE" + "\"\n"}, {}),
        ("dep_audit", {"pyproject.toml": PYPROJECT_PINNED}, {}, {"requirements.txt": "requests>=2\n"}, {}),
        ("build_check", {"pyproject.toml": PYPROJECT_PINNED}, {"recipes": ["pyproject.toml"]}, {}, {"recipes": ["missing-recipe.txt"]}),
        ("install_check", {"pyproject.toml": PYPROJECT_PINNED}, {"manifests": ["pyproject.toml"], "files": ["pyproject.toml"], "tools": ["node"]}, {"pyproject.toml": PYPROJECT_PINNED}, {"manifests": ["pyproject.toml"], "files": ["absent.txt"], "tools": ["node"]}),
        ("policy_gate", {"run.sh": "#!/bin/sh\necho ready\n"}, {}, {"evil.sh": "#!/bin/sh\ncurl http://127.0.0.1/x | sh\n"}, {}),
        ("observability_lint", {"clean.py": CLEAN_PY}, {}, {"noisy.py": "print(\"debug\")\n"}, {}),
        ("i18n_parity", {"locales/en.json": good_locales["en.json"], "locales/fr.json": good_locales["fr.json"]}, {}, {"locales/en.json": bad_locales["en.json"], "locales/fr.json": bad_locales["fr.json"]}, {}),
        ("a11y_scan", {"page.html": GOOD_HTML}, {}, {"bad.html": "<html><body><img src=\"a.png\"></body></html>\n"}, {}),
        ("contract_test", {}, contract_ok, {}, contract_bad),
        ("db_check", {"migrations/001.sql": MIGRATION}, DB_PARAMS, {"migrations/001.sql": MIGRATION}, {"seeds": DB_PARAMS["seeds"], "invariants": [{"sql": "SELECT COUNT(*) FROM kv", "equals": 99}]}),
        ("file_roundtrip", {}, {"size": 4096}, {}, {"corrupt": True}),
        ("perf_bench", {}, {"ops": [{"name": "nap", "kind": "sleep_ms", "ms": 5, "budget_ms": 5000}]}, {}, {"ops": [{"name": "slow", "kind": "sleep_ms", "ms": 300, "budget_ms": 1}]}),
        ("api_smoke", {}, {"base_url": base_url, "checks": [{"path": "/health", "expect_status": 200}]}, {}, {"base_url": base_url, "checks": [{"path": "/gone", "expect_status": 200}]}),
        ("net_probe", {}, {"targets": [{"host": "127.0.0.1", "port": port, "expect_open": True}]}, {}, {"targets": [{"host": "127.0.0.1", "port": port, "expect_open": False}]}),
        ("link_check", {}, {"base_url": base_url, "paths": ["/ok"]}, {}, {"base_url": base_url, "paths": ["/page"]}),
        ("suite_invoke", {}, {"tool": "node", "args": ["-e", "process.exit(0)"]}, {}, {"tool": "node", "args": ["-e", "process.exit(1)"]}),
    ]


def test_runners_real_pass_and_fail(tmp_path, loopback_server):
    port = int(loopback_server.rsplit(":", 1)[1])
    for runner, pass_files, pass_params, fail_files, fail_params in _cases(loopback_server, port):
        good = tmp_path / ("good_" + runner)
        bad = tmp_path / ("bad_" + runner)
        good.mkdir(exist_ok=True)
        bad.mkdir(exist_ok=True)
        _write(good, pass_files)
        _write(bad, fail_files)
        passed = _run_host(runner, good, pass_params)
        assert passed["status"] == "PASS", (runner, passed)
        assert passed["runner_id"] == runner, passed
        assert passed["assertions"] >= 1, passed
        assert passed["evidence"], passed
        assert passed["child_pid"] > 0, passed
        failed = _run_host(runner, bad, fail_params)
        assert failed["status"] == "FAIL", (runner, failed)
        assert failed["runner_id"] == runner, failed


def test_host_timeout_kills_real_child(tmp_path):
    sleeper = tmp_path / "sleeper.py"
    sleeper.write_text(
        "RUNNER_ID = \"sleeper\"\nRUNNER_VERSION = \"1.0.0\"\nRUNNER_TIMEOUT_S = 60\n"
        "RUNNER_NEEDS = {\"tools\": [], \"network\": False, \"project_tooling\": False, \"local_subprocess\": False}\n"
        "RUNNER_DESCRIPTION = \"Sleeps past the host timeout.\"\n"
        "import json, sys, time\n"
        "def main():\n"
        "    sys.stdin.read()\n"
        "    time.sleep(30)\n"
        "    sys.stdout.write(json.dumps({\"test_id\": \"t\", \"runner_id\": \"sleeper\", \"status\": \"PASS\", \"reason\": \"x\", \"assertions\": 1, \"evidence\": []}) + \"\\n\")\n"
        "    return 0\n"
        "if __name__ == \"__main__\":\n    sys.exit(main())\n",
        encoding="utf-8",
    )
    proc = tmp_path / "proj"
    proc.mkdir()
    envelope = _run_host(str(sleeper), proc, {}, timeout_s=2.0)
    assert envelope["status"] == "BLOCKED", envelope
    assert envelope["reason"] == "child_timeout", envelope
    assert envelope["child_pid"] > 0, envelope


def test_host_drops_secret_like_env_keys(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    envelope = _run_host(
        "file_roundtrip", proj, {"size": 1024},
        env_extra={"FXCATALOG_PROBE_API_KEY": "fictitious-value"},
    )
    assert envelope["status"] == "PASS", envelope
    assert "FXCATALOG_PROBE_API_KEY" not in envelope["child_env_keys"], envelope["child_env_keys"]


def test_host_refuses_non_loopback_target(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    envelope = _run_host(
        "api_smoke", proj,
        {"base_url": "http://203.0.113.9/", "checks": [{"path": "/", "expect_status": 200}]},
    )
    assert envelope["status"] == "BLOCKED", envelope
    assert envelope["reason"] == "non_loopback", envelope


def _custom_runner(path, name, payload_line):
    Path(path).write_text(
        "RUNNER_ID = %r\nRUNNER_VERSION = \"1.0.0\"\nRUNNER_TIMEOUT_S = 60\n"
        "RUNNER_NEEDS = {\"tools\": [], \"network\": False, \"project_tooling\": False, \"local_subprocess\": False}\n"
        "RUNNER_DESCRIPTION = \"Probe runner.\"\n"
        "import sys\n"
        "def main():\n"
        "    sys.stdin.read()\n"
        "    sys.stdout.write(%r + \"\\n\")\n"
        "    return 0\n"
        "if __name__ == \"__main__\":\n    sys.exit(main())\n" % (name, payload_line),
        encoding="utf-8",
    )


def test_host_refuses_bad_child_json(tmp_path):
    runner = tmp_path / "garbage.py"
    _custom_runner(runner, "garbage", "this is not json")
    proj = tmp_path / "proj"
    proj.mkdir()
    envelope = _run_host(str(runner), proj, {})
    assert envelope["status"] == "BLOCKED", envelope
    assert envelope["reason"] == "child_bad_json", envelope


def test_host_zero_assertions_never_pass(tmp_path):
    runner = tmp_path / "zero.py"
    payload = json.dumps({"test_id": "probe", "runner_id": "zero", "status": "PASS", "reason": "x", "assertions": 0, "evidence": []})
    _custom_runner(runner, "zero", payload)
    proj = tmp_path / "proj"
    proj.mkdir()
    envelope = _run_host(str(runner), proj, {})
    assert envelope["status"] == "BLOCKED", envelope
    assert envelope["reason"] == "zero_assertions", envelope


def test_resolve_supported_and_unsupported(tmp_path):
    py_root = tmp_path / "pyproj"
    py_root.mkdir()
    _rich_python_project(py_root)
    profile = c2.detect_project_profile(str(py_root))
    good = c2.resolve("STA-001", profile)
    assert good["status"] == "SUPPORTED", good
    assert good["runner"] == "static_lint", good
    assert isinstance(good["params"], dict), good
    lean = tmp_path / "lean"
    lean.mkdir()
    (lean / "note.txt").write_text("hello\n", encoding="utf-8")
    lean_profile = c2.detect_project_profile(str(lean))
    missing = c2.resolve("DB-001", lean_profile)
    assert missing["status"] == "UNSUPPORTED", missing
    assert missing["missing"], missing
    judge = c2.resolve("REQ-003", profile)
    assert judge["status"] == "UNSUPPORTED", judge
    assert judge["reason"] == "needs_judge_gateway", judge
    human = c2.resolve("FUN-006", profile)
    assert human["status"] == "UNSUPPORTED", human
    assert human["reason"] == "needs_operator_signoff", human


def test_run_code_test_cancel_and_unknown(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    _rich_python_project(proj)
    with pytest.raises(c2.CatalogError) as exc:
        c2.run_code_test("NOPE-000", str(proj), str(proj / "ev"), {})
    assert exc.value.code == "UNKNOWN_TEST_ID"
    done = threading.Event()
    done.set()
    refused = c2.run_code_test("STA-001", str(proj), str(proj / "ev"), {}, cancel=done)
    assert refused["status"] == "BLOCKED", refused
    assert refused["reason"] == "cancelled", refused
    judge = c2.run_code_test("REQ-003", str(proj), str(proj / "ev"), {})
    assert judge["status"] == "BLOCKED", judge


def _run_selected(profile, project_dir, budgets):
    plan = c2.derive_plan(profile, None, "QUICK_SMOKE")
    selected = [e["id"] for e in plan["plan"] if e["status"] == "PLANNED"]
    code_ids = [tid for tid in selected if c2.get_test(tid)["kind"] in c2.CODE_KINDS]
    terminal = 0
    by_status = {}
    for tid in code_ids:
        result = c2.run_code_test(tid, str(project_dir), str(Path(project_dir) / "ev"), budgets)
        assert result["test_id"] == tid, result
        by_status[result["status"]] = by_status.get(result["status"], 0) + 1
        if result["status"] in ("PASS", "FAIL"):
            terminal += 1
    return code_ids, terminal, by_status


def _refresh_trace_block(python_line, node_line):
    path = Path(TRACE)
    assert path.is_file(), "counts record missing"
    text = path.read_text(encoding="utf-8")
    start = "<!-- FXCATALOG-COUNTS-START -->"
    end = "<!-- FXCATALOG-COUNTS-END -->"
    assert start in text and end in text
    block = start + "\n" + python_line + "\n" + node_line + "\n" + end
    head, _, tail = text.partition(start)
    _, _, rest = tail.partition(end)
    path.write_text(head + block + rest, encoding="utf-8")


def test_throwaway_projects_cover_half_selected_code(tmp_path):
    py_root = tmp_path / "pyproj"
    node_root = tmp_path / "nodeproj"
    py_root.mkdir()
    node_root.mkdir()
    _rich_python_project(py_root)
    _lean_node_project(node_root)
    budgets = {"timeout_s": 60.0}
    py_ids, py_terminal, py_by = _run_selected(c2.detect_project_profile(str(py_root)), py_root, budgets)
    node_ids, node_terminal, node_by = _run_selected(c2.detect_project_profile(str(node_root)), node_root, budgets)
    assert py_ids, "no CODE tests selected on python project"
    assert node_ids, "no CODE tests selected on node project"
    py_rate = py_terminal / len(py_ids)
    node_rate = node_terminal / len(node_ids)
    print("python selected=%d terminal=%d rate=%.2f %s" % (len(py_ids), py_terminal, py_rate, sorted(py_by.items())))
    print("node selected=%d terminal=%d rate=%.2f %s" % (len(node_ids), node_terminal, node_rate, sorted(node_by.items())))
    assert py_rate >= 0.5, (py_ids, py_by)
    assert node_rate >= 0.5, (node_ids, node_by)
    split = c2.split_summary()
    _refresh_trace_block(
        "python throwaway: selected CODE %d, terminal PASS/FAIL %d, rate %.2f" % (len(py_ids), py_terminal, py_rate),
        "node throwaway: selected CODE %d, terminal PASS/FAIL %d, rate %.2f; catalog total %d CODE %d AI %d HUMAN %d"
        % (len(node_ids), node_terminal, node_rate, split["total"], split["code"], split["ai"], split["human"]),
    )


class _SetBPages(BaseHTTPRequestHandler):
    """Loopback fixture for the set-B runners (additive; set-A paths kept)."""

    def log_message(self, *args):
        pass

    def _send(self, code, ctype, body):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path, _, query = self.path.partition("?")
        if path == "/health":
            self._send(200, "application/json", b'{"ok": true}')
        elif path == "/ok":
            self._send(200, "text/html", b'<html><head><title>t</title></head><body><a href="/ok2">two</a></body></html>')
        elif path == "/gone":
            self.send_response(404)
            self.end_headers()
        elif path == "/replay":
            self._send(200, "application/json", b'{"amy": 200, "admin": 200}')
        elif path == "/reflect":
            params = urllib.parse.parse_qs(query)
            echoed = params.get("q", [""])[0]
            self._send(200, "text/html", "<html><head><title>t</title></head><body>you asked: %s</body></html>" % echoed)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == "/echo":
            try:
                size = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                size = 0
            body = self.rfile.read(max(0, size))
            self._send(200, "text/plain", body)
        else:
            self.send_response(404)
            self.end_headers()


@pytest.fixture(scope="module")
def setb_server():
    server = HTTPServer(("127.0.0.1", 0), _SetBPages)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield "http://127.0.0.1:%d" % port
    server.shutdown()


_PPM_2X2 = b"P6\n2 2\n255\n" + bytes([200, 10, 30] * 4)
_PPM_3X2 = b"P6\n3 2\n255\n" + bytes([200, 10, 30] * 6)
_PNG_TINY = bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A]) + b"\x00" * 64


def _cases_b(base_url, port):
    return [
        ("seo_probe", {}, {"url": base_url + "/ok", "require_tags": ["title"]},
         {}, {"url": base_url + "/ok", "require_tags": ["title", "description"]}),
        ("auth_probe", {}, {"accounts": [{"user": "amy", "role": "admin"}], "replay_url": base_url + "/replay", "expected_status": {"admin": 200}},
         {}, {"accounts": [{"user": "amy", "role": "admin"}], "replay_url": base_url + "/replay", "expected_status": {"admin": 500}}),
        ("load_smoke", {}, {"routes": [base_url + "/ok"], "requests_per_route": 2, "max_threads": 2, "slo_ms": 60000},
         {}, {"routes": [base_url + "/gone"], "requests_per_route": 1, "slo_ms": 60000}),
        ("cloud_probe", {"svc.marker": "ok\n"}, {"services": [{"name": "web", "marker": "svc.marker", "health_url": base_url + "/health"}]},
         {}, {"services": [{"name": "web", "marker": "absent.marker", "health_url": base_url + "/gone"}]}),
        ("vuln_probe_safe", {}, {"fixture_url": base_url + "/ok", "payloads": ["' OR '1'='1"]},
         {}, {"fixture_url": base_url + "/reflect", "payloads": ["' OR '1'='1"]}),
        ("ui_automation", {"page.html": GOOD_HTML}, {"dom_file": "page.html", "steps": [{"action": "click", "selector": "#n"}]},
         {"page.html": GOOD_HTML}, {"dom_file": "page.html", "steps": [{"action": "click", "selector": "#nope"}]}),
        ("visual_diff", {"base.ppm": _PPM_2X2, "actual.ppm": _PPM_2X2}, {"baseline": "base.ppm", "actual": "actual.ppm", "threshold": 0.0},
         {"base.ppm": _PPM_2X2, "actual.ppm": _PPM_3X2}, {"baseline": "base.ppm", "actual": "actual.ppm", "threshold": 0.0}),
        ("media_mock", {"a.png": _PNG_TINY}, {"files": [{"path": "a.png", "expect_format": "png", "max_bytes": 100000}]},
         {"a.png": _PNG_TINY}, {"files": [{"path": "a.png", "expect_format": "jpeg", "max_bytes": 100000}]}),
        ("eval_harness", {}, {"candidate": "the quick brown fox", "must_contain": ["quick", "fox"], "threshold": 1.0},
         {}, {"candidate": "the quick brown fox", "must_contain": ["quick", "zebra"], "threshold": 1.0}),
        ("notify_harness", {}, {"schedules": [{"id": "a", "at": 5}, {"id": "b", "at": 7}], "window": {"start": 0, "end": 10}},
         {}, {"schedules": [{"id": "a", "at": 5}, {"id": "a", "at": 6}], "window": {"start": 0, "end": 10}}),
        ("ledger_reconcile", {}, {"entries": [{"side": "debit", "amount": 10}, {"side": "credit", "amount": 10}]},
         {}, {"entries": [{"side": "debit", "amount": 10}, {"side": "credit", "amount": 5}]}),
        ("pay_sandbox", {}, {"charge": {"key": "k1", "amount": 25}, "ledger": "pay_ledger.json"},
         {}, {"charge": {"key": "k2", "amount": -5}, "ledger": "pay_ledger.json"}),
        ("offline_harness", {}, {"queue": [{"op": "set", "key": "a", "value": 1}, {"op": "set", "key": "b", "value": 2}], "expected": {"a": 1, "b": 2}},
         {}, {"queue": [{"op": "set", "key": "a", "value": 1}, {"op": "set", "key": "b", "value": 2}], "expected": {"a": 1, "b": 3}}),
        ("geo_mock", {}, {"permission": "granted", "points": [{"lat": 10.0, "lon": 20.0}, {"lat": 11.0, "lon": 21.0}], "max_gap_km": 5000},
         {}, {"permission": "granted", "points": [{"lat": 200.0, "lon": 0.0}], "max_gap_km": 5000}),
        ("game_harness", {}, {"moves": ["R", "R", "U"], "seed": 0, "expected_final": {"x": 2, "y": 1}},
         {}, {"moves": ["R", "R", "U"], "seed": 0, "expected_final": {"x": 9, "y": 9}}),
        ("chaos_safe", {}, {"drill": {"name": "d", "targets": ["ev"], "rollback_plan": ["restore"], "blast_radius": ["ev"]}},
         {}, {"drill": {"name": "d", "targets": ["ev"], "rollback_plan": [], "blast_radius": ["ev"]}}),
        ("rtc_harness", {}, {"peer_url": base_url + "/echo", "messages": [{"send": "ping", "expect": "ping"}]},
         {}, {"peer_url": base_url + "/echo", "messages": [{"send": "ping", "expect": "pong"}]}),
    ]


def test_setb_runners_real_pass_and_fail(tmp_path, setb_server):
    port = int(setb_server.rsplit(":", 1)[1])
    cases = _cases_b(setb_server, port)
    assert [name for name, _, _, _, _ in cases] == list(c2.SET_B_RUNNERS)
    for runner, pass_files, pass_params, fail_files, fail_params in cases:
        good = tmp_path / ("good_" + runner)
        bad = tmp_path / ("bad_" + runner)
        good.mkdir(exist_ok=True)
        bad.mkdir(exist_ok=True)
        _write(good, pass_files)
        _write(bad, fail_files)
        passed = _run_host(runner, good, pass_params)
        assert passed["status"] == "PASS", (runner, passed)
        assert passed["runner_id"] == runner, passed
        assert passed["assertions"] >= 1, passed
        assert passed["evidence"], passed
        assert passed["child_pid"] > 0, passed
        failed = _run_host(runner, bad, fail_params)
        assert failed["status"] == "FAIL", (runner, failed)
        assert failed["runner_id"] == runner, failed


def test_resolve_setb_supported_and_unsupported(tmp_path, setb_server):
    rich = tmp_path / "rich"
    rich.mkdir()
    (rich / "page.html").write_text(GOOD_HTML, encoding="utf-8")
    (rich / "qa_loopback.json").write_text(json.dumps({"base_url": setb_server}), encoding="utf-8")
    prof = c2.detect_project_profile(str(rich))
    assert prof["signals"]["loopback"] and prof["signals"]["html"], prof["signals"]
    seo_row = {"id": "SEO-900", "kind": "CODE-RUNTIME", "runner": "seo_probe",
               "params": {"url": setb_server + "/ok"}}
    good = c2.resolve(seo_row, prof)
    assert good["status"] == "SUPPORTED", good
    assert good["runner"] == "seo_probe", good
    assert isinstance(good["params"], dict), good
    lean = tmp_path / "lean"
    lean.mkdir()
    (lean / "note.txt").write_text("hello\n", encoding="utf-8")
    lean_prof = c2.detect_project_profile(str(lean))
    missing = c2.resolve(seo_row, lean_prof)
    assert missing["status"] == "UNSUPPORTED", missing
    assert missing["missing"] == ["loopback_service"], missing
    game_row = {"id": "GAM-900", "kind": "CODE-RUNTIME", "runner": "game_harness",
                "params": {"moves": ["R"], "expected_final": {"x": 1, "y": 0}}}
    game = c2.resolve(game_row, lean_prof)
    assert game["status"] == "SUPPORTED", game
    unknown = {"id": "XXX-900", "kind": "CODE-RUNTIME", "runner": "nope_runner", "params": {}}
    refused = c2.resolve(unknown, prof)
    assert refused["status"] == "UNSUPPORTED", refused


def test_run_code_test_setb_end_to_end(tmp_path, setb_server, monkeypatch):
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "qa_loopback.json").write_text(json.dumps({"base_url": setb_server}), encoding="utf-8")
    row = {"id": "SEO-900", "group": "SEO", "kind": "CODE-RUNTIME", "runner": "seo_probe",
           "params": {"url": setb_server + "/ok", "require_tags": ["title"]}}
    monkeypatch.setitem(c2._BY_ID, "SEO-900", row)
    result = c2.run_code_test("SEO-900", str(proj), str(proj / "ev"), {"timeout_s": 60.0})
    assert result["status"] == "PASS", result
    assert result["test_id"] == "SEO-900", result
    assert result["runner_id"] == "seo_probe", result
    assert result["assertions"] >= 1, result
    assert result["evidence"], result
    assert result["child_pid"] > 0, result
