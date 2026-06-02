"""Cross-check sections 6-12 and top posts against live Reddit data"""
import requests
import pandas as pd
import numpy as np
import time
import re
from datetime import datetime, timedelta

s = requests.Session()
s.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})

# Load our data
posts_df = pd.read_csv('data/r_Hedera/posts.csv')
comments_df = pd.read_csv('data/r_Hedera/comments.csv')
posts_df['created_utc'] = pd.to_datetime(posts_df['created_utc'], errors='coerce')
comments_df['created_utc'] = pd.to_datetime(comments_df['created_utc'], errors='coerce')

period_start = datetime(2026, 5, 5)
period_end = datetime(2026, 5, 11, 23, 59, 59)
posts_p = posts_df[(posts_df['created_utc'] >= period_start) & (posts_df['created_utc'] <= period_end)].copy()
comments_p = comments_df[(comments_df['created_utc'] >= period_start) & (comments_df['created_utc'] <= period_end)].copy()

print("=" * 80)
print("CROSS-CHECK: Sections 6-12 + Top Posts")
print("=" * 80)

# ── SECTION 6: COMMUNITY ENGAGEMENT QUALITY ──
print()
print("SECTION 6: COMMUNITY ENGAGEMENT QUALITY")
print("-" * 80)

all_prior_authors = (
    set(posts_df[posts_df['created_utc'] < period_start]['author'].dropna()) |
    set(comments_df[comments_df['created_utc'] < period_start]['author'].dropna())
)
unique_authors = set(posts_p['author'].dropna()) | set(comments_p['author'].dropna())
unique_authors.discard('[deleted]')
unique_authors.discard('AutoModerator')
unique_authors.discard('Hedera-ModTeam')

first_timers = unique_authors - all_prior_authors
returning = unique_authors & all_prior_authors

print("  Unique authors (excl bots/deleted): " + str(len(unique_authors)))
print("  First-timers: " + str(len(first_timers)))
print("  Returning: " + str(len(returning)))
print("  Report says: First-time=107, Returning=148")

# Top 10 contributor share
author_activity = pd.concat([
    posts_p[~posts_p['author'].isin(['[deleted]', 'AutoModerator', 'Hedera-ModTeam'])]['author'].value_counts(),
    comments_p[~comments_p['author'].isin(['[deleted]', 'AutoModerator', 'Hedera-ModTeam'])]['author'].value_counts()
]).groupby(level=0).sum()
top10_share = (author_activity.nlargest(10).sum() / max(author_activity.sum(), 1)) * 100
print("  Top 10 contributor share: " + str(round(top10_share, 1)) + "%")
print("  Report says: 32.0%")
print("  Top 10 contributors:")
for name, count in author_activity.nlargest(10).items():
    print("    " + str(name) + ": " + str(int(count)) + " actions")

# Unanswered questions
support_mask = posts_p['title'].fillna('').str.contains(
    r'how|help|issue|error|problem|question|\?', case=False, regex=True)
support_posts = posts_p[support_mask]
commented_ids = set(comments_p['post_id'].astype(str))
unanswered = set(support_posts['id'].astype(str)) - commented_ids
print("  Support questions: " + str(len(support_posts)))
print("  Unanswered: " + str(len(unanswered)))
if len(unanswered) > 0:
    for uid in unanswered:
        title = posts_p[posts_p['id'].astype(str) == uid]['title'].values
        if len(title) > 0:
            print("    UNANSWERED: " + str(title[0])[:60])

# Avg time to first response
now = datetime.utcnow()
response_times = []
for _, post in support_posts.iterrows():
    pid = str(post['id'])
    post_time = post['created_utc']
    replies = comments_p[comments_p['post_id'].astype(str) == pid]
    if len(replies) > 0:
        hrs = (replies['created_utc'].min() - post_time).total_seconds() / 3600
        if 0 <= hrs <= 168:
            response_times.append(hrs)
avg_response = np.mean(response_times) if response_times else None
print("  Avg response time: " + (str(round(avg_response, 1)) + " hrs (from " + str(len(response_times)) + " posts)" if avg_response else "N/A"))

# Thread depth
avg_depth = pd.to_numeric(comments_p['depth'], errors='coerce').mean()
print("  Avg thread depth: " + str(round(avg_depth, 1)))

# ── SECTION 7: DEVELOPER FUNNEL ──
print()
print("SECTION 7: DEVELOPER FUNNEL")
print("-" * 80)

