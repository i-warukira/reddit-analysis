"""Verify report data against live Reddit API"""
import requests, time
from datetime import datetime

s = requests.Session()
s.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})

all_posts = []
after = None
for page in range(5):
    url = 'https://old.reddit.com/r/Hedera/new.json?limit=100&raw_json=1'
    if after:
        url += '&after=' + after
    r = s.get(url, timeout=15)
    if r.status_code != 200:
        print('Error: ' + str(r.status_code))
        break
    data = r.json()
    children = data['data']['children']
    for c in children:
        p = c['data']
        created = datetime.fromtimestamp(p['created_utc'])
        if created >= datetime(2026, 5, 5) and created <= datetime(2026, 5, 11, 23, 59, 59):
            ptype = 'video' if p.get('is_video') else 'gallery' if p.get('is_gallery') else 'image' if 'i.redd.it' in p.get('url','') else 'link' if not p.get('is_self') else 'text'
            all_posts.append({
                'title': p['title'][:70],
                'score': p['score'],
                'comments': p['num_comments'],
                'created': created.strftime('%Y-%m-%d %H:%M'),
                'author': p['author'],
                'type': ptype,
                'upvote_ratio': p.get('upvote_ratio', 0),
            })
    after = data['data'].get('after')
    if not after:
        break
    time.sleep(2)

print('=' * 80)
print('LIVE Reddit r/Hedera posts for May 5-11: ' + str(len(all_posts)))
print('=' * 80)
print()
all_posts.sort(key=lambda x: x['created'])
for i, p in enumerate(all_posts, 1):
    print(str(i).rjust(3) + '. [' + p['created'] + '] UP:' + str(p['score']).rjust(4) + ' CMT:' + str(p['comments']).rjust(3) + ' ' + p['type'].ljust(7) + ' | ' + p['title'])

print()
print('TOP 5 BY SCORE (LIVE):')
print('-' * 80)
for p in sorted(all_posts, key=lambda x: x['score'], reverse=True)[:5]:
    print('  UP:' + str(p['score']).rjust(4) + ' CMT:' + str(p['comments']).rjust(3) + ' | ' + p['title'])

print()
print('TOP 5 BY COMMENTS (LIVE):')
print('-' * 80)
for p in sorted(all_posts, key=lambda x: x['comments'], reverse=True)[:5]:
    print('  UP:' + str(p['score']).rjust(4) + ' CMT:' + str(p['comments']).rjust(3) + ' | ' + p['title'])

print()
total_score = sum(p['score'] for p in all_posts)
total_comments = sum(p['comments'] for p in all_posts)
avg_ratio = sum(p['upvote_ratio'] for p in all_posts) / max(len(all_posts), 1) * 100
print('Total posts: ' + str(len(all_posts)))
print('Total upvotes: ' + str(total_score))
print('Total comments (from post metadata): ' + str(total_comments))
print('Avg upvote ratio: ' + str(round(avg_ratio, 1)) + '%')
authors = set(p['author'] for p in all_posts)
print('Unique post authors: ' + str(len(authors)))
print('Posts per day (6 days): ' + str(round(len(all_posts)/6, 1)))

# Type breakdown
types = {}
for p in all_posts:
    types[p['type']] = types.get(p['type'], 0) + 1
print('Post type mix: ' + ' / '.join(k + ' ' + str(round(v/len(all_posts)*100)) + '%' for k, v in sorted(types.items(), key=lambda x: -x[1])))

print()
print('=' * 80)
print('COMPARISON: Report says 62 posts, 769 comments')
print('Live data shows ' + str(len(all_posts)) + ' posts, ' + str(total_comments) + ' comments (metadata)')
print('=' * 80)
