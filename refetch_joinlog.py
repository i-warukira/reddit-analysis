# -*- coding: utf-8 -*-
"""
Prepare a clean re-fetch of the Discord join-log so joins can be told apart from
leaves.

Three things must happen, in this order. Missing any one of them makes the
re-fetch fail silently:

  1. SCHEMA. fetch_discord.py opens messages.csv in APPEND mode and only writes a
     header when the file is new. The existing file has a 10-column header, so an
     11-field row (with the new `embed` field) is written into it misaligned and
     the column never appears. The CSV must be rewritten with the `embed` column
     first, empty for existing rows.
  2. ROWS. The fetcher appends, so re-downloading without deleting the old
     join-log rows leaves two copies of every message and doubles that channel's
     counts.
  3. CURSOR. The saved cursor makes the fetcher skip everything already seen, so
     it has to be cleared for that one channel.

It also checks that the fetcher sitting next to the data actually captures
embeds -- running the old copy is what makes this whole exercise pointless.

Safety
------
- Dry run by default; --apply required.
- Everything is rehearsed on a temporary copy first and the result verified
  before the real file is touched.
- Timestamped backups of messages.csv and state.json before any write.
- Touches ONE channel id; all other rows and cursors are left alone.

Usage
-----
    python -X utf8 refetch_joinlog.py            # rehearse + report
    python -X utf8 refetch_joinlog.py --apply    # do it
"""
import argparse, csv, json, os, shutil, sys, tempfile
from datetime import datetime

import pandas as pd

CSV_PATH = 'data/discord_hedera/messages.csv'
STATE = 'data/discord_hedera/state.json'
FETCHER = 'fetch_discord.py'
JOIN_CHANNEL_ID = '1135213560927105024'
NEW_COL = 'embed'


def migrate(src, dst, channel_id):
    """Write src -> dst with the embed column present and the channel's rows gone.

    Streamed row by row rather than via pandas, so a 128k-row file is rewritten
    without loading it all and without pandas reinterpreting any dtypes.
    """
    kept = removed = 0
    with open(src, newline='', encoding='utf-8') as fin:
        r = csv.DictReader(fin)
        fields = list(r.fieldnames or [])
        if NEW_COL not in fields:
            fields.append(NEW_COL)
        with open(dst, 'w', newline='', encoding='utf-8') as fout:
            w = csv.DictWriter(fout, fieldnames=fields)
            w.writeheader()
            for row in r:
                if str(row.get('channel_id', '')) == str(channel_id):
                    removed += 1
                    continue
                row.setdefault(NEW_COL, '')
                w.writerow(row)
                kept += 1
    return fields, kept, removed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--channel', default=JOIN_CHANNEL_ID)
    args = ap.parse_args()

    for p in (CSV_PATH, STATE):
        if not os.path.exists(p):
            sys.exit(f'missing {p} -- run from the repo root')

    # --- the check that was missing last time ---------------------------------
    fetcher_ok = os.path.exists(FETCHER) and 'embed_text' in open(FETCHER, encoding='utf-8').read()
    print(f'fetcher captures embeds : {"yes" if fetcher_ok else "NO"}  ({os.path.abspath(FETCHER)})')
    if not fetcher_ok:
        sys.exit('\nThe fetch_discord.py next to this data does not capture embeds.\n'
                 'Re-fetching with it would delete 80k rows and gain nothing.\n'
                 'Copy the updated fetcher here first, then re-run.')

    before = pd.read_csv(CSV_PATH, low_memory=False, dtype=str)
    n_hit = int((before['channel_id'].astype(str) == str(args.channel)).sum())
    name = before.loc[before['channel_id'].astype(str) == str(args.channel), 'channel'].iloc[0] if n_hit else '?'
    state = json.load(open(STATE, encoding='utf-8'))

    print(f'channel                 : {name} ({args.channel})')
    print(f'rows before             : {len(before):,}  ({len(before.columns)} columns)')
    print(f'rows to remove          : {n_hit:,}')
    print(f'cursor to clear         : {state.get(str(args.channel), "(none)")}')

    # --- rehearse on a copy, then verify -------------------------------------
    tmpdir = tempfile.mkdtemp(prefix='joinlog-')
    trial = os.path.join(tmpdir, 'messages.csv')
    fields, kept, removed = migrate(CSV_PATH, trial, args.channel)
    check = pd.read_csv(trial, low_memory=False, dtype=str)

    ok = (
        NEW_COL in check.columns
        and len(check) == len(before) - n_hit
        and int((check['channel_id'].astype(str) == str(args.channel)).sum()) == 0
        and list(check.columns) == fields
    )
    print()
    print('--- rehearsal on a temporary copy ---')
    print(f'  embed column present  : {NEW_COL in check.columns}')
    print(f'  rows after            : {len(check):,}  (expected {len(before) - n_hit:,})')
    print(f'  join-log rows left    : {int((check["channel_id"].astype(str) == str(args.channel)).sum())}')
    print(f'  columns               : {len(check.columns)}  {fields[-3:]}')
    print(f'  other channels intact : {check["channel_id"].nunique()} of {before["channel_id"].nunique() - 1} expected')
    print(f'  VERDICT               : {"OK" if ok else "FAILED - not applying"}')

    if not ok:
        shutil.rmtree(tmpdir, ignore_errors=True)
        sys.exit('rehearsal failed; real files untouched')

    if not args.apply:
        shutil.rmtree(tmpdir, ignore_errors=True)
        print('\nDRY RUN -- nothing written. Re-run with --apply.')
        return

    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    for src in (CSV_PATH, STATE):
        shutil.copy2(src, f'{src}.bak-{stamp}')
        print(f'backed up               : {src}.bak-{stamp}')

    shutil.move(trial, CSV_PATH)          # the verified file becomes the real one
    shutil.rmtree(tmpdir, ignore_errors=True)
    state.pop(str(args.channel), None)
    json.dump(state, open(STATE, 'w', encoding='utf-8'))

    print(f'\napplied: {removed:,} rows removed, {kept:,} kept, embed column added, cursor cleared.')
    print('Next: set "backfill_days": 600, run fetch_discord.py, then rebuild.')


if __name__ == '__main__':
    main()
