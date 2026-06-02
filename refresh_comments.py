"""
Refresh comments for recent posts that are already cached.
Fetches comments for the last N days of posts and appends to comments.csv.
"""
import asyncio
import aiohttp
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))
from config import USER_AGENT, MIRRORS

POSTS_CSV    = 'data/r_Hedera/posts.csv'
COMMENTS_CSV = 'data/r_Hedera/comments.csv'
DAYS_BACK    = 30   # change to 7 for weekly-only

async def fetch_comments(session, permalink, retries=3):
    for mirror in MIRRORS:
        url = f"{mirror}{permalink}.json?limit=500&raw_json=1"
        for attempt in range(retries):
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as r:
                    if r.status == 200:
                        data = await r.json()
                        if isinstance(data, list) and len(data) > 1:
                            return parse_comments(data[1]['data']['children'], permalink)
            except Exception:
                await asyncio.sleep(2)
    return []

def parse_comments(children, permalink, depth=0, max_depth=5):
    rows = []
    if depth > max_depth:
        return rows
    for child in children:
        if child.get('kind') != 't1':
            continue
        c = child['data']
        rows.append({
            'post_permalink': permalink,
            'comment_id':     c.get('id'),
            'parent_id':      c.get('parent_id'),
            'author':         c.get('author'),
            'body':           c.get('body', ''),
            'score':          c.get('score', 0),
            'created_utc':    datetime.utcfromtimestamp(c['created_utc']).strftime('%Y-%m-%dT%H:%M:%S')
                              if c.get('created_utc') else None,
            'depth':          depth,
            'is_submitter':   int(c.get('is_submitter', False)),
            'post_id':        permalink.split('/')[4] if permalink else '',
            'post_title':     '',
            'post_selftext':  '',
            'post_author':    '',
        })
        replies = c.get('replies', {})
        if isinstance(replies, dict):
            nested = replies.get('data', {}).get('children', [])
            rows.extend(parse_comments(nested, permalink, depth+1, max_depth))
    return rows

async def main():
    posts_df = pd.read_csv(POSTS_CSV)
    posts_df['created_utc'] = pd.to_datetime(posts_df['created_utc'], errors='coerce')
    posts_df = posts_df.dropna(subset=['created_utc'])

    cutoff = datetime.utcnow() - timedelta(days=DAYS_BACK)
    recent = posts_df[posts_df['created_utc'] >= cutoff].copy()
    print(f"Found {len(recent)} posts from last {DAYS_BACK} days — fetching comments...")

    # Load existing comment IDs to avoid duplicates
    try:
        existing = pd.read_csv(COMMENTS_CSV)
        existing_ids = set(existing['comment_id'].astype(str))
        print(f"Loaded {len(existing_ids)} existing comments")
    except Exception:
        existing = pd.DataFrame()
        existing_ids = set()

    headers = {'User-Agent': USER_AGENT}
    all_new = []

    async with aiohttp.ClientSession(headers=headers) as session:
        for i, (_, post) in enumerate(recent.iterrows()):
            permalink = post['permalink']
            title     = post.get('title', '')
            author    = post.get('author', '')
            print(f"  [{i+1}/{len(recent)}] {title[:55]}...", end=' ', flush=True)
            comments  = await fetch_comments(session, permalink)
            new_comments = [c for c in comments if str(c['comment_id']) not in existing_ids]
            # Tag with post info
            for c in new_comments:
                c['post_title']  = title
                c['post_author'] = author
                existing_ids.add(str(c['comment_id']))
            all_new.extend(new_comments)
            print(f"{len(new_comments)} new comments")
            await asyncio.sleep(1)   # polite rate limit

    if all_new:
        new_df = pd.DataFrame(all_new)
        combined = pd.concat([existing, new_df], ignore_index=True) if not existing.empty else new_df
        combined.to_csv(COMMENTS_CSV, index=False)
        print(f"\n✅ Added {len(all_new)} new comments → {COMMENTS_CSV}")
        print(f"   Total comments now: {len(combined)}")
    else:
        print("\n⚠️  No new comments found (all already cached or posts have no replies)")

if __name__ == '__main__':
    asyncio.run(main())
