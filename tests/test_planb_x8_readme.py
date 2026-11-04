"""PLANB X8: README Quick start is true on Windows PowerShell with the default
execution policy: npm.cmd (npm.ps1 is refused), and no separate uvicorn
install step because pyproject.toml declares it (found by DIRECTOR/RUN/PLANB_CLEAN.md).
"""

import os
import re

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(*parts):
    with open(os.path.join(_ROOT, *parts), encoding="utf-8") as handle:
        return handle.read()


def _powershell_blocks(text):
    return re.findall(r"```powershell\n(.*?)```", text, flags=re.S)


def test_readme_powershell_blocks_use_npm_cmd_not_bare_npm():
    blocks = _powershell_blocks(_read("README.md"))
    assert blocks
    joined = "\n".join(blocks)
    assert "npm.cmd --prefix frontend install" in joined
    assert "npm.cmd --prefix frontend " + "run build" in joined
    assert "npm.cmd --prefix frontend test" in joined
    for line in joined.splitlines():
        assert not re.match(r"^\s*npm\s", line), line
    assert "npm.ps1" in _read("README.md")


def test_no_separate_uvicorn_install_step_and_dependency_is_declared():
    for name in (("README.md",), ("docs", "TROUBLESHOOTING.md")):
        text = _read(*name)
        assert "pip install uvicorn" not in text
    assert "uvicorn==" in _read("pyproject.toml")
    assert "pip install -e ." in _read("README.md")


def test_troubleshooting_npm_lines_use_npm_cmd():
    text = _read("docs", "TROUBLESHOOTING.md")
    assert "npm.cmd --prefix frontend " + "run build" in text
    assert "`npm --prefix frontend" not in text
