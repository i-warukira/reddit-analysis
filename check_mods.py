"""Check for mod activity in May 5-11 period"""
import pandas as pd
import requests
import time
from datetime import datetime

posts_df = pd.read_csv('data/r_Hedera/posts.csv')
comments_df = pd.read_csv('data/r_Hedera/comments.csv')
posts_df['created_utc'] = pd.to_datetime(posts_df['created_utc'], errors='coerce')
comments_df['created_utc'] = pd.to_datetime(comments_df['created_utc'], errors='coerce')

mask_p = (posts_df['created_utc'] >= '2026-05-05') & (posts_df['created_utc'] <= '2026-05-11 23:59:59')
mask_c = (comments_df['created_utc'] >= '2026-05-05') & (comments_df['created_utc'] <= '2026-05-11 23:59:59')
posts_p = posts_df[mask_p]
comments_p = comments_df[mask_c]

print("=" * 80)
print("MOD ACTIVITY CHECK — May 5-11, 2026")
print("=" * 80)

# 1. Check for deleted/removed posts
print()
print("1. REMOVED/DELETED POSTS:")
print("-" * 80)
removed = posts_p[posts_p['selftext'].fillna('').isin(['[removed]', '[deleted]'])]
deleted_author = posts_p[posts_p['author'].fillna('') == '[deleted]']
for _, p in removed.iterrows():
    print("  REMOVED: " + str(p['title'])[:60] + " | by " + str(p['author']))
for _, p in deleted_author.iterrows():
    print("  DELETED AUTHOR: " + str(p['title'])[:60])
if len(removed) == 0 and len(deleted_author) == 0:
    print("  None found in scraped data")

# 2. Check for removed comments
print()
print("2. REMOVED/DELETED COMMENTS:")
print("-" * 80)
removed_comments = comments_p[comments_p['body'].fillna('').isin(['[removed]', '[deleted]'])]
print("  Removed comments: " + str(len(removed_comments)))
for _, c in removed_comments.head(10).iterrows():
    print("    - by " + str(c['author']) + " in post: " + str(c.get('post_title', ''))[:50])

# 3. Check for known mod accounts
print()
print("3. KNOWN MOD/OFFICIAL ACCOUNT ACTIVITY:")
print("-" * 80)
# Common Hedera mod accounts
mod_patterns = ['mod', 'automod', 'automoderator', 'hedera', 'hashgraph', 'hederaofficial',
                'hedera_hashgraph', 'jconn', 'neeraj', 'isheep', 'lealana']
for mod in mod_patterns:
    mod_posts = posts_p[posts_p['author'].fillna('').str.lower().str.contains(mod, na=False)]
    mod_comments = comments_p[comments_p['author'].fillna('').str.lower().str.contains(mod, na=False)]
    if len(mod_posts) > 0 or len(mod_comments) > 0:
        print("  " + mod + ": " + str(len(mod_posts)) + " posts, " + str(len(mod_comments)) + " comments")
        for _, c in mod_comments.head(5).iterrows():
            print("    Comment by " + str(c['author']) + ": " + str(c['body'])[:80])

# 4. Check for mod-like actions in comment text
print()
print("4. COMMENTS MENTIONING MOD ACTIONS:")
print("-" * 80)
mod_keywords = comments_p[comments_p['body'].fillna('').str.contains(
    r'removed|banned|locked|pinned|stickied|rule violation|warning|moderator|mod team|this post has been',
    case=False, regex=True, na=False)]
for _, c in mod_keywords.head(20).iterrows():
    body_short = str(c['body'])[:120].replace('\n', ' ')
    print("  [" + str(c['author']) + "] " + body_short)
    print("    in: " + str(c.get('post_title', ''))[:50])
    print()

# 5. Check for posts with distinguishing features of mod intervention
print()
print("5. POSTS WITH ZERO SCORE (possible mod action):")
print("-" * 80)
zero_score = posts_p[posts_p['score'] <= 0]
for _, p in zero_score.iterrows():
    print("  " + str(p['title'])[:60] + " | score=" + str(p['score']) + " | comments=" + str(p['num_comments']))

# 6. Now fetch mod list from Reddit
print()
print("6. FETCHING CURRENT MOD LIST FROM REDDIT:")
print("-" * 80)
s = requests.Session()
s.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
try:
    r = s.get('https://old.reddit.com/r/Hedera/about/moderators.json', timeout=15)
    if r.status_code == 200:
        data = r.json()
        mod_names = []
        for mod in data.get('data', {}).get('children', []):
            name = mod.get('name', '')
            mod_names.append(name.lower())
            print("  " + name)

        # Now check if any mods commented in the period
        print()
        print("7. MOD COMMENTS IN PERIOD (using actual mod list):")
        print("-" * 80)
        for mod_name in mod_names:
            mod_c = comments_p[comments_p['author'].fillna('').str.lower() == mod_name]
            if len(mod_c) > 0:
                print("  " + mod_name + ": " + str(len(mod_c)) + " comments")
                for _, c in mod_c.iterrows():
                    body_short = str(c['body'])[:100].replace('\n', ' ')
                    post_title = str(c.get('post_title', ''))[:50]
                    print("    -> [" + post_title + "] " + body_short)
                    print()

        # Check mod posts
        print("8. MOD POSTS IN PERIOD:")
        print("-" * 80)
        for mod_name in mod_names:
            mod_p = posts_p[posts_p['author'].fillna('').str.lower() == mod_name]
            if len(mod_p) > 0:
                for _, p in mod_p.iterrows():
                    print("  " + mod_name + ": " + str(p['title'])[:60] + " | UP:" + str(p['score']))
    else:
        print("  Could not fetch mod list (status " + str(r.status_code) + ")")
except Exception as e:
    print("  Error: " + str(e))
