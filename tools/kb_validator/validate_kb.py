"""K09-B KB validator CLI.

Calls tools.kb_validator.iface.validate_kb_dir only. Exit 0 when the KB dir
is accepted, exit 1 when it is rejected (or the usage is wrong). Prints the
kb dir plus OK, or the kb dir plus the error code.
"""

from __future__ import annotations

import os
import sys
from typing import List, Optional

try:
    from tools.kb_validator.iface import validate_kb_dir
except ImportError:
    sys.path.insert(
        0,
        os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        ),
    )
    from tools.kb_validator.iface import validate_kb_dir


def main(argv: Optional[List[str]] = None) -> int:
    args = sys.argv[1:] if argv is None else list(argv)
    if len(args) != 1:
        print("usage: validate_kb.py <kb_dir>", file=sys.stderr)
        return 1
    result = validate_kb_dir(args[0])
    if result.ok:
        print("%s OK" % result.kb_dir)
        return 0
    print("%s %s" % (result.kb_dir, result.error_code))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
