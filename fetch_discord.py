"""
Fetch messages from a Discord server (official Bot API) into
data/discord_hedera/messages.csv — the feed for build_discord_dashboard.py.

Uses ONLY the official bot API (a user-token export would breach Discord ToS).

Setup (once):
  1. https://discord.com/developers/applications -> New Application -> Bot.
     Under Bot: enable "Message Content Intent". Copy the bot token.
  2. Invite the bot to the server (OAuth2 -> URL Generator: scope `bot`,
     permissions: View Channels + Read Message History). A server admin must
     accept the invite for the Hedera server.
  3. Save discord_config.json next to this script (git-ignored):
       { "token": "BOT_TOKEN", "guild_id": "123456789012345678",
         "channels": [] }            # empty = all readable text channels
       optional: "backfill_days": 30 # first-run history depth

Run:  python -X utf8 fetch_discord.py            # incremental (state-aware)
      python -X utf8 fetch_discord.py --list     # just list readable channels
"""
import argparse, csv, json, os, sys, time
from datetime import datetime, timedelta, timezone
import requests

API = 'https://discord.com/api/v10'
OUT_DIR = 'data/discord_hedera'
CSV_PATH = os.path.join(OUT_DIR, 'messages.csv')
STATE_PATH = os.path.join(OUT_DIR, 'state.json')
FIELDS = ['id', 'channel_id', 'channel', 'author_id', 'author', 'bot',
          'created_utc', 'content', 'reactions', 'reply_to']

DISCORD_EPOCH_MS = 1420070400000

def dt_to_snowflake(dt):
    ms = int(dt.replace(tzinfo=timezone.utc).timestamp() * 1000)
    return str((ms - DISCORD_EPOCH_MS) << 22)

def snowflake_to_iso(sf):
    ms = (int(sf) >> 22) + DISCORD_EPOCH_MS
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S')

def load_config():
    try:
        cfg = json.load(open('discord_config.json', encoding='utf-8'))
    except FileNotFoundError:
        sys.exit('discord_config.json not found — see the docstring for setup.')
    if not cfg.get('token') or not cfg.get('guild_id'):
        sys.exit('discord_config.json needs "token" and "guild_id".')
    return cfg

def api(cfg, path, params=None):
    while True:
        r = requests.get(API + path, params=params, timeout=30,
                         headers={'Authorization': f'Bot {cfg["token"]}'})
        if r.status_code == 429:                       # rate limited — obey retry_after
            wait = float(r.json().get('retry_after', 2))
            time.sleep(wait + 0.1)
            continue
        if r.status_code == 403:
            return None                                # no access to this channel — skip
        if not r.ok:
            sys.exit(f'Discord API {r.status_code} on {path}: {r.text[:200]}')
        # soft pacing: stay well under the bucket
        if r.headers.get('X-RateLimit-Remaining') == '0':
            time.sleep(float(r.headers.get('X-RateLimit-Reset-After', 1)) + 0.05)
        return r.json()

def text_channels(cfg):
    chans = api(cfg, f'/guilds/{cfg["guild_id"]}/channels') or []
    keep = [c for c in chans if c['type'] in (0, 5)]   # text + announcement
    if cfg.get('channels'):
        want = {str(x) for x in cfg['channels']}
        keep = [c for c in keep if c['id'] in want or c['name'] in want]
    return keep

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--list', action='store_true', help='list readable channels and exit')
    args = ap.parse_args()
    cfg = load_config()
    os.makedirs(OUT_DIR, exist_ok=True)

    chans = text_channels(cfg)
    if args.list:
        for c in chans: print(f'{c["id"]}  #{c["name"]}')
        return
    print(f'{len(chans)} text channels in guild {cfg["guild_id"]}')

    state = {}
    if os.path.exists(STATE_PATH):
        state = json.load(open(STATE_PATH, encoding='utf-8'))
    backfill_days = int(cfg.get('backfill_days', 30))
    default_after = dt_to_snowflake(datetime.utcnow() - timedelta(days=backfill_days))

    new_file = not os.path.exists(CSV_PATH)
    fout = open(CSV_PATH, 'a', newline='', encoding='utf-8')
    w = csv.DictWriter(fout, fieldnames=FIELDS)
    if new_file: w.writeheader()

    total = 0
    for c in chans:
        after = state.get(c['id'], default_after)
        got = 0
        while True:
            page = api(cfg, f'/channels/{c["id"]}/messages',
                       {'after': after, 'limit': 100})
            if page is None:                            # 403: bot can't read this channel
                print(f'  #{c["name"]}: no access, skipped'); break
            if not page: break
            page.sort(key=lambda m: int(m['id']))       # oldest -> newest
            for m in page:
                w.writerow({
                    'id': m['id'], 'channel_id': c['id'], 'channel': c['name'],
                    'author_id': m['author']['id'],
                    'author': m['author'].get('global_name') or m['author']['username'],
                    'bot': 1 if m['author'].get('bot') else 0,
                    'created_utc': snowflake_to_iso(m['id']),
                    'content': (m.get('content') or '').replace('\r', ' ').replace('\n', ' ')[:1500],
                    'reactions': sum(r_['count'] for r_ in m.get('reactions', [])),
                    'reply_to': (m.get('referenced_message') or {}).get('id', '') if m.get('message_reference') else '',
                })
            got += len(page)
            after = page[-1]['id']
            state[c['id']] = after
            if len(page) < 100: break
        if got: print(f'  #{c["name"]}: +{got} messages')
        total += got
        json.dump(state, open(STATE_PATH, 'w', encoding='utf-8'))
    fout.close()
    print(f'Done. +{total} new messages -> {CSV_PATH}')

if __name__ == '__main__':
    main()