def mentions_combined(posts, comments, *patterns):
    combined = '|'.join(patterns)
    p = int(posts['title'].fillna('').str.contains(combined, case=False, regex=True).sum())
    t = int(posts['selftext'].fillna('').str.contains(combined, case=False, regex=True).sum())
    c = int(comments['body'].fillna('').str.contains(combined, case=False, regex=True).sum())
    return p + t + c

code_in_body = int(posts_p['selftext'].fillna('').str.contains(
    r'```|    [^\s]|\bconst \b|\bfunction \b|\bimport \b', regex=True).sum())
code_in_comments = int(comments_p['body'].fillna('').str.contains(
    r'```|    [^\s]|\bconst \b|\bfunction \b|\bimport \b', regex=True).sum())
print("  Code in post bodies: " + str(code_in_body))
print("  Code in comments: " + str(code_in_comments))

docs_posts = int(posts_p['selftext'].fillna('').str.contains(r'docs\.hedera\.com', case=False).sum())
docs_comments = int(comments_p['body'].fillna('').str.contains(r'docs\.hedera\.com', case=False).sum())
docs_urls = int(posts_p['url'].fillna('').str.contains(r'docs\.hedera\.com', case=False).sum())
print("  docs.hedera.com links: posts=" + str(docs_posts) + " comments=" + str(docs_comments) + " urls=" + str(docs_urls) + " total=" + str(docs_posts + docs_comments + docs_urls))

github_posts = int(posts_p['selftext'].fillna('').str.contains(r'github\.com/hiero|github\.com/hashgraph', case=False).sum())
github_comments = int(comments_p['body'].fillna('').str.contains(r'github\.com/hiero|github\.com/hashgraph', case=False).sum())
github_urls = int(posts_p['url'].fillna('').str.contains(r'github\.com/hiero|github\.com/hashgraph', case=False).sum())
print("  GitHub/Hiero links: posts=" + str(github_posts) + " comments=" + str(github_comments) + " urls=" + str(github_urls) + " total=" + str(github_posts + github_comments + github_urls))

tool_count = mentions_combined(posts_p, comments_p, r'playground|portal|contract builder')
print("  Tool mentions: " + str(tool_count))

tutorial_count = int(posts_p['title'].fillna('').str.contains(r'tutorial|how-?to|guide|step.by.step|walkthrough', case=False, regex=True).sum())
print("  Tutorial posts: " + str(tutorial_count))

sdk_count = int(posts_p['title'].fillna('').str.contains(r'\bsdk\b|javascript|java|\bgo\b|swift|\brust\b', case=False, regex=True).sum())
print("  SDK questions: " + str(sdk_count))

hackathon_count = int(posts_p['title'].fillna('').str.contains(r'hackathon|apex|ethdenver', case=False, regex=True).sum())
print("  Hackathon posts: " + str(hackathon_count))

# ── SECTION 8: CROSS-PLATFORM SIGNAL ──
print()
print("SECTION 8: CROSS-PLATFORM SIGNAL")
print("-" * 80)

# Check in posts body, comments body, AND post URLs
def cross_platform_check(pattern, label):
    in_titles = int(posts_p['title'].fillna('').str.contains(pattern, case=False, regex=True).sum())
    in_selftext = int(posts_p['selftext'].fillna('').str.contains(pattern, case=False, regex=True).sum())
    in_urls = int(posts_p['url'].fillna('').str.contains(pattern, case=False, regex=True).sum())
    in_comments = int(comments_p['body'].fillna('').str.contains(pattern, case=False, regex=True).sum())
    total = in_titles + in_selftext + in_urls + in_comments
    print("  " + label + ": titles=" + str(in_titles) + " selftext=" + str(in_selftext) + " urls=" + str(in_urls) + " comments=" + str(in_comments) + " TOTAL=" + str(total))
    return total

cross_platform_check(r'twitter\.com|x\.com/\w|\btwitter\b', 'Twitter/X')
cross_platform_check(r'discord\.gg|discord\.com|\bdiscord\b', 'Discord')
cross_platform_check(r'youtube\.com|youtu\.be|\byoutube\b|community call', 'YouTube')
cross_platform_check(r'kapa\.ai|hivemind', 'Kapa/Hivemind')

# ── SECTION 9: RISK & COMPLIANCE ──
print()
print("SECTION 9: RISK & COMPLIANCE")
print("-" * 80)

scam = int(posts_p['title'].fillna('').str.contains(r'scam|phishing|stolen|hack|fake', case=False, regex=True).sum())
scam_c = int(comments_p['body'].fillna('').str.contains(r'scam|phishing|stolen|hack|fake', case=False, regex=True).sum())
print("  Scam mentions: posts=" + str(scam) + " comments=" + str(scam_c))

