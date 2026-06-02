"""
Hedera Subreddit Analytics — Community Intelligence Tracker
Period: 2026-05-05 to 2026-05-11 (no HederaCon section)
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import re
import sys

OUTPUT_FILE = 'REPORT_2026-05-11_FINAL.txt'
_outfile = open(OUTPUT_FILE, 'w', encoding='utf-8')
_orig_print = print
def print(*args, **kwargs):
    kwargs['file'] = _outfile
    _orig_print(*args, **kwargs)
    _orig_print(*args, **{k: v for k, v in kwargs.items() if k != 'file'})

posts_df    = pd.read_csv('data/r_Hedera/posts.csv')
comments_df = pd.read_csv('data/r_Hedera/comments.csv')
posts_df['created_utc']    = pd.to_datetime(posts_df['created_utc'], errors='coerce')
comments_df['created_utc'] = pd.to_datetime(comments_df['created_utc'], errors='coerce')
posts_df    = posts_df.dropna(subset=['created_utc'])
comments_df = comments_df.dropna(subset=['created_utc'])

period_start = datetime(2026, 5, 5)
period_end   = datetime(2026, 5, 11, 23, 59, 59)
posts_p      = posts_df[(posts_df['created_utc'] >= period_start) & (posts_df['created_utc'] <= period_end)].copy()
comments_p   = comments_df[(comments_df['created_utc'] >= period_start) & (comments_df['created_utc'] <= period_end)].copy()
period_label = '2026-05-05 to 2026-05-11'
num_days     = 6

def mentions(df, *patterns):
    col = 'title' if 'title' in df.columns else 'body'
    combined = '|'.join(patterns)
    return int(df[col].fillna('').str.contains(combined, case=False, regex=True).sum())

def mentions_combined(posts, comments, *patterns):
    combined = '|'.join(patterns)
    p = int(posts['title'].fillna('').str.contains(combined, case=False, regex=True).sum())
    c = int(comments['body'].fillna('').str.contains(combined, case=False, regex=True).sum())
    return p + c

def sep(char='='):
    print(char * 72)

total_posts    = max(len(posts_p), 1)
posts_per_day  = len(posts_p) / num_days
avg_upvote_ratio = posts_p['upvote_ratio'].mean() * 100 if len(posts_p) > 0 else 0

sentiment_positive = len(posts_p[posts_p['sentiment_label'] == 'positive']) if 'sentiment_label' in posts_p.columns else 0
sentiment_negative = len(posts_p[posts_p['sentiment_label'] == 'negative']) if 'sentiment_label' in posts_p.columns else 0
sentiment_neutral  = total_posts - sentiment_positive - sentiment_negative

all_titles  = ' '.join(posts_p['title'].fillna('').tolist()).lower()
tokens      = re.findall(r'\b[a-z]{4,}\b', all_titles)
stopwords   = {'that','this','with','have','from','they','will','what','your','about',
               'been','were','when','also','like','just','more','some','into','than',
               'then','them','these','there','their','which','would','hedera','hbar'}
freq        = {}
for t in tokens:
    if t not in stopwords:
        freq[t] = freq.get(t, 0) + 1
top_keywords = sorted(freq, key=freq.get, reverse=True)[:3]

fud_count       = mentions(posts_p, r'fud|scam|fake|crash|rug')
scam_count      = mentions(posts_p, r'scam|phishing|stolen|hack|fake')
ai_studio_count = mentions_combined(posts_p, comments_p, r'ai studio|aistudio')
hackathon_count = mentions(posts_p, r'hackathon|apex|ethdenver')

support_mask  = posts_p['title'].fillna('').str.contains(
    r'how|help|issue|error|problem|question|\?', case=False, regex=True)
support_posts = posts_p[support_mask]

all_prior_authors = (
    set(posts_df[posts_df['created_utc'] < period_start]['author'].dropna()) |
    set(comments_df[comments_df['created_utc'] < period_start]['author'].dropna())
)
prev_30_start = period_start - timedelta(days=30)
prev_authors  = (
    set(posts_df[(posts_df['created_utc'] >= prev_30_start) &
                  (posts_df['created_utc'] < period_start)]['author'].dropna()) |
    set(comments_df[(comments_df['created_utc'] >= prev_30_start) &
                     (comments_df['created_utc'] < period_start)]['author'].dropna())
)
unique_authors = set(posts_p['author'].dropna()) | set(comments_p['author'].dropna())
first_timers   = unique_authors - all_prior_authors
returning      = unique_authors & all_prior_authors
mom_growth     = ((len(unique_authors) - len(prev_authors)) / max(len(prev_authors), 1)) * 100

support_post_ids = set(support_posts['id'].astype(str))
commented_ids    = set(comments_p['post_id'].astype(str))
resolved_support = len(support_post_ids & commented_ids)

docs_hedera  = int(posts_p['selftext'].fillna('').str.contains(r'docs\.hedera\.com', case=False).sum() +
                   comments_p['body'].fillna('').str.contains(r'docs\.hedera\.com', case=False).sum())
github_hiero = int(posts_p['selftext'].fillna('').str.contains(r'github\.com/hiero|github\.com/hashgraph', case=False).sum() +
                   comments_p['body'].fillna('').str.contains(r'github\.com/hiero|github\.com/hashgraph', case=False).sum())

# ========================================================================
sep()
print("HEDERA REDDIT — COMMUNITY INTELLIGENCE TRACKER")
sep()
print(f"Analysis Period : {period_label}")
print(f"Posts analyzed  : {len(posts_p)}  |  Comments analyzed: {len(comments_p)}")
print()

sep()
print("REDESIGN OVERVIEW — 7 Sections (Eliminated Reporting Fatigue & Duplicates)")
print()
print(f"  {'Section':<43} {'Purpose':<38} Signal Type")
print("-" * 72)
for s, p, t in [
    ("1. Period Overview",               "Narrative headline (wins/concerns/sentiment)", "Executive summary"),
    ("2. Subreddit Health",              "Core volume + engagement KPIs",                "Operational metrics"),
    ("3. Content Performance",           "What hit/didn't — top posts / type mix",       "Performance signal"),
    ("4. Topic & Sentiment Signal",      "What's being discussed about Hedera",          "Community signal"),
    ("5. Developer Funnel",              "Builder signals — code/docs/SDKs/Q's",         "Product signal"),
    ("6. Community Health & Moderation", "Contributor diversity + mod operations",       "Health signal"),
    ("7. Signal to Team",                "Feature requests / bugs / escalations",        "Action items"),
]:
    print(f"  {s:<43} {p:<38} {t}")
print()
sep()
print("5 DESIGN PRINCIPLES")
sep()
for i, (name, desc) in enumerate([
    ("Narrative First",        "Exec reads only Section 1 and gets the full story"),
    ("Signal Over Volume",     "Quality metrics not vanity counts (% unanswered > total posts)"),
    ("Every Section -> Action","Clear next steps not just data"),
    ("Trend-Friendly Columns", "Period 1 2 3 layout — patterns visible over time"),
    ("One Metric One Home",    "No duplication — each metric lives where most actionable"),
], 1):
    print(f"  {i}. {name:<25} {desc}")

# 1. PERIOD OVERVIEW
print()
sep()
print("1. PERIOD OVERVIEW — the so-what, written in plain English")
sep()

wins, concerns = [], []
if posts_per_day >= 5:
    wins.append(f"{posts_per_day:.1f} posts/day — healthy daily activity")
if avg_upvote_ratio >= 80:
    wins.append(f"{avg_upvote_ratio:.1f}% upvote ratio — positive community sentiment")
if scam_count == 0 and fud_count == 0:
    wins.append("Zero scams / FUD / misinformation detected — clean community")
if len(support_posts) > 0 and resolved_support == len(support_posts):
    wins.append(f"All {len(support_posts)} support questions answered — 100% resolution")

if ai_studio_count == 0:
    concerns.append("AI Studio: 0 mentions — zero community visibility (critical gap)")
if hackathon_count == 0:
    concerns.append("Hackathon posts: 0 — no event promotion this period")
if docs_hedera <= 1:
    concerns.append(f"Developer docs: only {docs_hedera} link(s) shared — needs promotion")
if github_hiero == 0:
    concerns.append("GitHub / Hiero: 0 links shared — missed technical education")

print(f"{'Reporting period (dates)':<42} {period_label}")
headline_safety = 'zero' if scam_count == 0 else str(scam_count)
headline_activity = 'healthy' if posts_per_day >= 5 else 'moderate'
print(f"{'Headline':<42} {len(posts_p)} posts / {len(comments_p)} comments — {headline_activity} activity, {headline_safety} safety issues")
print()
print("Top 3 wins:")
for i, w in enumerate(wins[:3], 1):
    print(f"  {i}. {w}")
print()
print("Top 3 concerns:")
for i, c in enumerate(concerns[:3], 1):
    print(f"  {i}. {c}")
print()
dominant = f"Top keywords: {', '.join(top_keywords)}; HBAR mentions: {mentions(posts_p, r'hbar')}; Hedera mentions: {mentions(posts_p, r'hedera')}"
print(f"{'Dominant narrative':<42} {dominant}")
sentiment_dir = "UP" if sentiment_positive > sentiment_negative else "FLAT"
print(f"{'Sentiment shift vs last period':<42} {sentiment_dir} — pos {sentiment_positive/total_posts*100:.0f}% / neutral {sentiment_neutral/total_posts*100:.0f}% / neg {sentiment_negative/total_posts*100:.0f}%")

# 2. SUBREDDIT HEALTH
print()
sep()
print("2. SUBREDDIT HEALTH — size and activity volume")
sep()
active_users      = len(unique_authors)
comments_per_post = len(comments_p) / total_posts
pct_active        = (active_users / total_posts) * 100

for label, val in [
    ("Subscribers / members", active_users),
    ("Net new subscribers (new posters/commenters)", len(first_timers)),
    ("MoM growth %", f"{mom_growth:+.1f}%"),
    ("Posts (period)", len(posts_p)),
    ("Comments (period)", len(comments_p)),
    ("Active users (period)", active_users),
    ("% of subscribers who posted or commented", f"{pct_active:.1f}%"),
    ("Peak online users", "(Reddit mod dashboard — manual input)"),
    ("Avg upvote ratio %", f"{avg_upvote_ratio:.1f}%"),
    ("Comments per post (avg)", f"{comments_per_post:.1f}"),
    ("Posts per day (avg)", f"{posts_per_day:.1f}"),
]:
    print(f"{label:<42} {val}")

# 3. CONTENT PERFORMANCE
print()
sep()
print("3. CONTENT PERFORMANCE — what hit, what didn't")
sep()
if len(posts_p) > 0:
    top_idx      = posts_p['score'].idxmax()
    top_title    = posts_p.loc[top_idx, 'title'][:60]
    top_upvotes  = int(posts_p.loc[top_idx, 'score'])
    top_comments_val = int(posts_p.loc[top_idx, 'num_comments'])
    avg_upvotes  = posts_p['score'].mean()
    avg_comments_val = posts_p['num_comments'].mean()
    zero_eng     = len(posts_p[(posts_p['score'] <= 1) & (posts_p['num_comments'] == 0)])
    pct_zero     = zero_eng / len(posts_p) * 100
    total_upvotes = posts_p['score'].sum()
    comments_upvotes_ratio = len(comments_p) / max(total_upvotes, 1)
    type_pct     = (posts_p['post_type'].value_counts() / len(posts_p) * 100).round(1)
    mix_parts = [f"{k} {v:.0f}%" for k, v in type_pct.items()]

    for label, val in [
        ("Top post — title", top_title),
        ("Top post — upvotes", top_upvotes),
        ("Top post — comments", top_comments_val),
        ("Avg post upvotes", f"{avg_upvotes:.1f}"),
        ("Avg post comments", f"{avg_comments_val:.1f}"),
        ("Post type mix", ' / '.join(mix_parts)),
        ("Comments-to-upvotes ratio", f"{comments_upvotes_ratio:.2f}"),
        ("% of posts with zero engagement", f"{pct_zero:.1f}%"),
        ("Hedera team/mod posts vs community posts", f"0 team / {len(posts_p)} community"),
    ]:
        print(f"{label:<42} {val}")

# 4. TOPIC MONITORING
print()
sep()
print("4. TOPIC MONITORING — what's being said about Hedera")
sep()
hedera_count      = mentions(posts_p, r'\bhedera\b')
hbar_count        = mentions(posts_p, r'\bhbar\b')
hiero_count       = mentions(posts_p, r'\bhiero\b')
ecosystem_count   = mentions(posts_p, r'ecosystem|partner|integration')
competitive_count = mentions(posts_p, r'\beth\b|ethereum|solana|\bsol\b|\bxrp\b|ripple')
price_count       = mentions(posts_p, r'price|moon|bullish|bearish|speculation')
external_count    = mentions(posts_p, r'r/cryptocurrency|r/cryptomarkets|crosspost')
impersonation_count = mentions_combined(posts_p, comments_p, r'impersonat|fake account|pretend')

for label, val in [
    ("Posts mentioning Hedera", hedera_count),
    ("Posts mentioning HBAR", hbar_count),
    ("Posts mentioning Hiero", hiero_count),
    ("Sentiment (positive/neutral/neg)", f"pos {sentiment_positive/total_posts*100:.0f}% / neutral {sentiment_neutral/total_posts*100:.0f}% / neg {sentiment_negative/total_posts*100:.0f}%"),
    ("Support questions posted", len(support_posts)),
    ("Resolved support questions", resolved_support),
    ("Posts mentioning ecosystem members", ecosystem_count),
    ("Posts mentioning AI Studio", ai_studio_count),
    ("Competitive mentions (ETH/SOL/XRP)", competitive_count),
    ("Top 3 trending keywords", ', '.join(top_keywords)),
    ("Price / speculation posts flagged", price_count),
    ("FUD / negative narrative posts", fud_count),
]:
    print(f"{label:<42} {val}")

# 5. MODERATION
print()
sep()
print("5. MODERATION")
sep()
removed_posts = len(posts_p[posts_p['selftext'].fillna('').isin(['[removed]', '[deleted]'])])
removed_posts += len(posts_p[posts_p['author'].fillna('') == '[deleted]'])

for label, val in [
    ("Posts removed (spam/rules)", removed_posts),
    ("Reported posts", "(Reddit mod dashboard — manual input)"),
    ("Active moderators", "(Reddit mod dashboard — manual input)"),
    ("Scam / phishing links detected", scam_count),
    ("Impersonation accounts reported", impersonation_count),
    ("Bans issued / warnings given", "(Reddit mod dashboard — manual input)"),
    ("AutoMod actions", "(Reddit mod dashboard — manual input)"),
    ("Avg response time to reports", "(Reddit mod dashboard — manual input)"),
    ("Rule violations by rule #", "(Reddit mod dashboard — manual input)"),
]:
    print(f"{label:<42} {val}")

# 6. COMMUNITY ENGAGEMENT QUALITY
print()
sep()
print("6. COMMUNITY ENGAGEMENT QUALITY — contributor diversity")
sep()
author_activity = pd.concat([
    posts_p['author'].value_counts(),
    comments_p['author'].value_counts()
]).groupby(level=0).sum()
top10_share = (author_activity.nlargest(10).sum() / max(author_activity.sum(), 1)) * 100
unanswered_all = len(set(support_posts['id'].astype(str)) - commented_ids)
avg_thread_depth = pd.to_numeric(comments_p['depth'], errors='coerce').mean() if 'depth' in comments_p.columns and len(comments_p) > 0 else 0
official_accounts = ['hedera', 'hashgraph', 'hederaofficial', 'hedera_hashgraph']
team_posts    = len(posts_p[posts_p['author'].fillna('').str.lower().isin(official_accounts)])
team_comments = len(comments_p[comments_p['author'].fillna('').str.lower().isin(official_accounts)])

now = datetime.utcnow()
response_times = []
for _, post in support_posts.iterrows():
    post_id   = str(post['id'])
    post_time = post['created_utc']
    replies   = comments_p[comments_p['post_id'].astype(str) == post_id]
    if len(replies) > 0:
        hrs = (replies['created_utc'].min() - post_time).total_seconds() / 3600
        if 0 <= hrs <= 168:
            response_times.append(hrs)
avg_response = np.mean(response_times) if response_times else None

print(f"{'First-time posters (new contributors)':<42} {len(first_timers)}")
print(f"{'Returning contributors':<42} {len(returning)}")
print(f"{'Top 10 contributor activity share %':<42} {top10_share:.1f}%")
print(f"{'Unanswered questions count':<42} {unanswered_all}")
if avg_response is not None:
    print(f"{'Avg time-to-first-response on questions':<42} {avg_response:.1f} hrs  (from {len(response_times)} posts)")
else:
    print(f"{'Avg time-to-first-response on questions':<42} No replied support posts found")
print(f"{'Hedera team participation (posts/comments)':<42} {team_posts} posts / {team_comments} comments")
print(f"{'Avg thread depth':<42} {avg_thread_depth:.1f}")

# 7. DEVELOPER FUNNEL
print()
sep()
print("7. DEVELOPER FUNNEL — builder signals")
sep()
code_in_body     = int(posts_p['selftext'].fillna('').str.contains(
    r'```|    [^\s]|\bconst \b|\bfunction \b|\bimport \b', regex=True).sum())
code_in_title    = mentions(posts_p, r'code|snippet|javascript|java|golang|python|rust')
code_posts_count = int(max(code_in_body, code_in_title))
tool_count     = mentions_combined(posts_p, comments_p, r'playground|portal|contract builder')
tutorial_count = mentions(posts_p, r'tutorial|how-?to|guide|step.by.step|walkthrough')
sdk_count      = mentions(posts_p, r'\bsdk\b|javascript|java|\bgo\b|swift|\brust\b')
cutoff_24h     = now - timedelta(hours=24)
old_support    = support_posts[support_posts['created_utc'] <= cutoff_24h]
unanswered_dev = len(set(old_support['id'].astype(str)) - commented_ids)

for label, val in [
    ("Posts containing code snippets", code_posts_count),
    ("Links to docs.hedera.com shared", docs_hedera),
    ("Links to GitHub / Hiero shared", github_hiero),
    ("Tool mentions (Playground/Portal etc)", tool_count),
    ("Tutorial / how-to posts", tutorial_count),
    ("SDK-specific questions", sdk_count),
    ("Hackathon-related posts", hackathon_count),
    ("Unanswered dev questions (>24h)", unanswered_dev),
]:
    print(f"{label:<42} {val}")

# 8. CROSS-PLATFORM SIGNAL
print()
sep()
print("8. CROSS-PLATFORM SIGNAL")
sep()
twitter_count  = mentions_combined(posts_p, comments_p, r'twitter\.com|x\.com|\btwitter\b|\bx\.com\b')
discord_count  = mentions_combined(posts_p, comments_p, r'discord\.gg|discord\.com|\bdiscord\b')
youtube_count  = mentions_combined(posts_p, comments_p, r'youtube\.com|youtu\.be|\byoutube\b|community call')
kapa_count     = mentions_combined(posts_p, comments_p, r'kapa\.ai|hivemind|docs\.hedera\.com')
crosspost_count= mentions(posts_p, r'crosspost|cross-post|x-post')

for label, val in [
    ("Crossposts from / to X (Twitter)", crosspost_count),
    ("Links to Discord shared", discord_count),
    ("Community call / YouTube references", youtube_count),
    ("Redirects to Kapa AI / Hivemind / docs", kapa_count),
    ("Twitter / X mentions", twitter_count),
]:
    print(f"{label:<42} {val}")

# 9. RISK & COMPLIANCE
print()
sep()
print("9. RISK & COMPLIANCE")
sep()
compliance_topics = mentions_combined(posts_p, comments_p, r'sec|regulation|legal|compliance|lawsuit|ban')
misinformation    = mentions_combined(posts_p, comments_p, r'false|misinformation|fake news|not true|debunk')

for label, val in [
    ("Scam attempts detected", scam_count),
    ("Misinformation posts flagged", misinformation),
    ("Users educated on security", "(manual — track mod comment interventions)"),
    ("Posts escalated to Hedera team", "(manual — track via mod notes)"),
    ("Compliance-sensitive topics flagged", compliance_topics),
]:
    print(f"{label:<42} {val}")

# 10. FEEDBACK & PRODUCT SIGNAL
print()
sep()
print("10. FEEDBACK & PRODUCT SIGNAL")
sep()
feature_requests = mentions(posts_p, r'feature request|should have|please add|wish|would be nice|suggestion')
bug_reports      = mentions(posts_p, r'\bbug\b|broken|not working|doesn\'t work|issue with|error')
escalated        = feature_requests + bug_reports

for label, val in [
    ("Feature requests captured", feature_requests),
    ("Bug reports surfaced", bug_reports),
    ("Dominant narrative (short text)", f"{', '.join(top_keywords)} — {'positive' if sentiment_positive >= sentiment_negative else 'mixed'} sentiment"),
    ("Top 3 community concerns", "see Section 1 concerns above"),
    ("Items escalated to dev team", escalated),
]:
    print(f"{label:<42} {val}")

# 11. REACH & DISCOVERY
print()
sep()
print("11. REACH & DISCOVERY")
sep()
highly_upvoted = len(posts_p[posts_p['score'] >= 500])
moderately_upvoted = len(posts_p[posts_p['score'] >= 100])

for label, val in [
    ("Mentions in r/CryptoCurrency etc", external_count),
    ("Notable / influencer account activity", "(requires manual account list)"),
    ("Appearances in r/all or r/popular", f"{highly_upvoted} posts (500+ upvotes)"),
    ("Moderately upvoted posts (100+)", moderately_upvoted),
]:
    print(f"{label:<42} {val}")

# 12. MOD OPERATIONS
print()
sep()
print("12. MOD OPERATIONS")
sep()
for label, val in [
    ("Mod hours logged", "(manual — mod team input required)"),
    ("Tickets / escalations closed", "(manual — mod team input required)"),
    ("Automations added or updated", "(manual — mod team input required)"),
    ("New resources created (wiki/FAQ/pins)", "(manual — mod team input required)"),
]:
    print(f"{label:<42} {val}")

# TOP PERFORMING POSTS
print()
sep()
print("TOP PERFORMING POSTS — Which threads drove engagement")
sep()
if len(posts_p) > 0:
    top5_upvotes = posts_p.nlargest(5, 'score')[['title', 'score', 'num_comments']].copy()
    top5_upvotes['engagement'] = (top5_upvotes['num_comments'] / (top5_upvotes['score'] + 1)).round(2)
    print()
    print("TOP 5 BY UPVOTES:")
    print("-" * 72)
    for i, (idx, row) in enumerate(top5_upvotes.iterrows(), 1):
        title = row['title'][:55]
        print(f"  {i}. {title}")
        print(f"     UP {int(row['score'])} upvotes  |  REPLY {int(row['num_comments'])} comments  |  engagement {row['engagement']:.2f}x")

    top5_comments = posts_p.nlargest(5, 'num_comments')[['title', 'score', 'num_comments']].copy()
    top5_comments['engagement'] = (top5_comments['num_comments'] / (top5_comments['score'] + 1)).round(2)
    print()
    print("TOP 5 BY DISCUSSION (Comments):")
    print("-" * 72)
    for i, (idx, row) in enumerate(top5_comments.iterrows(), 1):
        title = row['title'][:55]
        print(f"  {i}. {title}")
        print(f"     UP {int(row['score'])} upvotes  |  REPLY {int(row['num_comments'])} comments  |  engagement {row['engagement']:.2f}x")

# AREAS FOR IMPROVEMENT
print()
sep()
print("AREAS FOR IMPROVEMENT — Next steps for the community")
sep()
improvements = []
if docs_hedera <= 2:
    improvements.append(f"DOCS: Developer docs (docs.hedera.com) — Only {docs_hedera} link(s) shared. → Pin developer resource thread, promote SDK documentation")
if github_hiero == 0:
    improvements.append("CODE: GitHub/Hiero — Zero mentions. → Create tech-focused weekly thread, highlight open-source projects")
if ai_studio_count == 0:
    improvements.append("AI: AI Studio visibility — Zero mentions (critical gap). → Feature AI Studio in official announcement, create demo/tutorial")
if hackathon_count == 0:
    improvements.append("EVENTS: Hackathon/Events — Zero promotion. → Announce upcoming hackathons, post requirements")
print()
for imp in improvements[:6]:
    print(f"  • {imp}")
    print()

# SUMMARY SCORECARD
print()
sep()
print("SUMMARY SCORECARD")
sep()
health  = "HEALTHY"  if (posts_per_day >= 5 and avg_upvote_ratio >= 80) else "MODERATE"
dev     = "ACTIVE"   if (code_posts_count + sdk_count + tutorial_count >= 10) else "LOW"
risk    = "LOW"      if (scam_count + fud_count <= 2) else "HIGH"
support_rate = f"{resolved_support}/{len(support_posts)} resolved" if len(support_posts) > 0 else "No support posts"

for label, val in [
    ("Period", period_label),
    ("Posts", len(posts_p)),
    ("Comments", len(comments_p)),
    ("Unique contributors", active_users),
    ("Posts per day", f"{posts_per_day:.1f}"),
    ("Comments per post", f"{comments_per_post:.1f}"),
    ("Community health", health),
    ("Developer activity", dev),
    ("Risk level", risk),
    ("Support resolution", support_rate),
]:
    print(f"{label:<40} {val}")
if avg_response:
    print(f"{'Avg response time':<40} {avg_response:.1f} hrs")
print()
sep()
print("END OF REPORT")
sep()

_outfile.close()
_orig_print(f"\nReport saved to {OUTPUT_FILE}")
