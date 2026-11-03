"""FXBUILDRACE tripwire: every dist-building test must delegate to the
shared file-locked helper (tests/_distbuild.py). The gate pool runs one
test file per process; a direct vite build into frontend/dist from any
file reintroduces the emptyDir/prepareOutDir race. Pure source scan:
no build, no browser, milliseconds.
"""
import os

WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS = os.path.join(WS, "tests")

FORBIDDEN = (
    "--prefix frontend run build",
    '"vite.js"',
    "--outDir",
    "emptyOutDir",
)

SELF = os.path.basename(__file__)


def test_no_direct_dist_build():
    offenders = []
    for name in sorted(os.listdir(TESTS)):
        if not (name.startswith("test_") and name.endswith(".py")):
            continue
        if name == SELF:
            continue
        path = os.path.join(TESTS, name)
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        hits = [pat for pat in FORBIDDEN if pat in src]
        if hits:
            offenders.append("%s: %s" % (name, ", ".join(hits)))
    assert not offenders, (
        "direct dist build outside tests/_distbuild.py: %s "
        "(delegate to tests._distbuild.build_once)" % "; ".join(offenders))
