# U6 locale parity sweep: en leaf set == uk leaf set == LocaleKey union,
# minus the committed allowlist. Run from frontend/: python localeparity.py
# Exit 0 when clean; exit 1 listing every drifted key otherwise.
import json
import re
import sys
from pathlib import Path

HERE = Path.cwd()
EN = HERE / "src" / "locale" / "en.json"
UK = HERE / "src" / "locale" / "uk.json"
DTS = HERE / "src" / "settings" / "k07b-iface.d.ts"
ALLOWLIST = HERE / "src" / "locale" / "parity-allowlist.json"


def leaves(node, prefix=""):
    out = set()
    if isinstance(node, dict):
        for key, value in node.items():
            out |= leaves(value, f"{prefix}.{key}" if prefix else key)
    else:
        out.add(prefix)
    return out


def main():
    en = leaves(json.loads(EN.read_text(encoding="utf-8")))
    uk = leaves(json.loads(UK.read_text(encoding="utf-8")))
    text = DTS.read_text(encoding="utf-8")
    start = text.find("export type LocaleKey =")
    union = set(re.findall(r"'([^']+)'", text[start:text.find(";", start)])) if start >= 0 else set()
    allowed = set(json.loads(ALLOWLIST.read_text(encoding="utf-8"))) if ALLOWLIST.exists() else set()
    raw_drift = (en ^ uk) | ((en | uk) ^ union)
    drift = sorted(raw_drift - allowed)
    stale = sorted(allowed - raw_drift)
    for key in drift:
        where = []
        if (key in en) != (key in uk):
            where.append("en-uk")
        if (key in union) != (key in en or key in uk):
            where.append("union")
        print("DRIFT " + key + " [" + ",".join(where) + "]")
    for key in stale:
        print("STALE-ALLOWLIST " + key)
    if drift or stale:
        print("parity: FAIL (" + str(len(drift)) + " drifted, " + str(len(stale)) + " stale)")
        return 1
    print("parity: OK (en=" + str(len(en)) + " uk=" + str(len(uk)) + " union=" + str(len(union)) + " allowed=" + str(len(allowed)) + ")")
    return 0


if __name__ == "__main__":
    sys.exit(main())
