"""
Populate the r/Hedera avatar cache: author -> Reddit profile-pic URL.

The dashboard (build_dashboard.py) reads data/r_Hedera/avatars.json and shows the
real profile pic in the Mentions feed where available, falling back to a colored
initial otherwise. This script fetches those URLs — run it ANYWHERE Reddit is
reachable (it is IP-blocked on the build host, so run it on your own machine).

Reliability:
  * If REDDIT_CLIENT_ID + REDDIT_CLIENT_SECRET are set, it uses read-only OAuth
    (recommended — avoids the anonymous 403s). Create an app at
    https://www.reddit.com/prefs/apps  (type "script").
  * Otherwise it tries anonymously (often 403/429-limited).

Incremental + polite: skips authors already cached, rate-limits, saves as it goes.

Run:  python -X utf8 fetch_avatars.py            # top active authors
      python -X utf8 fetch_avatars.py --all      # every author seen
"""
import os, sys, json, time
import requests
import pandas as pd

POSTS_CSV = 'data/r_Hedera/posts.csv'
COMMENTS_CSV = 'data/r_Hedera/comments.csv'
CACHE = 'data/r_Hedera/avatars.json'
LIMIT = None if '--all' in sys.argv else 400   # cap to most-active authors by default

UA = 'reddit-research/1.0 (hedera-mod-dashboard avatar fetch)'

def oauth_session():
    cid, secret = os.environ.get('REDDIT_CLIENT_ID'), os.environ.get('REDDIT_CLIENT_SECRET')
    s = requests.Session(); s.headers.update({'User-Agent': UA})
    if cid and secret:
        try:
            tok = requests.post('https://www.reddit.com/api/v1/access_token',
                                auth=(cid, secret), data={'grant_type': 'client_credentials'},
                                headers={'User-Agent': UA}, timeout=20)
            if tok.status_code == 200:
                s.headers['Authorization'] = 'bearer ' + tok.json()['access_token']
                print('Using OAuth (read-only).')
                return s, 'https://oauth.reddit.com'
            print('OAuth failed', tok.status_code, '— falling back to anonymous.')
        except Exception as e:
            print('OAuth error:', str(e)[:80])
    print('Using anonymous requests (may be rate-limited / 403).')
    return s, 'https://www.reddit.com'

def candidate_authors():
    counts = {}
    for f, col in [(POSTS_CSV, 'author'), (COMMENTS_CSV, 'author')]:
        try:
            col_s = pd.read_csv(f, low_memory=False, usecols=[col])[col].dropna()
            for a, n in col_s.value_counts().items():
                if a and a not in ('[deleted]', '[removed]'):
                    counts[a] = counts.get(a, 0) + int(n)
        except Exception as e:
            print('skip', f, str(e)[:60])
    ranked = sorted(counts, key=counts.get, reverse=True)
    return ranked if LIMIT is None else ranked[:LIMIT]

def main():
    cache = {}
    try:
        with open(CACHE, encoding='utf-8') as f:
            cache = json.load(f)
    except Exception:
        pass
    s, base = oauth_session()
    authors = [a for a in candidate_authors() if a not in cache]
    print(f'{len(cache)} cached · {len(authors)} to fetch')
    done = 0
    for i, a in enumerate(authors, 1):
        try:
            r = s.get(f'{base}/user/{a}/about', params={'raw_json': 1}, timeout=20)
            if r.status_code == 200:
                d = r.json().get('data', {})
                icon = (d.get('snoovatar_img') or d.get('icon_img') or '').split('?')[0]
                cache[a] = icon          # '' means "checked, no avatar" → don't re-fetch
                done += 1
            elif r.status_code == 404:
                cache[a] = ''            # deleted/suspended
            elif r.status_code == 429:
                print('  rate-limited, sleeping 30s'); time.sleep(30); continue
            elif r.status_code == 403:
                print('  403 — Reddit blocked this request (need OAuth or a non-blocked network).')
                break
        except Exception as e:
            print('  err', a, str(e)[:50])
        if i % 25 == 0:
            with open(CACHE, 'w', encoding='utf-8') as f:
                json.dump(cache, f)
            print(f'  …{i}/{len(authors)} (saved)')
        time.sleep(1.1)
    with open(CACHE, 'w', encoding='utf-8') as f:
        json.dump(cache, f, indent=0)
    have = sum(1 for v in cache.values() if v)
    print(f'Done. {done} new fetched · {have} authors with a pic · cache: {CACHE}')

if __name__ == '__main__':
    main()
