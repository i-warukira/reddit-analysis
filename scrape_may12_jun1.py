"""
Scrape r/Hedera posts + comments for 2026-05-12 .. 2026-06-01 from the
Arctic-Shift Reddit archive (live reddit JSON is IP-blocked on this host),
then append into data/r_Hedera/posts.csv and comments.csv (dedup by id),
matching the existing schema exactly so the report generator can run.
"""
import requests, time, sys
import pandas as pd
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from analytics.sentiment import analyze_sentiment, extract_keywords

BASE = 'https://arctic-shift.photon-reddit.com'
AFTER = '2026-05-12T00:00:00'
BEFORE = '2026-06-02T00:00:00'   # exclusive upper bound = end of Jun 1 UTC
SUB = 'Hedera'

s = requests.Session()
s.headers.update({'User-Agent': 'reddit-research/1.0 (community-health-report)'})

def get(path, params, retries=5):
    for a in range(retries):
        try:
            r = s.get(BASE + path, params=params, timeout=60)
            if r.status_code == 200:
                return r.json()['data']
            if r.status_code == 429:
                time.sleep(5 * (a + 1)); continue
        except Exception as e:
            print('   retry', a, str(e)[:60])
            time.sleep(3)
    return []

# ---- 1. Posts (paginate by created_utc ascending) ----
print('Fetching posts...')
posts_raw, seen = [], set()
after_ts = AFTER
while True:
    batch = get('/api/posts/search',
                {'subreddit': SUB, 'after': after_ts, 'before': BEFORE,
                 'limit': 100, 'sort': 'asc'})
    if not batch:
        break
    new = [p for p in batch if p['id'] not in seen]
    for p in new:
        seen.add(p['id'])
    posts_raw.extend(new)
    last = batch[-1]['created_utc']
    print(f'  +{len(new)} posts (total {len(posts_raw)}) up to {datetime.utcfromtimestamp(last)}')
    if len(batch) < 100:
        break
    after_ts = datetime.utcfromtimestamp(last + 1).strftime('%Y-%m-%dT%H:%M:%S')
    time.sleep(1)

def post_type(p):
    url = (p.get('url') or '').lower()
    if p.get('is_video'):
        return 'video'
    if p.get('is_gallery'):
        return 'gallery'
    if any(e in url for e in ['.jpg', '.jpeg', '.png', '.gif', '.webp']) or 'i.redd.it' in url:
        return 'image'
    if p.get('is_self'):
        return 'text'
    return 'link'

post_rows = []
for p in posts_raw:
    title = p.get('title') or ''
    selftext = p.get('selftext') or ''
    sscore, slabel = analyze_sentiment(f'{title} {selftext}')
    kw = ','.join(w for w, _ in extract_keywords([f'{title} {selftext}'], top_n=5))
    post_rows.append({
        'id': p.get('id'),
        'title': title,
        'author': p.get('author'),
        'created_utc': datetime.utcfromtimestamp(p.get('created_utc', 0)).strftime('%Y-%m-%d %H:%M:%S'),
        'permalink': p.get('permalink'),
        'url': p.get('url_overridden_by_dest', p.get('url')),
        'score': p.get('score', 0),
        'upvote_ratio': p.get('upvote_ratio', 0),
        'num_comments': p.get('num_comments', 0),
        'num_crossposts': p.get('num_crossposts', 0),
        'selftext': selftext,
        'post_type': post_type(p),
        'is_nsfw': p.get('over_18', False),
        'is_spoiler': p.get('spoiler', False),
        'flair': p.get('link_flair_text', ''),
        'total_awards': p.get('total_awards_received', 0),
        'has_media': bool(p.get('is_video')) or bool(p.get('is_gallery')) or 'i.redd.it' in (p.get('url') or ''),
        'media_downloaded': False,
        'source': 'Arctic-Shift',
        'keywords': kw,
        'sentiment_score': sscore,
        'sentiment_label': slabel,
    })
print(f'Total posts in window: {len(post_rows)}')

# ---- 2. Comments (bulk by subreddit + date, paginate) ----
print('Fetching comments...')
comments_raw, cseen = [], set()
after_ts = AFTER
while True:
    batch = get('/api/comments/search',
                {'subreddit': SUB, 'after': after_ts, 'before': BEFORE,
                 'limit': 100, 'sort': 'asc'})
    if not batch:
        break
    new = [c for c in batch if c['id'] not in cseen]
    for c in new:
        cseen.add(c['id'])
    comments_raw.extend(new)
    last = batch[-1]['created_utc']
    print(f'  +{len(new)} comments (total {len(comments_raw)}) up to {datetime.utcfromtimestamp(last)}')
    if len(batch) < 100:
        break
    after_ts = datetime.utcfromtimestamp(last + 1).strftime('%Y-%m-%dT%H:%M:%S')
    time.sleep(1)

# depth: 0 if parent is the submission (t3_), else 1 + parent comment depth
by_id = {c['id']: c for c in comments_raw}
depth_cache = {}
def depth_of(cid, guard=0):
    if cid in depth_cache:
        return depth_cache[cid]
    c = by_id.get(cid)
    if not c or guard > 50:
        return 0
    parent = c.get('parent_id', '') or ''
    if parent.startswith('t3_'):
        d = 0
    else:
        pid = parent.split('_', 1)[-1]
        d = (depth_of(pid, guard + 1) + 1) if pid in by_id else 0
    depth_cache[cid] = d
    return d

# permalink/title/selftext/author lookup from posts in window
pinfo = {p['id']: p for p in posts_raw}
comment_rows = []
for c in comments_raw:
    link = (c.get('link_id', '') or '').split('_', 1)[-1]
    p = pinfo.get(link, {})
    comment_rows.append({
        'post_permalink': p.get('permalink', ''),
        'comment_id': c.get('id'),
        'parent_id': c.get('parent_id'),
        'author': c.get('author'),
        'body': c.get('body', ''),
        'score': c.get('score', 0),
        'created_utc': datetime.utcfromtimestamp(c.get('created_utc', 0)).strftime('%Y-%m-%d %H:%M:%S'),
        'depth': depth_of(c.get('id')),
        'is_submitter': c.get('is_submitter', False),
        'post_id': link,
        'post_title': p.get('title', ''),
        'post_selftext': p.get('selftext', ''),
        'post_author': p.get('author', ''),
    })
print(f'Total comments in window: {len(comment_rows)}')

# ---- 3. Append to existing CSVs (dedup) ----
posts_path = 'data/r_Hedera/posts.csv'
comments_path = 'data/r_Hedera/comments.csv'

posts_old = pd.read_csv(posts_path)
new_posts = pd.DataFrame(post_rows)
new_posts = new_posts[~new_posts['id'].astype(str).isin(posts_old['id'].astype(str))]
posts_out = pd.concat([posts_old, new_posts], ignore_index=True)
posts_out.to_csv(posts_path, index=False)
print(f'posts.csv: +{len(new_posts)} new rows -> {len(posts_out)} total')

comments_old = pd.read_csv(comments_path)
new_comments = pd.DataFrame(comment_rows)
new_comments = new_comments[~new_comments['comment_id'].astype(str).isin(comments_old['comment_id'].astype(str))]
comments_out = pd.concat([comments_old, new_comments], ignore_index=True)
comments_out.to_csv(comments_path, index=False)
print(f'comments.csv: +{len(new_comments)} new rows -> {len(comments_out)} total')
print('Done.')
