"""M-P4-143 competitor CLI entry.

Run as ``python -m tools.competitor audit <input>`` from the repo root, or
as ``python tools/competitor/__main__.py audit <input>``. Both spellings
reach the same CLI. Stdlib only.
"""

from __future__ import annotations

import os
import sys

try:
    from tools.competitor.cli import main
except ImportError:
    sys.path.insert(
        0,
        os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        ),
    )
    from tools.competitor.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
