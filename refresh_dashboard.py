"""
Auto-refresh runner for the Hedera Moderator Intelligence Dashboard.

What it does each run:
  1. Finds the newest post date already in data/r_Hedera/posts.csv.
  2. Pulls any newer r/Hedera posts + comments from the Arctic-Shift archive
     (live Reddit JSON is IP-blocked on this host) up to "now".
  3. Appends them to the CSVs (dedup, schema-matched, space-separated dates).
  4. Rebuilds dashboard_hedera.html via build_dashboard.py.

Designed to be safe to run repeatedly and on a schedule (idempotent: dedup by id).

Run manually:   python -X utf8 refresh_dashboard.py
Run a backfill: python -X utf8 refresh_dashboard.py 2026-04-01   (since-date override)
"""
import sys, time, subprocess, re
import requests
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from analytics.sentiment import analyze_sentiment, extract_keywords

BASE = 'https://arctic-shift.photon-reddit.com'
SUB = 'Hedera'
POSTS_CSV = 'data/r_Hedera/posts.csv'
COMMENTS_CSV = 'data/r_Hedera/comments.csv'

s = requests.Session()
s.headers.update({'User-Agent': 'reddit-research/1.0 (mod-dashboard-refresh)'})

def get(path, params, retries=5):
    for a in range(retries):
        try:
            r = s.get(BASE + path, params=params, timeout=60)
            if r.status_code == 200:
                return r.json()['data']
            if r.status_code == 429:
                time.sleep(5 * (a + 1)); continue
        except Exception as e:
            print('   retry', a, str(e)[:60]); time.sleep(3)
    return []

def paginate(path, after, before):
    out, seen, cur = [], set(), after
    while True:
        batch = get(path, {'subreddit': SUB, 'after': cur, 'before': before, 'limit': 100, 'sort': 'asc'})
        if not batch:
            break
        new = [x for x in batch if x['id'] not in seen]
        for x in new:
            seen.add(x['id'])
        out.extend(new)
        last = batch[-1]['created_utc']
        if len(batch) < 100:
            break
        cur = datetime.utcfromtimestamp(last + 1).strftime('%Y-%m-%dT%H:%M:%S')
        time.sleep(1)
    return out

def post_type(p):
    url = (p.get('url') or '').lower()
    if p.get('is_video'): return 'video'
    if p.get('is_gallery'): return 'gallery'
    if any(e in url for e in ['.jpg', '.jpeg', '.png', '.gif', '.webp']) or 'i.redd.it' in url: return 'image'
    if p.get('is_self'): return 'text'
    return 'link'

# ---- determine since-date ----
posts_old = pd.read_csv(POSTS_CSV)
cdt = pd.to_datetime(posts_old['created_utc'].astype(str).str.replace('T', ' '), errors='coerce')
if len(sys.argv) > 1:
    since = datetime.strptime(sys.argv[1], '%Y-%m-%d')
else:
    since = (cdt.max() or datetime.utcnow() - timedelta(days=7)).to_pydatetime()
after = since.strftime('%Y-%m-%dT%H:%M:%S')
before = (datetime.utcnow() + timedelta(days=1)).strftime('%Y-%m-%dT00:00:00')
print(f'Refreshing r/{SUB} from {after} to {before}')

posts_raw = paginate('/api/posts/search', after, before)
print(f'  fetched {len(posts_raw)} posts')
comments_raw = paginate('/api/comments/search', after, before)
print(f'  fetched {len(comments_raw)} comments')

# ---- build rows ----
post_rows = []
for p in posts_raw:
    title = p.get('title') or ''; selftext = p.get('selftext') or ''
    sscore, slabel = analyze_sentiment(f'{title} {selftext}')
    kw = ','.join(w for w, _ in extract_keywords([f'{title} {selftext}'], top_n=5))
    post_rows.append({'id': p.get('id'), 'title': title, 'author': p.get('author'),
        'created_utc': datetime.utcfromtimestamp(p.get('created_utc', 0)).strftime('%Y-%m-%d %H:%M:%S'),
        'permalink': p.get('permalink'), 'url': p.get('url_overridden_by_dest', p.get('url')),
        'score': p.get('score', 0), 'upvote_ratio': p.get('upvote_ratio', 0),
        'num_comments': p.get('num_comments', 0), 'num_crossposts': p.get('num_crossposts', 0),
        'selftext': selftext, 'post_type': post_type(p), 'is_nsfw': p.get('over_18', False),
        'is_spoiler': p.get('spoiler', False), 'flair': p.get('link_flair_text', ''),
        'total_awards': p.get('total_awards_received', 0),
        'has_media': bool(p.get('is_video')) or bool(p.get('is_gallery')) or 'i.redd.it' in (p.get('url') or ''),
        'media_downloaded': False, 'source': 'Arctic-Shift', 'keywords': kw,
        'sentiment_score': sscore, 'sentiment_label': slabel})

by_id = {c['id']: c for c in comments_raw}
depth_cache = {}
def depth_of(cid, g=0):
    if cid in depth_cache: return depth_cache[cid]
    c = by_id.get(cid)
    if not c or g > 50: return 0
    par = c.get('parent_id', '') or ''
    d = 0 if par.startswith('t3_') else (depth_of(par.split('_', 1)[-1], g + 1) + 1 if par.split('_', 1)[-1] in by_id else 0)
    depth_cache[cid] = d; return d

pinfo = {p['id']: p for p in posts_raw}
comment_rows = []
for c in comments_raw:
    link = (c.get('link_id', '') or '').split('_', 1)[-1]; p = pinfo.get(link, {})
    comment_rows.append({'post_permalink': p.get('permalink', ''), 'comment_id': c.get('id'),
        'parent_id': c.get('parent_id'), 'author': c.get('author'), 'body': c.get('body', ''),
        'score': c.get('score', 0),
        'created_utc': datetime.utcfromtimestamp(c.get('created_utc', 0)).strftime('%Y-%m-%d %H:%M:%S'),
        'depth': depth_of(c.get('id')), 'is_submitter': c.get('is_submitter', False),
        'post_id': link, 'post_title': p.get('title', ''), 'post_selftext': p.get('selftext', ''),
        'post_author': p.get('author', '')})

# ---- append (dedup) ----
np_ = pd.DataFrame(post_rows)
if len(np_):
    np_ = np_[~np_['id'].astype(str).isin(posts_old['id'].astype(str))]
    pd.concat([posts_old, np_], ignore_index=True).to_csv(POSTS_CSV, index=False)
print(f'  posts.csv +{len(np_) if len(post_rows) else 0} new')

comments_old = pd.read_csv(COMMENTS_CSV)
nc = pd.DataFrame(comment_rows)
if len(nc):
    nc = nc[~nc['comment_id'].astype(str).isin(comments_old['comment_id'].astype(str))]
    pd.concat([comments_old, nc], ignore_index=True).to_csv(COMMENTS_CSV, index=False)
print(f'  comments.csv +{len(nc) if len(comment_rows) else 0} new')

# ---- rebuild dashboard ----
print('Rebuilding dashboard...')
subprocess.run([sys.executable, '-X', 'utf8', 'build_dashboard.py'], check=True)
print('Refresh complete.')
