"""
Refresh missing comments, then regenerate the verified report.
"""
import requests
import pandas as pd
import time
from datetime import datetime

s = requests.Session()
s.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})

# Step 1: Update post scores from live data
print("Updating post scores from live Reddit...")
posts_df = pd.read_csv('data/r_Hedera/posts.csv')
posts_df['created_utc'] = pd.to_datetime(posts_df['created_utc'], errors='coerce')
mask = (posts_df['created_utc'] >= '2026-05-05') & (posts_df['created_utc'] <= '2026-05-11 23:59:59')

after = None
live_posts = {}
for page in range(5):
    url = 'https://old.reddit.com/r/Hedera/new.json?limit=100&raw_json=1'
    if after:
        url += '&after=' + after
    r = s.get(url, timeout=15)
    if r.status_code != 200:
        break
    data = r.json()
    for c in data['data']['children']:
        p = c['data']
        created = datetime.fromtimestamp(p['created_utc'])
        if created >= datetime(2026, 5, 5) and created <= datetime(2026, 5, 11, 23, 59, 59):
            live_posts[p['permalink']] = {
                'score': p['score'],
                'num_comments': p['num_comments'],
                'upvote_ratio': p['upvote_ratio'],
            }
    after = data['data'].get('after')
    if not after:
        break
    time.sleep(2)

# Update scores in dataframe
updated = 0
for idx, row in posts_df[mask].iterrows():
    permalink = row['permalink']
    if permalink in live_posts:
        live = live_posts[permalink]
        posts_df.at[idx, 'score'] = live['score']
        posts_df.at[idx, 'num_comments'] = live['num_comments']
        posts_df.at[idx, 'upvote_ratio'] = live['upvote_ratio']
        updated += 1

posts_df.to_csv('data/r_Hedera/posts.csv', index=False)
print('Updated ' + str(updated) + ' posts with live scores')

# Step 2: Scrape missing comments for the one post
comments_df = pd.read_csv('data/r_Hedera/comments.csv')
period_posts = posts_df[mask]

for _, p in period_posts.iterrows():
    pid = str(p['id'])
    actual = len(comments_df[comments_df['post_id'].astype(str) == pid])
    expected = int(p['num_comments'])
    if expected > 0 and actual < expected * 0.5:
        permalink = p['permalink']
        print('Refreshing comments for: ' + str(p['title'])[:50])
        try:
            url = 'https://old.reddit.com' + permalink + '.json?limit=500'
            r = s.get(url, timeout=15)
            if r.status_code == 200:
                data = r.json()
                if len(data) > 1:
                    new_comments = []
                    def parse(items, depth=0):
                        for item in items:
                            if item['kind'] != 't1':
                                continue
                            c = item['data']
                            new_comments.append({
                                'post_permalink': permalink,
                                'post_id': pid,
                                'post_title': str(p['title']),
                                'post_selftext': str(p.get('selftext', '')),
                                'post_author': str(p.get('author', '')),
                                'comment_id': c.get('id'),
                                'parent_id': c.get('parent_id'),
                                'author': c.get('author'),
                                'body': c.get('body', ''),
                                'score': c.get('score', 0),
                                'created_utc': datetime.fromtimestamp(c.get('created_utc', 0)).isoformat(),
                                'depth': depth,
                                'is_submitter': c.get('is_submitter', False),
                            })
                            replies = c.get('replies')
                            if replies and isinstance(replies, dict):
                                parse(replies.get('data', {}).get('children', []), depth + 1)
                    parse(data[1]['data']['children'])
                    # Remove old comments for this post and add new
                    comments_df = comments_df[comments_df['post_id'].astype(str) != pid]
                    new_df = pd.DataFrame(new_comments)
                    comments_df = pd.concat([comments_df, new_df], ignore_index=True)
                    print('  Scraped ' + str(len(new_comments)) + ' comments (was ' + str(actual) + ')')
        except Exception as e:
            print('  Error: ' + str(e))
        time.sleep(2)

comments_df.to_csv('data/r_Hedera/comments.csv', index=False)
print('Comments file updated')
print('Done!')
