# Development tool for this build, shown as written. Not part of the app.
# Machine paths, server addresses and session ids were replaced by <PLACEHOLDERS>; the logic is unchanged.
"""Advisor monitor: a mass delete on D: shows up within 20 s. Read-only, counts entries only.
OpenCode deny rules match command text, so a script file that deletes is not refused: this is the alarm, backups are the cure."""
import os
import time

ROOTS = [
    "<DRIVE_ROOT>/",
    "<PROJECTS_ROOT>",
    "<KIT_ROOT>",
    "<BUILD_ROOT>",
    "<BUILD_ROOT>/APP",
    "<BUILD_ROOT>/APP/src/agent_si",
    "<BUILD_ROOT>/APP/tests",
    "<BUILD_ROOT>/APP/frontend/src",
    "<BUILD_ROOT>/kit",
    "<BUILD_ROOT>/DIRECTOR",
    "<BUILD_ROOT>/DIRECTOR/TOOLS",
    "<BUILD_ROOT>/DIRECTOR/INBOX",
]
MUST = ["<BUILD_ROOT>/APP/.git/HEAD"]
POLL_S = 20
DROP = 2


def count(path):
    try:
        return len(os.listdir(path))
    except OSError:
        return -1


def main():
    high = {r: count(r) for r in ROOTS}
    print("WIPEWATCH start %s" % time.strftime("%H:%M"), {r: n for r, n in high.items() if n < 0}, flush=True)
    while True:
        time.sleep(POLL_S)
        for r in ROOTS:
            n = count(r)
            if n < 0 or n <= high[r] - DROP:
                print("WIPE ALERT %s %s was %d now %d" % (time.strftime("%H:%M:%S"), r, high[r], n), flush=True)
            if n > high[r]:
                high[r] = n
            elif n < high[r] and n >= 0:
                high[r] = max(n, high[r] - 1)
        for f in MUST:
            if not os.path.exists(f):
                print("WIPE ALERT %s missing %s" % (time.strftime("%H:%M:%S"), f), flush=True)


if __name__ == "__main__":
    main()
