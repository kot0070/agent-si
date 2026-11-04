# Development tool for this build, shown as written. Not part of the app.
# Machine paths, server addresses and session ids were replaced by <PLACEHOLDERS>; the logic is unchanged.
"""Plan B spend guard (read-only on opencode.db, no model calls, no subprocess).
Sums the Anthropic spend of Plan B sessions. With --watch it waits and exits on one event:
DONE in PLANB_LOG.md, STALL (no new message for 20 min), or BUDGET (interrupts the sessions first).
Owner cap: Claude $90; the guard stops at $85 to keep a margin for messages in flight.
"""
import argparse
import base64
import json
import os
import sqlite3
import time
import urllib.request

DB = os.path.expanduser(r'~/.local/share/opencode/opencode.db')
RUN = r'<BUILD_ROOT>\DIRECTOR\RUN'
SINCE_MS = 1793750000000
SRV = '<MUSE_SERVER_URL>'


def read_state():
    con = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
    total, last, sids = 0.0, 0, set()
    for sid, updated, raw in con.execute(
            "select session_id, time_updated, data from session_message "
            "where type='assistant' and time_created>=?", (SINCE_MS,)):
        data = json.loads(raw)
        if (data.get('model') or {}).get('providerID') != 'anthropic':
            continue
        total += float(data.get('cost') or 0)
        last = max(last, updated)
        sids.add(sid)
    con.close()
    return total, last, sids


def interrupt(sids):
    pw = os.environ.get('OPENCODE_WAKE_PASSWORD', '')
    basic = base64.b64encode(f'opencode:{pw}'.encode()).decode()
    for sid in sids:
        req = urllib.request.Request(f'{SRV}/api/session/{sid}/interrupt', method='POST',
                                     headers={'Authorization': f'Basic {basic}'})
        try:
            urllib.request.urlopen(req, timeout=20)
        except OSError as exc:
            print('interrupt failed', sid, exc)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--watch', action='store_true')
    ap.add_argument('--limit', type=float, default=85.0)
    ap.add_argument('--stall-min', type=int, default=20)
    ap.add_argument('--done-text', default='DONE')
    args = ap.parse_args()
    while True:
        total, last, sids = read_state()
        if not args.watch:
            print(f'spend ${total:.2f} sessions {len(sids)}')
            return
        log = os.path.join(RUN, 'PLANB_LOG.md')
        text = open(log, encoding='utf-8', errors='replace').read() if os.path.exists(log) else ''
        if total >= args.limit:
            interrupt(sids)
            print(f'BUDGET spend ${total:.2f}, sessions interrupted')
            return
        if args.done_text in text:
            print(f'DONE spend ${total:.2f}')
            return
        if last and time.time() * 1000 - last > args.stall_min * 60 * 1000:
            print(f'STALL spend ${total:.2f}, no new message for {args.stall_min} min')
            return
        time.sleep(60)


if __name__ == '__main__':
    main()
