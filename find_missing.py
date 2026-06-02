import pandas as pd

posts = pd.read_csv('data/r_Hedera/posts.csv')
comments = pd.read_csv('data/r_Hedera/comments.csv')
posts['created_utc'] = pd.to_datetime(posts['created_utc'], errors='coerce')
mask = (posts['created_utc'] >= '2026-05-05') & (posts['created_utc'] <= '2026-05-11 23:59:59')
period_posts = posts[mask]

missing_permalinks = []
for _, p in period_posts.iterrows():
    pid = str(p['id'])
    actual_count = len(comments[comments['post_id'].astype(str) == pid])
    expected = int(p['num_comments'])
    if expected > 0 and actual_count < expected * 0.5:
        title = str(p['title'])[:50]
        permalink = str(p['permalink'])
        print('MISSING: ' + title + ' | expected=' + str(expected) + ' scraped=' + str(actual_count))
        missing_permalinks.append(permalink)

print()
print('Total posts with missing comments: ' + str(len(missing_permalinks)))
