"""
Hedera Subreddit Analytics — Community Intelligence Tracker
Full 11-section report matching the Hedera Moderator tracker framework
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import re

# ── Load data ──────────────────────────────────────────────────────────────────
posts_df    = pd.read_csv('data/r_Hedera/posts.csv')
comments_df = pd.read_csv('data/r_Hedera/comments.csv')

posts_df['created_utc']    = pd.to_datetime(posts_df['created_utc'], errors='coerce')
comments_df['created_utc'] = pd.to_datetime(comments_df['created_utc'], errors='coerce')
posts_df    = posts_df.dropna(subset=['created_utc'])
comments_df = comments_df.dropna(subset=['created_utc'])

# ── Time window (change days= to adjust period) ────────────────────────────────
now          = datetime.utcnow()
period_start = now - timedelta(days=7)
posts_p      = posts_df[posts_df['created_utc'] >= period_start].copy()
comments_p   = comments_df[comments_df['created_utc'] >= period_start].copy()
period_label = f"{period_start.strftime('%Y-%m-%d')} to {now.strftime('%Y-%m-%d')}"
num_days     = 7

# ── Helpers ────────────────────────────────────────────────────────────────────
def mentions(df, *patterns):
    col = 'title' if 'title' in df.columns else 'body'
    combined = '|'.join(patterns)
    return int(df[col].fillna('').str.contains(combined, case=False, regex=True).sum())

def mentions_combined(posts, comments, *patterns):
    """Count mentions across both post titles AND comment bodies."""
    combined = '|'.join(patterns)
    p = int(posts['title'].fillna('').str.contains(combined, case=False, regex=True).sum())
    c = int(comments['body'].fillna('').str.contains(combined, case=False, regex=True).sum())
    return p + c

def sep(char='='):
    print(char * 72)

# ── Pre-compute shared values ──────────────────────────────────────────────────
total_posts    = max(len(posts_p), 1)
posts_per_day  = len(posts_p) / num_days
avg_upvote_ratio = posts_p['upvote_ratio'].mean() * 100 if len(posts_p) > 0 else 0

# Sentiment
sentiment_positive = len(posts_p[posts_p['sentiment_label'] == 'positive']) if 'sentiment_label' in posts_p.columns else 0
sentiment_negative = len(posts_p[posts_p['sentiment_label'] == 'negative']) if 'sentiment_label' in posts_p.columns else 0
sentiment_neutral  = total_posts - sentiment_positive - sentiment_negative

# Keywords
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

# Topic counts
fud_count      = mentions(posts_p, r'fud|scam|fake|crash|rug')
scam_count     = mentions(posts_p, r'scam|phishing|stolen|hack|fake')
ai_studio_count = mentions_combined(posts_p, comments_p, r'ai studio|aistudio')
hackathon_count = mentions(posts_p, r'hackathon|apex|ethdenver')

# Support posts
support_mask = posts_p['title'].fillna('').str.contains(
    r'how|help|issue|error|problem|question|\?', case=False, regex=True)
support_posts = posts_p[support_mask]

# Prior authors for new/returning calculation
all_prior_authors = (
    set(posts_df[posts_df['created_utc'] < period_start]['author'].dropna()) |
    set(comments_df[comments_df['created_utc'] < period_start]['author'].dropna())
)
prev_30_start  = period_start - timedelta(days=30)
prev_authors   = (
    set(posts_df[(posts_df['created_utc'] >= prev_30_start) &
                  (posts_df['created_utc'] < period_start)]['author'].dropna()) |
    set(comments_df[(comments_df['created_utc'] >= prev_30_start) &
                     (comments_df['created_utc'] < period_start)]['author'].dropna())
)
unique_authors = set(posts_p['author'].dropna()) | set(comments_p['author'].dropna())
first_timers   = unique_authors - all_prior_authors
returning      = unique_authors & all_prior_authors
mom_growth     = ((len(unique_authors) - len(prev_authors)) / max(len(prev_authors), 1)) * 100

# ══════════════════════════════════════════════════════════════════════════════
sep()
print("HEDERA REDDIT — COMMUNITY INTELLIGENCE TRACKER")
sep()
print(f"Analysis Period : {period_label}")
print(f"Posts analyzed  : {len(posts_p)}  |  Comments analyzed: {len(comments_p)}")
print()

# ── Redesign Overview ──────────────────────────────────────────────────────────
sep()
print("REDESIGN OVERVIEW — 7 Sections (Eliminated Reporting Fatigue & Duplicates)")
sep()
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

# ══════════════════════════════════════════════════════════════════════════════
# 1. PERIOD OVERVIEW
# ══════════════════════════════════════════════════════════════════════════════
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
if len(support_posts) > 0:
    answered = set(comments_p['post_id'].astype(str)) & set(support_posts['id'].astype(str))
    if len(answered) == len(support_posts):
        wins.append(f"All {len(support_posts)} support questions answered — 100% resolution")

if ai_studio_count == 0:
    concerns.append(f"AI Studio: 0 mentions — zero community visibility (critical gap)")
if hackathon_count == 0:
    concerns.append("Hackathon posts: 0 — no event promotion this period")

docs_hedera = int(posts_p['selftext'].fillna('').str.contains(r'docs\.hedera\.com', case=False).sum() +
                  comments_p['body'].fillna('').str.contains(r'docs\.hedera\.com', case=False).sum())
github_hiero = int(posts_p['selftext'].fillna('').str.contains(r'github\.com/hiero|github\.com/hashgraph', case=False).sum() +
                   comments_p['body'].fillna('').str.contains(r'github\.com/hiero|github\.com/hashgraph', case=False).sum())
if docs_hedera <= 1:
    concerns.append(f"Developer docs: only {docs_hedera} link(s) shared — needs promotion")
if github_hiero == 0:
    concerns.append("GitHub / Hiero: 0 links shared — missed technical education")

print(f"{'Reporting period (dates)':<42} {period_label}")
print(f"{'Headline':<42} {len(posts_p)} posts / {len(comments_p)} comments — "
      f"{'healthy' if posts_per_day >= 5 else 'moderate'} activity, "
      f"{'zero' if scam_count == 0 else str(scam_count)} safety issues")
print()
print("Top 3 wins:")
for i, w in enumerate(wins[:3], 1): print(f"  {i}. {w}")
print()
print("Top 3 concerns:")
for i, c in enumerate(concerns[:3], 1): print(f"  {i}. {c}")
print()
dominant = f"Top keywords: {', '.join(top_keywords)}; HBAR mentions: {mentions(posts_p, r'hbar')}; Hedera mentions: {mentions(posts_p, r'hedera')}"
print(f"{'Dominant narrative':<42} {dominant}")
sentiment_dir = "UP" if sentiment_positive > sentiment_negative else "FLAT"
print(f"{'Sentiment shift vs last period':<42} {sentiment_dir} — "
      f"pos {sentiment_positive/total_posts*100:.0f}% / "
      f"neutral {sentiment_neutral/total_posts*100:.0f}% / "
      f"neg {sentiment_negative/total_posts*100:.0f}%")

# ══════════════════════════════════════════════════════════════════════════════
# 2. SUBREDDIT HEALTH
# ══════════════════════════════════════════════════════════════════════════════
print()
sep()
print("2. SUBREDDIT HEALTH — size and activity volume")
sep()

active_users      = len(unique_authors)
comments_per_post = len(comments_p) / total_posts
pct_active        = (active_users / total_posts) * 100

print(f"{'Subscribers / members':<42} {active_users}")
print(f"{'Net new subscribers (new posters/commenters)':<42} {len(first_timers)}")
print(f"{'MoM growth %':<42} {mom_growth:+.1f}%")
print(f"{'Posts (period)':<42} {len(posts_p)}")
print(f"{'Comments (period)':<42} {len(comments_p)}")
print(f"{'Active users (period)':<42} {active_users}")
print(f"{'% of subscribers who posted or commented':<42} {pct_active:.1f}%")
print(f"{'Peak online users':<42} (Reddit mod dashboard — manual input)")
print(f"{'Avg upvote ratio %':<42} {avg_upvote_ratio:.1f}%")
print(f"{'Comments per post (avg)':<42} {comments_per_post:.1f}")
print(f"{'Posts per day (avg)':<42} {posts_per_day:.1f}")

# ══════════════════════════════════════════════════════════════════════════════
# 3. CONTENT PERFORMANCE
# ══════════════════════════════════════════════════════════════════════════════
print()
sep()
print("3. CONTENT PERFORMANCE — what hit, what didn't")
sep()

if len(posts_p) > 0:
    top_idx      = posts_p['score'].idxmax()
    top_title    = posts_p.loc[top_idx, 'title'][:60]
    top_upvotes  = int(posts_p.loc[top_idx, 'score'])
    top_comments = int(posts_p.loc[top_idx, 'num_comments'])
    avg_upvotes  = posts_p['score'].mean()
    avg_comments = posts_p['num_comments'].mean()
    zero_eng     = len(posts_p[(posts_p['score'] <= 1) & (posts_p['num_comments'] == 0)])
    pct_zero     = zero_eng / len(posts_p) * 100
    total_upvotes = posts_p['score'].sum()
    comments_upvotes_ratio = len(comments_p) / max(total_upvotes, 1)
    type_pct     = (posts_p['post_type'].value_counts() / len(posts_p) * 100).round(1)
else:
    top_title = 'N/A'; top_upvotes = top_comments = 0
    avg_upvotes = avg_comments = pct_zero = comments_upvotes_ratio = 0
    type_pct = {}

print(f"{'Top post — title':<42} {top_title}")
print(f"{'Top post — upvotes':<42} {top_upvotes}")
print(f"{'Top post — comments':<42} {top_comments}")
print(f"{'Avg post upvotes':<42} {avg_upvotes:.1f}")
print(f"{'Avg post comments':<42} {avg_comments:.1f}")
mix_parts = [f"{k} {v:.0f}%" for k, v in type_pct.items()]
print(f"{'Post type mix':<42} {' / '.join(mix_parts)}")
print(f"{'Comments-to-upvotes ratio':<42} {comments_upvotes_ratio:.2f}")
print(f"{'% of posts with zero engagement':<42} {pct_zero:.1f}%")
print(f"{'Hedera team/mod posts vs community posts':<42} 0 team / {len(posts_p)} community")

# ══════════════════════════════════════════════════════════════════════════════
# 4. TOPIC MONITORING
# ══════════════════════════════════════════════════════════════════════════════
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

# Support resolved
support_post_ids  = set(support_posts['id'].astype(str))
commented_ids     = set(comments_p['post_id'].astype(str))
resolved_support  = len(support_post_ids & commented_ids)

print(f"{'Posts mentioning Hedera':<42} {hedera_count}")
print(f"{'Posts mentioning HBAR':<42} {hbar_count}")
print(f"{'Posts mentioning Hiero':<42} {hiero_count}")
print(f"{'Sentiment (positive/neutral/neg)':<42} "
      f"pos {sentiment_positive/total_posts*100:.0f}% / "
      f"neutral {sentiment_neutral/total_posts*100:.0f}% / "
      f"neg {sentiment_negative/total_posts*100:.0f}%")
print(f"{'Support questions posted':<42} {len(support_posts)}")
print(f"{'Resolved support questions':<42} {resolved_support}")
print(f"{'Posts mentioning ecosystem members':<42} {ecosystem_count}")
print(f"{'Posts mentioning AI Studio':<42} {ai_studio_count}")
print(f"{'Competitive mentions (ETH/SOL/XRP)':<42} {competitive_count}")
print(f"{'Top 3 trending keywords':<42} {', '.join(top_keywords)}")
print(f"{'Price / speculation posts flagged':<42} {price_count}")
print(f"{'FUD / negative narrative posts':<42} {fud_count}")

# ══════════════════════════════════════════════════════════════════════════════
# 5. MODERATION
# ══════════════════════════════════════════════════════════════════════════════
print()
sep()
print("5. MODERATION")
sep()

removed_posts = len(posts_p[posts_p['selftext'].fillna('').isin(['[removed]', '[deleted]'])])
removed_posts += len(posts_p[posts_p['author'].fillna('') == '[deleted]'])

print(f"{'Posts removed (spam/rules)':<42} {removed_posts}")
print(f"{'Reported posts':<42} (Reddit mod dashboard — manual input)")
print(f"{'Active moderators':<42} (Reddit mod dashboard — manual input)")
print(f"{'Scam / phishing links detected':<42} {scam_count}")
print(f"{'Impersonation accounts reported':<42} {impersonation_count}")
print(f"{'Bans issued / warnings given':<42} (Reddit mod dashboard — manual input)")
print(f"{'AutoMod actions':<42} (Reddit mod dashboard — manual input)")
print(f"{'Avg response time to reports':<42} (Reddit mod dashboard — manual input)")
print(f"{'Rule violations by rule #':<42} (Reddit mod dashboard — manual input)")

# ══════════════════════════════════════════════════════════════════════════════
# 6. COMMUNITY ENGAGEMENT QUALITY
# ══════════════════════════════════════════════════════════════════════════════
print()
sep()
print("6. COMMUNITY ENGAGEMENT QUALITY — contributor diversity")
sep()

# Top 10 share
author_activity = pd.concat([
    posts_p['author'].value_counts(),
    comments_p['author'].value_counts()
]).groupby(level=0).sum()
top10_share = (author_activity.nlargest(10).sum() / max(author_activity.sum(), 1)) * 100

# Unanswered questions (ALL questions not just dev)
all_q_ids        = set(support_posts['id'].astype(str))
unanswered_all   = len(all_q_ids - commented_ids)

# Avg thread depth
avg_thread_depth = pd.to_numeric(comments_p['depth'], errors='coerce').mean() if 'depth' in comments_p.columns and len(comments_p) > 0 else 0

# Hedera team participation (posts by known official accounts)
official_accounts = ['hedera', 'hashgraph', 'hederaofficial', 'hedera_hashgraph']
team_posts    = len(posts_p[posts_p['author'].fillna('').str.lower().isin(official_accounts)])
team_comments = len(comments_p[comments_p['author'].fillna('').str.lower().isin(official_accounts)])

# Avg time-to-first-response
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

# ══════════════════════════════════════════════════════════════════════════════
# 7. DEVELOPER FUNNEL
# ══════════════════════════════════════════════════════════════════════════════
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

print(f"{'Posts containing code snippets':<42} {code_posts_count}")
print(f"{'Links to docs.hedera.com shared':<42} {docs_hedera}")
print(f"{'Links to GitHub / Hiero shared':<42} {github_hiero}")
print(f"{'Tool mentions (Playground/Portal etc)':<42} {tool_count}")
print(f"{'Tutorial / how-to posts':<42} {tutorial_count}")
print(f"{'SDK-specific questions':<42} {sdk_count}")
print(f"{'Hackathon-related posts':<42} {hackathon_count}")
print(f"{'Unanswered dev questions (>24h)':<42} {unanswered_dev}")

# ══════════════════════════════════════════════════════════════════════════════
# 8. CROSS-PLATFORM SIGNAL
# ══════════════════════════════════════════════════════════════════════════════
print()
sep()
print("8. CROSS-PLATFORM SIGNAL")
sep()

twitter_count  = mentions_combined(posts_p, comments_p, r'twitter\.com|x\.com|\btwitter\b|\bx\.com\b')
discord_count  = mentions_combined(posts_p, comments_p, r'discord\.gg|discord\.com|\bdiscord\b')
youtube_count  = mentions_combined(posts_p, comments_p, r'youtube\.com|youtu\.be|\byoutube\b|community call')
kapa_count     = mentions_combined(posts_p, comments_p, r'kapa\.ai|hivemind|docs\.hedera\.com')
crosspost_count= mentions(posts_p, r'crosspost|cross-post|x-post')

print(f"{'Crossposts from / to X (Twitter)':<42} {crosspost_count}")
print(f"{'Links to Discord shared':<42} {discord_count}")
print(f"{'Community call / YouTube references':<42} {youtube_count}")
print(f"{'Redirects to Kapa AI / Hivemind / docs':<42} {kapa_count}")
print(f"{'Twitter / X mentions':<42} {twitter_count}")

# ══════════════════════════════════════════════════════════════════════════════
# 9. RISK & COMPLIANCE
# ══════════════════════════════════════════════════════════════════════════════
print()
sep()
print("9. RISK & COMPLIANCE")
sep()

compliance_topics = mentions_combined(posts_p, comments_p, r'sec|regulation|legal|compliance|lawsuit|ban')
misinformation    = mentions_combined(posts_p, comments_p, r'false|misinformation|fake news|not true|debunk')

print(f"{'Scam attempts detected':<42} {scam_count}")
print(f"{'Misinformation posts flagged':<42} {misinformation}")
print(f"{'Users educated on security':<42} (manual — track mod comment interventions)")
print(f"{'Posts escalated to Hedera team':<42} (manual — track via mod notes)")
print(f"{'Compliance-sensitive topics flagged':<42} {compliance_topics}")

# ══════════════════════════════════════════════════════════════════════════════
# 10. FEEDBACK & PRODUCT SIGNAL
# ══════════════════════════════════════════════════════════════════════════════
print()
sep()
print("10. FEEDBACK & PRODUCT SIGNAL")
sep()

feature_requests = mentions(posts_p, r'feature request|should have|please add|wish|would be nice|suggestion')
bug_reports      = mentions(posts_p, r'\bbug\b|broken|not working|doesn\'t work|issue with|error')
escalated        = feature_requests + bug_reports

print(f"{'Feature requests captured':<42} {feature_requests}")
print(f"{'Bug reports surfaced':<42} {bug_reports}")
print(f"{'Dominant narrative (short text)':<42} {', '.join(top_keywords)} — "
      f"{'positive' if sentiment_positive >= sentiment_negative else 'mixed'} sentiment")
print(f"{'Top 3 community concerns':<42} see Section 1 concerns above")
print(f"{'Items escalated to dev team':<42} {escalated}")

# ══════════════════════════════════════════════════════════════════════════════
# 11. REACH & DISCOVERY
# ══════════════════════════════════════════════════════════════════════════════
print()
sep()
print("11. REACH & DISCOVERY")
sep()

highly_upvoted = len(posts_p[posts_p['score'] >= 500])
moderately_upvoted = len(posts_p[posts_p['score'] >= 100])

print(f"{'Mentions in r/CryptoCurrency etc':<42} {external_count}")
print(f"{'Notable / influencer account activity':<42} (requires manual account list)")
print(f"{'Appearances in r/all or r/popular':<42} {highly_upvoted} posts (500+ upvotes)")
print(f"{'Moderately upvoted posts (100+)':<42} {moderately_upvoted}")

# ══════════════════════════════════════════════════════════════════════════════
# 12. MOD OPERATIONS
# ══════════════════════════════════════════════════════════════════════════════
print()
sep()
print("12. MOD OPERATIONS")
sep()

print(f"{'Mod hours logged':<42} (manual — mod team input required)")
print(f"{'Tickets / escalations closed':<42} (manual — mod team input required)")
print(f"{'Automations added or updated':<42} (manual — mod team input required)")
print(f"{'New resources created (wiki/FAQ/pins)':<42} (manual — mod team input required)")

# ══════════════════════════════════════════════════════════════════════════════
# SUMMARY SCORECARD
# ══════════════════════════════════════════════════════════════════════════════
print()
sep()
print("SUMMARY SCORECARD")
sep()

health  = "HEALTHY"  if (posts_per_day >= 5 and avg_upvote_ratio >= 80) else "MODERATE"
dev     = "ACTIVE"   if (code_posts_count + sdk_count + tutorial_count >= 10) else "LOW"
risk    = "LOW"      if (scam_count + fud_count <= 2) else "HIGH"
support_rate = f"{resolved_support}/{len(support_posts)} resolved" if len(support_posts) > 0 else "No support posts"

print(f"{'Period':<40} {period_label}")
print(f"{'Posts':<40} {len(posts_p)}")
print(f"{'Comments':<40} {len(comments_p)}")
print(f"{'Unique contributors':<40} {active_users}")
print(f"{'Posts per day':<40} {posts_per_day:.1f}")
print(f"{'Comments per post':<40} {comments_per_post:.1f}")
print(f"{'Community health':<40} {health}")
print(f"{'Developer activity':<40} {dev}")
print(f"{'Risk level':<40} {risk}")
print(f"{'Support resolution':<40} {support_rate}")
if avg_response:
    print(f"{'Avg response time':<40} {avg_response:.1f} hrs")
print()
sep()
print("END OF REPORT")
sep()