misinfo = mentions_combined(posts_p, comments_p, r'false|misinformation|fake news|not true|debunk')
print("  Misinformation flags: " + str(misinfo))

compliance = mentions_combined(posts_p, comments_p, r'sec|regulation|legal|compliance|lawsuit|ban')
print("  Compliance topics: " + str(compliance))

# Let's also check specifically for SEC-related content (the regex r'sec' is very broad)
sec_specific = mentions_combined(posts_p, comments_p, r'\bsec\b|securities|regulation|compliance')
print("  SEC/regulation specific: " + str(sec_specific))
# The word 'sec' matches 'second', 'section', etc. — let's see what's matching
sec_in_comments = comments_p[comments_p['body'].fillna('').str.contains(r'sec|regulation|legal|compliance|lawsuit|ban', case=False, regex=True)]
print("  Comments matching compliance pattern: " + str(len(sec_in_comments)))

# ── SECTION 10: FEEDBACK & PRODUCT ──
print()
print("SECTION 10: FEEDBACK & PRODUCT")
print("-" * 80)
feature = int(posts_p['title'].fillna('').str.contains(r'feature request|should have|please add|wish|would be nice|suggestion', case=False, regex=True).sum())
bugs = int(posts_p['title'].fillna('').str.contains(r'\bbug\b|broken|not working|doesn.t work|issue with|error', case=False, regex=True).sum())
print("  Feature requests: " + str(feature))
print("  Bug reports: " + str(bugs))
# Show which posts match bug pattern
bug_posts = posts_p[posts_p['title'].fillna('').str.contains(r'\bbug\b|broken|not working|doesn.t work|issue with|error', case=False, regex=True)]
for _, p in bug_posts.iterrows():
    print("    BUG: " + str(p['title'])[:60])

# ── SECTION 11: REACH & DISCOVERY ──
print()
print("SECTION 11: REACH & DISCOVERY")
print("-" * 80)
print("  Posts 500+ upvotes: " + str(len(posts_p[posts_p['score'] >= 500])))
print("  Posts 100+ upvotes: " + str(len(posts_p[posts_p['score'] >= 100])))
print("  Posts 50+ upvotes: " + str(len(posts_p[posts_p['score'] >= 50])))

# ── TOP POSTS VERIFICATION ──
print()
print("TOP POSTS — LIVE vs REPORT")
print("-" * 80)

# Fetch live data
all_live = []
after = None
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
            all_live.append({
                'title': p['title'][:70],
                'score': p['score'],
                'comments': p['num_comments'],
            })
    after = data['data'].get('after')
    if not after:
        break
    time.sleep(2)

print()
print("LIVE TOP 5 BY UPVOTES:")
for p in sorted(all_live, key=lambda x: x['score'], reverse=True)[:5]:
    print("  UP:" + str(p['score']).rjust(4) + " CMT:" + str(p['comments']).rjust(3) + " | " + p['title'])

print()
print("REPORT TOP 5 BY UPVOTES:")
for _, row in posts_p.nlargest(5, 'score').iterrows():
    print("  UP:" + str(int(row['score'])).rjust(4) + " CMT:" + str(int(row['num_comments'])).rjust(3) + " | " + str(row['title'])[:70])

print()
print("LIVE TOP 5 BY COMMENTS:")
for p in sorted(all_live, key=lambda x: x['comments'], reverse=True)[:5]:
    print("  UP:" + str(p['score']).rjust(4) + " CMT:" + str(p['comments']).rjust(3) + " | " + p['title'])

print()
print("REPORT TOP 5 BY COMMENTS:")
for _, row in posts_p.nlargest(5, 'num_comments').iterrows():
    print("  UP:" + str(int(row['score'])).rjust(4) + " CMT:" + str(int(row['num_comments'])).rjust(3) + " | " + str(row['title'])[:70])

# Score differences
print()
print("SCORE DIFFERENCES (live vs report):")
for lp in sorted(all_live, key=lambda x: x['score'], reverse=True)[:10]:
    match = posts_p[posts_p['title'].str[:40] == lp['title'][:40]]
    if len(match) > 0:
        our_score = int(match.iloc[0]['score'])
        our_cmt = int(match.iloc[0]['num_comments'])
        if abs(lp['score'] - our_score) > 2 or abs(lp['comments'] - our_cmt) > 2:
            print("  " + lp['title'][:50])
            print("    Live: UP=" + str(lp['score']) + " CMT=" + str(lp['comments']))
            print("    Ours: UP=" + str(our_score) + " CMT=" + str(our_cmt))
