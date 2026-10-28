"""Run-lane standard cleanup script: disk check plus own-temp cleanup.

Removal stays strictly inside one run's own temp folder under a base
folder: a run id that would escape the base is refused, and nothing outside
the base is ever removed. The disk state (free/total/ok) of the base is
reported with every receipt. Standard library only.

Usable as a module or as a script::

    python -m agent_si.automation.cleanup --base <dir> --run <run-id>
"""

import json
import os
import shutil
import sys

#: Environment override for the run-temp base folder.
BASE_ENV_VAR = "AGENT_SI_RUN_TEMP"

#: Platform temp variables consulted when the override is absent.
_FALLBACK_ENV_VARS = ("TEMP", "TMP", "TMPDIR")


def resolve_base(explicit=None):
    """Return the run-temp base folder without creating anything.

    The explicit folder wins, then the AGENT_SI_RUN_TEMP override, then
    the platform temp variables, then a portable folder under the home
    folder. No folder is created here; disk_check creates the base when
    it reports on it.
    """
    candidates = []
    if explicit:
        candidates.append(explicit)
    candidates.append(os.environ.get(BASE_ENV_VAR, ""))
    for name in _FALLBACK_ENV_VARS:
        candidates.append(os.environ.get(name, ""))
    candidates.append(
        os.path.join(os.path.expanduser("~"), ".agent_si", "run_temp")
    )
    for candidate in candidates:
        if candidate:
            return os.path.abspath(candidate)
    return os.path.abspath(
        os.path.join(os.path.expanduser("~"), ".agent_si", "run_temp")
    )


def _check_run_id(run_id):
    """Refuse run ids that could escape the base folder."""
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("run id must be a non-empty string")
    if run_id in (".", ".."):
        raise ValueError("run id stays inside the base: %r" % (run_id,))
    if os.path.isabs(run_id):
        raise ValueError("run id stays inside the base: %r" % (run_id,))
    for bad in ("/", "\\", ":", "\x00"):
        if bad in run_id:
            raise ValueError("run id stays inside the base: %r" % (run_id,))
    return run_id


def run_dir_for(base, run_id):
    """Return the run's own temp folder, refusing ids outside the base."""
    _check_run_id(run_id)
    base_abs = os.path.abspath(base)
    base_real = os.path.normcase(os.path.realpath(base_abs))
    target_real = os.path.normcase(
        os.path.realpath(os.path.abspath(os.path.join(base_abs, run_id)))
    )
    if target_real == base_real or not target_real.startswith(
        base_real + os.path.sep
    ):
        raise ValueError("run id stays inside the base: %r" % (run_id,))
    return os.path.join(base_abs, run_id)


def _disk_or_zero(path):
    """Return disk numbers for a folder, or zeros when it is unusable."""
    try:
        if not os.path.isdir(path):
            return {"total": 0, "free": 0, "ok": False}
        usage = shutil.disk_usage(path)
        return {
            "total": usage.total,
            "free": usage.free,
            "ok": bool(usage.free > 0),
        }
    except OSError:
        return {"total": 0, "free": 0, "ok": False}


def disk_check(path):
    """Report the disk state (free/total/ok) for a folder.

    The folder is created when missing, since it is an owned folder;
    the usage numbers come from the real disk probe.
    """
    os.makedirs(path, exist_ok=True)
    absolute = os.path.abspath(path)
    usage = shutil.disk_usage(absolute)
    return {
        "path": absolute,
        "total": usage.total,
        "free": usage.free,
        "ok": bool(usage.free > 0),
    }


def clean_run_temp(base, run_id):
    """Remove everything inside one run's own temp folder.

    Only entries directly inside the run folder are removed; the run
    folder itself is kept. Entries outside the base are never touched:
    an escaping run id raises ValueError before anything is removed.
    """
    target = run_dir_for(base, run_id)
    base_abs = os.path.abspath(base)
    if not os.path.isdir(target):
        receipt = {
            "base": base_abs,
            "run_id": run_id,
            "path": target,
            "removed": [],
            "missing": True,
            "refused": False,
        }
        receipt.update(_disk_or_zero(base_abs))
        return receipt
    removed = []
    for name in sorted(os.listdir(target)):
        full = os.path.join(target, name)
        if os.path.islink(full) or os.path.isfile(full):
            os.remove(full)
        elif os.path.isdir(full):
            shutil.rmtree(full)
        else:
            os.remove(full)
        removed.append(name)
    receipt = {
        "base": base_abs,
        "run_id": run_id,
        "path": target,
        "removed": removed,
        "missing": False,
        "refused": False,
    }
    receipt.update(_disk_or_zero(base_abs))
    return receipt


def main(argv):
    """Script entry: clean one run folder and print the JSON receipt."""
    base = None
    run_id = None
    args = list(argv)
    index = 0
    while index < len(args):
        if args[index] == "--base" and index + 1 < len(args):
            base = args[index + 1]
            index += 2
        elif args[index] == "--run" and index + 1 < len(args):
            run_id = args[index + 1]
            index += 2
        else:
            print(
                json.dumps(
                    {
                        "error": "usage: cleanup --base <dir> --run <run-id>",
                        "refused": True,
                    }
                )
            )
            return 2
    if not base or not run_id:
        print(
            json.dumps(
                {
                    "error": "usage: cleanup --base <dir> --run <run-id>",
                    "refused": True,
                }
            )
        )
        return 2
    try:
        receipt = clean_run_temp(base, run_id)
    except ValueError as exc:
        print(
            json.dumps(
                {
                    "base": os.path.abspath(base),
                    "run_id": run_id,
                    "removed": [],
                    "missing": False,
                    "refused": True,
                    "reason": str(exc),
                }
            )
        )
        return 1
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if not receipt.get("refused") else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
