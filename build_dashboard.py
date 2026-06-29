"""
Hedera Moderator Intelligence Dashboard — builder.

Recomputes all KPIs from data/r_Hedera/{posts,comments}.csv for each report
cohort, then writes ONE self-contained HTML file (no external CDNs, works
offline) with: trend charts across periods, side-by-side period comparison with
deltas, issue/resolution tracking, an escalation queue, sentiment themes, gaps,
recurring-issue detection, and a Risk table (severity -> evidence -> suggested
action). Auditable: every soft metric links back to the source rows.

Run:  python -X utf8 build_dashboard.py
Out:  dashboard_hedera.html  (open in any browser)
"""
import pandas as pd
import numpy as np
import re, json, html
from datetime import datetime, timedelta

POSTS_CSV = 'data/r_Hedera/posts.csv'
COMMENTS_CSV = 'data/r_Hedera/comments.csv'
OUT = 'index.html'   # single canonical file; Vercel serves it at the site root

# Reporting cadence: TWICE A MONTH — a first-half cohort (1st–15th) and a
# second-half cohort (16th–end of month). This matches the directed schedule of
# reporting mid-month and on the last day of each month (~13–16 days each).
# Cohorts span the full 2025+2026 history (for year-over-year + annual baselines)
# and extend through the latest data each rebuild.
def semimonthly_cohorts(earliest, latest):
    out, y, m = [], earliest.year, earliest.month
    while datetime(y, m, 1).date() <= latest.date():
        last_day = (datetime(y + (m == 12), (m % 12) + 1, 1) - timedelta(days=1))
        halves = [(datetime(y, m, 1), datetime(y, m, 15)),
                  (datetime(y, m, 16), last_day)]
        for s, e in halves:
            if e.date() >= earliest.date() and s.date() <= latest.date():
                out.append((s.strftime('%Y-%m-%d'), e.strftime('%Y-%m-%d')))
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return out

# ---------------------------------------------------------------- load
P = pd.read_csv(POSTS_CSV, low_memory=False)
C = pd.read_csv(COMMENTS_CSV, low_memory=False)
P['created_utc'] = pd.to_datetime(P['created_utc'].astype(str).str.replace('T', ' '), errors='coerce')
C['created_utc'] = pd.to_datetime(C['created_utc'].astype(str).str.replace('T', ' '), errors='coerce')
P = P.dropna(subset=['created_utc'])
C = C.dropna(subset=['created_utc'])
TRACKER_START = min(P['created_utc'].min(), C['created_utc'].min()).strftime('%Y-%m-%d')

# Optional avatar cache (author -> icon URL), populated by fetch_avatars.py wherever
# Reddit is reachable. Absent/empty on this host (Reddit is IP-blocked) — the feed then
# falls back to colored initials, so the dashboard still works fully offline.
AVATARS = {}
try:
    with open('data/r_Hedera/avatars.json', encoding='utf-8') as _f:
        AVATARS = json.load(_f)
except Exception:
    AVATARS = {}

def _snip(text, pat):
    m = re.search(pat, str(text), flags=re.IGNORECASE)
    if not m:
        return str(text)[:140].replace('\n', ' ')
    a = max(0, m.start() - 50); b = min(len(str(text)), m.end() + 50)
    return ('…' if a > 0 else '') + str(text)[a:b].replace('\n', ' ') + ('…' if b < len(str(text)) else '')

def ev_posts(df, pat):
    h = df[df['title'].fillna('').str.contains(pat, case=False, regex=True)]
    return [{'date': str(r['created_utc'])[:16], 'author': str(r.get('author', '')),
             'where': 'post', 'link': str(r.get('permalink', '')), 'text': _snip(r['title'], pat)}
            for _, r in h.iterrows()]

def ev_combined(posts, comments, pat):
    rows = ev_posts(posts, pat)
    h = comments[comments['body'].fillna('').str.contains(pat, case=False, regex=True)]
    for _, r in h.iterrows():
        rows.append({'date': str(r['created_utc'])[:16], 'author': str(r.get('author', '')),
                     'where': 'comment', 'link': str(r.get('post_permalink', '')), 'text': _snip(r['body'], pat)})
    return rows

def count_p(df, pat):
    return int(df['title'].fillna('').str.contains(pat, case=False, regex=True).sum())

# Risk categories: (key, label, regex, scope, severity thresholds, action)
RISK_DEFS = [
    # Actual scam/phishing ATTEMPTS (attack signals) — NOT users saying "x is a scam"
    ('scam', 'Scam / phishing attempts', r'wallet drainer|connect your wallet|double your (?:money|hbar|crypto|invest)|claim.{0,15}airdrop|airdrop.{0,15}claim|free hbar|t\.me/|join.{0,10}telegram|\bdm me\b|message me.{0,15}(?:support|help|wallet)|giveaway', 'both',
     'Verify & remove offending posts/comments; report sender to Reddit admins; warn affected users; pin a scam-awareness note.'),
    ('impersonation', 'Impersonation / fake accounts', r'impersonat|fake account|scam account|fake profile|posing as', 'both',
     'Cross-check named accounts; report impersonators to Reddit admins; add to mod watchlist.'),
    ('fud', 'FUD / negative narrative', r'\bfud\b|spreading fear|\brug\s?pull\b|rugpull', 'posts',
     'Engage with facts; surface official sources; avoid amplifying — monitor for coordination.'),
    ('misinformation', 'Misinformation', r'misinformation|fake news|not true|debunk|false claim', 'both',
     'Reply with authoritative correction (docs/official); flag persistent offenders.'),
    ('compliance', 'Compliance-sensitive (SEC/regulation/legal)', r'\bsec\b|\bcftc\b|regulation|regulatory|lawsuit|compliance|legal action|\bbanned\b', 'both',
     'Route to Hedera team for an official line; avoid mods giving legal/financial advice.'),
]

def severity(key, n):
    # category-specific thresholds -> (level, rank)
    t = {'scam': (1, 3), 'impersonation': (1, 3), 'fud': (3, 8),
         'misinformation': (3, 8), 'compliance': (40, 100)}[key]
    if n == 0: return ('None', 0)
    if n < t[0]: return ('Low', 1)
    if n < t[1]: return ('Medium', 2)
    return ('High', 3)

def metrics(start, end):
    ps = datetime.strptime(start, '%Y-%m-%d')
    pe = datetime.strptime(end, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
    ndays = (pe.date() - ps.date()).days + 1
    pp = P[(P.created_utc >= ps) & (P.created_utc <= pe)].copy()
    cp = C[(C.created_utc >= ps) & (C.created_utc <= pe)].copy()
    n_posts, n_comments = len(pp), len(cp)
    tot = max(n_posts, 1)

    # contributors / growth (equal-length prior window)
    prior_all = (set(P[P.created_utc < ps]['author'].dropna()) | set(C[C.created_utc < ps]['author'].dropna()))
    prevw_start = ps - timedelta(days=ndays)
    prev_auth = (set(P[(P.created_utc >= prevw_start) & (P.created_utc < ps)]['author'].dropna()) |
                 set(C[(C.created_utc >= prevw_start) & (C.created_utc < ps)]['author'].dropna()))
    uniq = (set(pp['author'].dropna()) | set(cp['author'].dropna())); uniq.discard('[deleted]')
    new_tr = uniq - prior_all
    returning = uniq & prior_all
    growth = ((len(uniq) - len(prev_auth)) / max(len(prev_auth), 1)) * 100

    # sentiment
    spos = int((pp.get('sentiment_label') == 'positive').sum()) if 'sentiment_label' in pp else 0
    sneg = int((pp.get('sentiment_label') == 'negative').sum()) if 'sentiment_label' in pp else 0
    sneu = tot - spos - sneg

    # keywords / themes
    toks = re.findall(r'\b[a-z]{4,}\b', ' '.join(pp['title'].fillna('').tolist()).lower())
    stop = {'that','this','with','have','from','they','will','what','your','about','been','were',
            'when','also','like','just','more','some','into','than','then','them','these','there',
            'their','which','would','hedera','hbar','going','really','people','think'}
    freq = {}
    for t in toks:
        if t not in stop:
            freq[t] = freq.get(t, 0) + 1
    themes = sorted(freq, key=freq.get, reverse=True)[:6]

    # content
    upr = pp['upvote_ratio'].mean() * 100 if n_posts else 0
    if n_posts:
        ti = pp['score'].idxmax()
        top_post = {'title': str(pp.loc[ti, 'title'])[:80], 'score': int(pp.loc[ti, 'score']),
                    'comments': int(pp.loc[ti, 'num_comments']), 'link': str(pp.loc[ti, 'permalink'])}
        type_mix = (pp['post_type'].value_counts() / n_posts * 100).round(0).astype(int).to_dict()
        top5 = pp.nlargest(5, 'score')[['title', 'score', 'num_comments', 'permalink']]
        top_posts = [{'title': str(r.title)[:70], 'score': int(r.score), 'comments': int(r.num_comments),
                      'link': str(r.permalink)} for r in top5.itertuples()]
        pct_zero = len(pp[(pp['score'] <= 1) & (pp['num_comments'] == 0)]) / n_posts * 100
        avg_up, avg_cm = pp['score'].mean(), pp['num_comments'].mean()
        mod100 = int((pp['score'] >= 100).sum())
    else:
        top_post, type_mix, top_posts, pct_zero, avg_up, avg_cm, mod100 = {}, {}, [], 0, 0, 0, 0

    # support / dev funnel
    sup_mask = pp['title'].fillna('').str.contains(r'how|help|issue|error|problem|question|\?', case=False, regex=True)
    sup = pp[sup_mask]
    commented = set(cp['post_id'].astype(str))
    resolved = len(set(sup['id'].astype(str)) & commented)
    res_rate = (resolved / len(sup) * 100) if len(sup) else 0
    now = datetime.utcnow()
    old_sup = sup[sup['created_utc'] <= now - timedelta(hours=24)]
    escalation = old_sup[~old_sup['id'].astype(str).isin(commented)]
    escalation_rows = [{'date': str(r['created_utc'])[:16], 'author': str(r['author']),
                        'title': str(r['title'])[:80], 'link': str(r['permalink'])}
                       for _, r in escalation.iterrows()]
    # response time
    rts = []
    for _, q in sup.iterrows():
        rep = cp[cp['post_id'].astype(str) == str(q['id'])]
        if len(rep):
            hrs = (rep['created_utc'].min() - q['created_utc']).total_seconds() / 3600
            if 0 <= hrs <= 168: rts.append(hrs)
    avg_resp = round(float(np.mean(rts)), 1) if rts else None

    sdk_q = count_p(pp, r'\bsdk\b|\bapi\b|javascript|\bjava\b|swift|\brust\b|smart contract')
    code_posts = int(pp['selftext'].fillna('').str.contains(r'```|\bconst \b|\bfunction \b|\bimport \b', regex=True).sum())
    docs = int(pp['selftext'].fillna('').str.contains(r'docs\.hedera\.com', case=False).sum() +
               cp['body'].fillna('').str.contains(r'docs\.hedera\.com', case=False).sum())
    github = int(pp['selftext'].fillna('').str.contains(r'github\.com/hiero|github\.com/hashgraph', case=False).sum() +
                 cp['body'].fillna('').str.contains(r'github\.com/hiero|github\.com/hashgraph', case=False).sum())
    ai_studio = len(ev_combined(pp, cp, r'ai studio|aistudio'))
    hackathon = count_p(pp, r'hackathon|apex|ethdenver')

    # recurring issues: near-duplicate question titles
    norm = sup['title'].fillna('').str.lower().str.replace(r'[^a-z0-9 ]', '', regex=True).str.strip()
    dup = norm.value_counts()
    recurring = [{'title': k[:80], 'count': int(v)} for k, v in dup.items() if v >= 2][:8]

    # risk table + evidence
    risks, risk_evidence = [], {}
    for key, label, pat, scope, action in RISK_DEFS:
        rows = ev_posts(pp, pat) if scope == 'posts' else ev_combined(pp, cp, pat)
        lvl, rank = severity(key, len(rows))
        risks.append({'key': key, 'label': label, 'count': len(rows), 'level': lvl, 'rank': rank, 'action': action})
        risk_evidence[key] = rows
    removed = int(pp['selftext'].fillna('').isin(['[removed]', '[deleted]']).sum() + (pp['author'].fillna('') == '[deleted]').sum())

    # gaps
    gaps = []
    if docs <= 2: gaps.append({'gap': 'Developer docs barely shared', 'detail': f'{docs} docs.hedera.com link(s)', 'action': 'Pin a developer-resources thread'})
    if github == 0: gaps.append({'gap': 'No GitHub / Hiero links', 'detail': '0 links', 'action': 'Create a weekly open-source / tech thread'})
    if ai_studio == 0: gaps.append({'gap': 'AI Studio invisible', 'detail': '0 mentions', 'action': 'Feature AI Studio in an official post + demo'})
    if hackathon == 0: gaps.append({'gap': 'No event/hackathon promotion', 'detail': '0 posts', 'action': 'Announce upcoming hackathons & requirements'})

    health = 'HEALTHY' if (n_posts / ndays >= 5 and upr >= 80) else 'MODERATE'
    risk_level = max([r['rank'] for r in risks] + [0])
    risk_word = ['LOW', 'LOW', 'MEDIUM', 'HIGH'][risk_level]

    # ---- widget data (sidebar/grid reskin) ----
    # daily post volume → hero area chart
    daily = []
    if n_posts:
        dser = pp.set_index('created_utc').resample('D').size()
        daily = [{'d': d.strftime('%m-%d'), 'c': int(v)} for d, v in dser.items()]
    # day-of-week × hour activity heatmap (7×24 counts)
    heat = [[0] * 24 for _ in range(7)]
    for _, r in pp.iterrows():
        t = r['created_utc']; heat[t.weekday()][t.hour] += 1
    heat_max = max((max(row) for row in heat), default=0)
    # top authors leaderboard (by post count, with total upvotes)
    top_authors = []
    if n_posts:
        au = pp[pp['author'].fillna('') != '[deleted]'].groupby('author').agg(
            posts=('id', 'count'), score=('score', 'sum')).sort_values('posts', ascending=False).head(8)
        top_authors = [{'author': a, 'posts': int(r.posts), 'score': int(r.score)} for a, r in au.iterrows()]
    # word-cloud weights
    theme_weights = [{'t': k, 'n': int(v)} for k, v in sorted(freq.items(), key=lambda x: -x[1])[:26]]
    # mentions feed: most recent posts with author + snippet + sentiment
    feed = []
    if n_posts:
        for r in pp.sort_values('created_utc', ascending=False).head(16).itertuples():
            au = str(getattr(r, 'author', ''))
            feed.append({'author': au, 'date': str(r.created_utc)[:16],
                         'title': str(r.title)[:140], 'score': int(r.score),
                         'comments': int(r.num_comments), 'link': str(r.permalink),
                         'sentiment': str(getattr(r, 'sentiment_label', 'neutral')),
                         'avatar': AVATARS.get(au, '')})

    return {
        'daily': daily, 'heat': heat, 'heat_max': heat_max, 'top_authors': top_authors,
        'theme_weights': theme_weights, 'feed': feed,
        'start': start, 'end': end, 'days': ndays,
        'posts': n_posts, 'comments': n_comments,
        # data-completeness flag: a week with posts but no comments is an archive
        # gap, not a dead week — the UI must not let it pollute comparisons.
        'comment_data': bool(n_comments > 0),
        'posts_per_day': round(n_posts / ndays, 1),
        'comments_per_post': round(n_comments / tot, 1),
        'avg_upvote_ratio': round(upr, 1),
        'contributors': len(uniq), 'new_to_tracker': len(new_tr), 'returning': len(returning),
        'growth_pct': round(growth, 1), 'pct_zero': round(pct_zero, 1),
        'avg_post_upvotes': round(float(avg_up), 1), 'avg_post_comments': round(float(avg_cm), 1),
        'mod_upvoted_100': mod100,
        'sentiment': {'pos': round(spos / tot * 100), 'neu': round(sneu / tot * 100), 'neg': round(sneg / tot * 100)},
        'themes': themes, 'type_mix': type_mix, 'top_post': top_post, 'top_posts': top_posts,
        'issues_tracked': len(sup), 'resolved': resolved, 'resolution_rate': round(res_rate, 1),
        'escalation_count': len(escalation_rows), 'escalation_rows': escalation_rows,
        'avg_response_hrs': avg_resp,
        'sdk_questions': sdk_q, 'code_posts': code_posts, 'docs_links': docs, 'github_links': github,
        'ai_studio': ai_studio, 'hackathon': hackathon,
        'recurring': recurring, 'gaps': gaps,
        'risks': risks, 'risk_evidence': risk_evidence, 'posts_removed': removed,
        'health': health, 'risk_level': risk_word,
    }

EARLIEST = min(P['created_utc'].min(), C['created_utc'].min())
LATEST = max(P['created_utc'].max(), C['created_utc'].max())
COHORTS = semimonthly_cohorts(EARLIEST, LATEST)
PERIODS = [metrics(s, e) for s, e in COHORTS]

# ---------------------------------------------------------------- comment-data completeness
# Arctic-Shift comment coverage has gaps (a multi-month blackout) and the most recent
# weeks are still being archived, so a week can have *some* comments yet be incomplete.
# Flag a week complete only if its comments/post is >= 50% of the median of the 8 most
# recent prior comment-bearing weeks — adaptive to each era's engagement baseline, so a
# real low-traffic week isn't flagged while a half-archived week is. Supervisors then
# compare comment metrics only across weeks both marked complete.
def mark_comment_completeness(periods):
    hist = []          # c/post of periods already seen as comment-bearing
    prev_cpp = None    # previous comment-bearing period's c/post
    for p in periods:
        cpp = p['comments'] / max(p['posts'], 1)
        if p['comments'] == 0:
            p['comment_data'] = False
            continue
        ref = float(np.median(hist[-8:])) if hist else cpp
        # complete only if (a) near the recent baseline AND (b) not a sharp
        # collapse vs the previous period (the signature of a still-filling archive)
        ok = cpp >= 0.5 * ref and (prev_cpp is None or cpp >= 0.4 * prev_cpp)
        p['comment_data'] = bool(ok)
        hist.append(cpp)
        prev_cpp = cpp
    return periods

mark_comment_completeness(PERIODS)

# ---------------------------------------------------------------- presets (Common Room–style)
# Period & Compare dropdowns offer these flexible windows. Last 15 days covers
# the directed twice-monthly cadence, so semi-monthly cohorts are kept only for
# Trends / annual baselines, not surfaced in the Period dropdown.
def make_preset(label, ndays):
    end = LATEST
    start = end - timedelta(days=ndays - 1)
    m = metrics(start.strftime('%Y-%m-%d'), end.strftime('%Y-%m-%d'))
    m['label'] = label; m['ndays'] = ndays
    cpp = m['comments'] / max(m['posts'], 1)
    hist = [p['comments'] / max(p['posts'], 1) for p in PERIODS if p['comments'] > 0][-8:]
    ref = float(np.median(hist)) if hist else cpp
    m['comment_data'] = bool(m['comments'] > 0 and cpp >= 0.5 * ref)
    return m

PRESETS = [make_preset(l, n) for l, n in
           [('Last 7 days', 7), ('Last 15 days', 15), ('Last 28 days', 28),
            ('Last 12 weeks', 84), ('Last 6 months', 182), ('Last 365 days', 365)]]
DEFAULT_PRESET = 1  # Last 15 days

# Daily aggregates: per-day atoms summed in the browser for any custom range.
def daily_bucket(d):
    ds = datetime(d.year, d.month, d.day)
    de = ds.replace(hour=23, minute=59, second=59)
    pp = P[(P.created_utc >= ds) & (P.created_utc <= de)]
    cp = C[(C.created_utc >= ds) & (C.created_utc <= de)]
    pos = int((pp.get('sentiment_label') == 'positive').sum()) if 'sentiment_label' in pp else 0
    neg = int((pp.get('sentiment_label') == 'negative').sum()) if 'sentiment_label' in pp else 0
    ur_sum = float(pp['upvote_ratio'].sum()) if 'upvote_ratio' in pp and len(pp) else 0.0
    ur_cnt = int(pp['upvote_ratio'].notna().sum()) if 'upvote_ratio' in pp else 0
    authors_p = sorted(set(str(a) for a in pp['author'].dropna() if str(a) != '[deleted]'))
    authors_c = sorted(set(str(a) for a in cp['author'].dropna() if str(a) != '[deleted]'))
    type_mix = {k: int(v) for k, v in pp['post_type'].value_counts().items()} if 'post_type' in pp else {}
    top_p = []
    if len(pp):
        for _, r in pp.nlargest(3, 'score').iterrows():
            top_p.append({'author': str(r.get('author', '')), 'date': str(r['created_utc'])[:16],
                          'title': str(r.get('title', ''))[:140], 'score': int(r.get('score', 0)),
                          'comments': int(r.get('num_comments', 0)), 'link': str(r.get('permalink', '')),
                          'sentiment': str(r.get('sentiment_label', 'neutral'))})
    author_counts = {}
    if len(pp):
        for a, sub in pp.groupby('author'):
            if str(a) == '[deleted]': continue
            author_counts[str(a)] = {'posts': int(len(sub)), 'score': int(sub['score'].sum())}
    return {'p': len(pp), 'c': len(cp), 'sp': pos, 'sn': neg,
            'urs': round(ur_sum, 2), 'urc': ur_cnt,
            'ap': authors_p, 'ac': authors_c, 'tm': type_mix,
            'tp': top_p, 'au': author_counts}

DAILY = {}
_d = EARLIEST
while _d.date() <= LATEST.date():
    DAILY[_d.strftime('%Y-%m-%d')] = daily_bucket(_d)
    _d += timedelta(days=1)

# Author first-seen index (for new-vs-returning in custom ranges)
AUTHOR_FIRST_SEEN = {}
for col_df in (P, C):
    sub = col_df.dropna(subset=['author', 'created_utc']).copy()
    sub['d'] = sub['created_utc'].dt.strftime('%Y-%m-%d')
    for a, g in sub.groupby('author'):
        if str(a) == '[deleted]': continue
        d0 = g['d'].min()
        if a not in AUTHOR_FIRST_SEEN or d0 < AUTHOR_FIRST_SEEN[a]:
            AUTHOR_FIRST_SEEN[a] = d0

# ---------------------------------------------------------------- annual baselines
# "Week vs annual average" needs a per-year baseline. We average each metric across
# all weekly cohorts that fall in a given calendar year (mean of weeks), plus carry
# the year's absolute totals. Weeks are assigned to the year of their start date.
ANNUAL_METRICS = ['posts_per_day', 'comments_per_post', 'avg_upvote_ratio', 'contributors',
                  'new_to_tracker', 'returning', 'resolution_rate', 'issues_tracked',
                  'escalation_count', 'sentiment_pos', 'sentiment_neg']

def _flat(p):
    # flatten the nested sentiment dict so it can be averaged like any other metric
    d = dict(p)
    d['sentiment_pos'] = p['sentiment']['pos']
    d['sentiment_neg'] = p['sentiment']['neg']
    return d

def annual_baselines(periods):
    years = {}
    for p in periods:
        y = p['end'][:4]   # bucket by end date so boundary weeks land in the right year
        years.setdefault(y, []).append(_flat(p))
    out = {}
    for y, rows in years.items():
        n = len(rows)
        avg = {m: round(float(np.mean([r.get(m, 0) for r in rows])), 1) for m in ANNUAL_METRICS}
        # absolute year totals come straight from the raw frames (not week means)
        ys, ye = datetime(int(y), 1, 1), datetime(int(y), 12, 31, 23, 59, 59)
        yp = P[(P.created_utc >= ys) & (P.created_utc <= ye)]
        yc = C[(C.created_utc >= ys) & (C.created_utc <= ye)]
        out[y] = {'year': y, 'weeks': n, 'avg': avg,
                  'total_posts': int(len(yp)), 'total_comments': int(len(yc))}
    return out

ANNUAL = annual_baselines(PERIODS)

DATA = {'tracker_start': TRACKER_START, 'generated': datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC'),
        'periods': PERIODS, 'presets': PRESETS, 'default_preset': DEFAULT_PRESET,
        'daily': DAILY, 'author_first_seen': AUTHOR_FIRST_SEEN,
        'earliest': EARLIEST.strftime('%Y-%m-%d'), 'latest': LATEST.strftime('%Y-%m-%d'),
        'annual': ANNUAL, 'annual_metrics': ANNUAL_METRICS}

# ---------------------------------------------------------------- saved aggregate artifact
# Compact, reusable rollup so future dashboard work doesn't re-parse the full CSVs and
# we keep an auditable record of the annual averages the dashboard compares against.
AGG_OUT = 'data/r_Hedera/aggregates.json'
try:
    agg = {'generated': DATA['generated'], 'tracker_start': TRACKER_START,
           'annual': ANNUAL,
           'weekly': [{'start': p['start'], 'end': p['end'],
                       **{m: _flat(p).get(m) for m in ANNUAL_METRICS},
                       'posts': p['posts'], 'comments': p['comments']} for p in PERIODS]}
    with open(AGG_OUT, 'w', encoding='utf-8') as f:
        json.dump(agg, f, indent=2)
    print(f'Aggregates written: {AGG_OUT}')
except Exception as e:
    print('  (aggregates not written:', str(e)[:80], ')')

# ---------------------------------------------------------------- HTML
TEMPLATE = r"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Cache-Control" content="no-cache, must-revalidate">
<title>ℏIntel — r/Hedera Community Intelligence</title>
<link rel="icon" href="public/log.png">
<style>
:root{--bg:#f3f5fa;--panel:#ffffff;--ink:#1d2540;--mut:#7a85a3;--line:#e7ebf3;
--accent:#3b82f6;--good:#22c55e;--warn:#f59e0b;--bad:#ef4444;--blue:#3b82f6;
--topbar:#ffffff;--btn-alt:#eef2fb;--hover:#eef2fb;
--sb:#ffffff;--sb-ink:#5d6275;--sb-brand:#1d2540;--sb-active-ink:#1d2540;
--sb-hover:rgba(0,0,0,.04);--sb-cnt-bg:rgba(0,0,0,.06);--sb-border:rgba(0,0,0,.06);--sb-note:#8b95a8;--sb-logo-bg:var(--btn-alt);
--shadow:0 1px 3px rgba(20,30,60,.05);--shadow-lg:0 12px 40px rgba(20,30,60,.18);}
html[data-theme="dark"]{--bg:#0f1217;--panel:#181c24;--ink:#e6e9f0;--mut:#8b95a8;--line:#262b35;
--btn-alt:#262b35;--hover:#262b35;--topbar:#161a21;
--sb:#13161c;--sb-ink:#a8b1c4;--sb-brand:#ffffff;--sb-active-ink:#ffffff;
--sb-hover:rgba(255,255,255,.06);--sb-cnt-bg:rgba(255,255,255,.1);--sb-border:rgba(255,255,255,.08);--sb-note:#8b95b6;--sb-logo-bg:#ffffff;
--shadow:0 1px 3px rgba(0,0,0,.3);--shadow-lg:0 16px 50px rgba(0,0,0,.6);}
@media (prefers-color-scheme: dark){html:not([data-theme="light"]){--bg:#0f1217;--panel:#181c24;--ink:#e6e9f0;--mut:#8b95a8;--line:#262b35;
--btn-alt:#262b35;--hover:#262b35;--topbar:#161a21;
--sb:#13161c;--sb-ink:#a8b1c4;--sb-brand:#ffffff;--sb-active-ink:#ffffff;
--sb-hover:rgba(255,255,255,.06);--sb-cnt-bg:rgba(255,255,255,.1);--sb-border:rgba(255,255,255,.08);--sb-note:#8b95b6;--sb-logo-bg:#ffffff;
--shadow:0 1px 3px rgba(0,0,0,.3);--shadow-lg:0 16px 50px rgba(0,0,0,.6);}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 system-ui,Segoe UI,Roboto,sans-serif}
.app{display:flex;min-height:100vh}
.sidebar{width:218px;flex-shrink:0;background:var(--sb);color:var(--sb-ink);position:sticky;top:0;height:100vh;padding:22px 0;overflow:auto;border-right:1px solid var(--sb-border)}
.brand{display:flex;align-items:center;gap:10px;padding:0 22px 22px;color:var(--sb-brand);font-weight:600;font-size:17px}
.brand .logo{width:30px;height:30px;border-radius:8px;object-fit:contain;background:var(--sb-logo-bg);padding:3px}
.brand .h{font-weight:400}
.sbtop{display:flex;align-items:center;gap:8px;padding:0 14px 18px}.sbtop .brand{padding:0;flex:1;min-width:0}
.sbtoggle{display:flex;align-items:center;justify-content:center;width:34px;height:34px;flex-shrink:0;border:none;border-radius:9px;background:var(--sb-hover);color:var(--sb-ink);cursor:pointer}
.sbtoggle svg{width:19px;height:19px}.sbtoggle:hover{background:var(--sb-cnt-bg);color:var(--sb-active-ink)}
.topmenu{display:none;align-items:center;justify-content:center;width:36px;height:36px;flex-shrink:0;margin-right:6px;border:1px solid var(--line);border-radius:9px;background:var(--panel);color:var(--ink);cursor:pointer}
.topmenu svg{width:19px;height:19px}.topmenu:hover{background:var(--bg)}
.sbscrim{position:fixed;inset:0;background:rgba(8,12,24,.5);opacity:0;pointer-events:none;transition:opacity .25s;z-index:99}
.app.sb-collapsed .sidebar{width:64px}
.app.sb-collapsed .brand span,.app.sb-collapsed .nav a .t,.app.sb-collapsed .nav .cnt,.app.sb-collapsed .sbnote{display:none}
.app.sb-collapsed .sbtop{justify-content:center}.app.sb-collapsed .sbtop .brand{display:none}
.tbctrls{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.sbctrls .tbctrls{flex-direction:column;align-items:stretch;gap:9px;padding:12px 14px 4px;margin-top:8px;border-top:1px solid var(--sb-border)}
.sbctrls label.lbl{color:var(--sb-ink);font-size:11px;margin-bottom:-5px}
.sbctrls select{width:100%}
.sbctrls .sub{color:#8b95b6;font-size:11px}
.sbctrls .btn{width:100%;display:block;text-align:center}
.nav a{display:flex;align-items:center;gap:11px;padding:11px 22px;color:var(--sb-ink);text-decoration:none;font-size:14px;cursor:pointer;border-left:3px solid transparent}
.nav a svg{width:18px;height:18px;flex-shrink:0}
.nav a:hover{background:var(--sb-hover);color:var(--sb-active-ink)}
.nav a.active{background:rgba(59,130,246,.16);border-left-color:var(--accent);color:var(--accent)}
html[data-theme="dark"] .nav a.active{color:#fff}
@media (prefers-color-scheme: dark){html:not([data-theme="light"]) .nav a.active{color:#fff}}
.nav .cnt{margin-left:auto;background:var(--sb-cnt-bg);border-radius:999px;padding:1px 9px;font-size:11px}
.sbnote{color:var(--sb-note);font-size:11px;padding:18px 22px;border-top:1px solid var(--sb-border);margin-top:14px}
.main{flex:1;min-width:0}
.topbar{display:flex;align-items:center;gap:10px;padding:14px 26px;background:var(--topbar);border-bottom:1px solid var(--line);flex-wrap:wrap;position:sticky;top:0;z-index:30}
.topbar h2{font-size:16px;margin:0;font-weight:600;margin-right:auto}
select{background:var(--panel);color:var(--ink);border:1px solid var(--line);border-radius:8px;padding:7px 9px;font-size:13px}
label.lbl{color:var(--mut);font-size:12px}
/* Common Room–style range picker — Inter-stack, tighter, tinted blue trigger */
body{font-feature-settings:"cv02","cv03","cv04","cv11";letter-spacing:-.005em;font-family:Inter,ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
.rangebtn{display:inline-flex;align-items:center;gap:9px;background:rgba(59,130,246,.10);border:1px solid rgba(59,130,246,.32);color:var(--accent);border-radius:7px;padding:6px 11px 6px 10px;font:600 13px Inter,system-ui;cursor:pointer;transition:all 120ms;letter-spacing:-.01em}
html[data-theme="dark"] .rangebtn{background:rgba(59,130,246,.13);border-color:rgba(59,130,246,.40);color:#dbeafe}
@media(prefers-color-scheme:dark){html:not([data-theme="light"]) .rangebtn{background:rgba(59,130,246,.13);border-color:rgba(59,130,246,.40);color:#dbeafe}}
.rangebtn:hover{background:rgba(59,130,246,.18);border-color:var(--accent)}
.rangebtn .rb-i{width:14px;height:14px;color:var(--accent)}
html[data-theme="dark"] .rangebtn .rb-i{color:#93c5fd}
@media(prefers-color-scheme:dark){html:not([data-theme="light"]) .rangebtn .rb-i{color:#93c5fd}}
.rangebtn .rb-c{width:13px;height:13px;opacity:.7;margin-left:1px}
.theme-toggle{background:transparent;border:1px solid var(--line);color:var(--mut);border-radius:7px;padding:6px;cursor:pointer;display:inline-flex;align-items:center;justify-content:center}
.theme-toggle svg{width:15px;height:15px}.theme-toggle:hover{color:var(--accent);border-color:var(--accent)}

/* Popover: tighter, slightly darker tone in dark mode, refined separators */
.rpop{position:fixed;background:var(--panel);border:1px solid var(--line);border-radius:10px;box-shadow:var(--shadow-lg);padding:6px;min-width:212px;z-index:200;font:400 13px Inter,system-ui;letter-spacing:-.005em}
html[data-theme="dark"] .rpop{background:#1a1d24;border-color:#2a2f3a}
@media(prefers-color-scheme:dark){html:not([data-theme="light"]) .rpop{background:#1a1d24;border-color:#2a2f3a}}
.rpop-presets button{display:flex;align-items:center;justify-content:space-between;width:100%;background:transparent;border:none;color:var(--ink);padding:8px 12px;border-radius:6px;cursor:pointer;font:500 13px Inter,system-ui;letter-spacing:-.005em;text-align:left}
.rpop-presets button:hover{background:var(--hover)}
.rpop-presets button.sel{background:var(--accent);color:#fff}
.rpop-presets .div{height:1px;background:var(--line);margin:5px 6px}

/* Calendar panel */
.rpop-cal{margin-top:4px;padding:10px 6px 6px;border-top:1px solid var(--line);min-width:530px}

/* Outlined Start/End tabs (segmented control) */
.rpop-tabs{display:grid;grid-template-columns:1fr 1fr;gap:0;border:1px solid var(--line);border-radius:7px;overflow:hidden;margin:0 4px 12px}
.rpop-tab{background:transparent;border:none;color:var(--mut);padding:8px 0;font:600 12.5px Inter,system-ui;letter-spacing:-.005em;cursor:pointer;border-right:1px solid var(--line)}
.rpop-tab:last-child{border-right:none}
.rpop-tab:hover{color:var(--ink)}
.rpop-tab.active{background:var(--hover);color:var(--accent)}
html[data-theme="dark"] .rpop-tab.active{background:#252932;color:#dbeafe;box-shadow:inset 0 0 0 1px rgba(59,130,246,.4)}
@media(prefers-color-scheme:dark){html:not([data-theme="light"]) .rpop-tab.active{background:#252932;color:#dbeafe;box-shadow:inset 0 0 0 1px rgba(59,130,246,.4)}}

.rpop-cal-nav{display:flex;justify-content:space-between;align-items:center;margin:0 4px 4px}
.rpop-cal-nav button{background:transparent;border:none;color:var(--mut);width:24px;height:24px;border-radius:5px;cursor:pointer;font-size:16px;line-height:1;font-family:inherit}
.rpop-cal-nav button:hover{background:var(--hover);color:var(--ink)}

.rpop-months{display:grid;grid-template-columns:1fr 1fr;gap:14px;padding:0 4px}
.rpop-m h4{margin:0 0 8px;text-align:center;font:500 13px Inter,system-ui;color:var(--ink);letter-spacing:-.01em}
.rpop-grid{display:grid;grid-template-columns:repeat(7,1fr);gap:1px;font-size:12px;text-align:center;font-variant-numeric:tabular-nums}
.rpop-dh{color:var(--mut);font-weight:500;padding:4px 0;font-size:10.5px;text-transform:none}

.rpop-d{padding:6px 0;border-radius:4px;cursor:pointer;color:var(--ink);user-select:none;font-weight:400;line-height:1.5}
.rpop-d:hover{background:var(--hover)}
.rpop-d.dis{color:var(--mut);opacity:.32;cursor:not-allowed}
.rpop-d.dis:hover{background:transparent}
.rpop-d.in-range{background:rgba(59,130,246,.18);border-radius:0;color:var(--ink)}
html[data-theme="dark"] .rpop-d.in-range{background:rgba(59,130,246,.22)}
@media(prefers-color-scheme:dark){html:not([data-theme="light"]) .rpop-d.in-range{background:rgba(59,130,246,.22)}}
.rpop-d.sel{background:var(--accent);color:#fff;font-weight:500;border-radius:5px}

.rpop-actions{display:flex;justify-content:flex-end;margin:10px 4px 0;gap:6px}
.rpop-apply{background:var(--accent);color:#fff;border:none;padding:7px 18px;border-radius:6px;cursor:pointer;font:600 12.5px Inter,system-ui;letter-spacing:-.005em}
.rpop-apply:hover{filter:brightness(1.06)}
.rpop-apply:disabled{opacity:.4;cursor:not-allowed}
@media(max-width:640px){.rpop-cal{min-width:0}.rpop-months{grid-template-columns:1fr}.rpop{left:8px!important;right:8px;width:auto;max-width:calc(100vw - 16px)}}
.content{padding:22px 26px 70px;max-width:1200px}
.sub{color:var(--mut);font-size:12px}
.grid{display:grid;gap:14px}.g4{grid-template-columns:repeat(4,1fr)}.g3{grid-template-columns:repeat(3,1fr)}.g2{grid-template-columns:repeat(2,1fr)}
@media(max-width:980px){.g4,.g3{grid-template-columns:repeat(2,1fr)}.g2{grid-template-columns:1fr}}
@media(max-width:640px){
  .topmenu{display:flex}
  .sidebar{position:fixed;left:0;top:0;height:100vh;width:266px;transform:translateX(-100%);transition:transform .25s ease;z-index:100;box-shadow:0 0 40px rgba(0,0,0,.45)}
  .app.sb-open .sidebar{transform:none}
  .app.sb-open .sbscrim{opacity:1;pointer-events:auto}
  .app .sidebar .brand span,.app .sidebar .nav a .t,.app .sidebar .nav .cnt{display:inline}
  .app .sidebar .sbnote{display:block}
  .topbar{position:static;padding:10px 14px}
  .topbar h2{flex:1;margin:0}
  .content{padding:16px 13px 64px}
  .grid{grid-template-columns:1fr!important;gap:12px}
  .g4{grid-template-columns:1fr 1fr!important}
  .kpi .v{font-size:23px}.hero .hv{font-size:34px}
  .hero{flex-direction:column;align-items:flex-start;gap:12px;padding:16px}.hero .hl{min-width:0}
  .card{padding:15px;overflow-x:auto}
  .heat{overflow-x:auto}.hrow{min-width:max-content}
  table{min-width:0}
}
.card{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:18px;box-shadow:0 1px 3px rgba(20,30,60,.05)}
.card h3{margin:0 0 12px;font-size:12px;letter-spacing:.05em;text-transform:uppercase;color:var(--mut)}
.kpi .v{font-size:30px;font-weight:600;letter-spacing:-.01em;color:var(--ink)}
.kpi .l{color:var(--mut);font-size:12px;margin-top:2px}
.delta{font-size:12px;font-weight:600;margin-left:8px}.up{color:var(--good)}.down{color:var(--bad)}.flat{color:var(--mut)}
.hero{display:flex;gap:22px;align-items:center;padding:20px 22px}.hero .hl{min-width:190px}.hero .hc{flex:1;min-width:0}
.hero .hc svg{max-height:160px;display:block}
.hero .hv{font-size:42px;font-weight:600;letter-spacing:-.02em;line-height:1.05;margin:4px 0}
.donut{align-items:center}.donut svg{flex-shrink:0}
table{width:100%;border-collapse:collapse;font-size:13px}th,td{text-align:left;padding:8px 9px;border-bottom:1px solid var(--line);vertical-align:middle}
th{color:var(--mut);font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:.04em}
td.num{text-align:right;font-variant-numeric:tabular-nums;color:var(--ink);font-weight:600}
.pill{display:inline-block;padding:2px 9px;border-radius:999px;font-size:11px;font-weight:700}.pill.warn{background:#fef3c7;color:#92600a}
.s-None,.s-Low,.s-HEALTHY,.s-LOW{background:#dcfce7;color:#15803d}
.s-Medium,.s-MODERATE,.s-MEDIUM{background:#fef3c7;color:#92600a}
.s-High,.s-HIGH{background:#fee2e2;color:#b91c1c}
a{color:var(--blue);text-decoration:none}a:hover{text-decoration:underline}
.muted{color:var(--mut)}.tag{display:inline-block;background:var(--btn-alt);border:1px solid var(--line);border-radius:6px;padding:3px 8px;margin:2px;font-size:12px}
details{margin-top:6px}summary{cursor:pointer;color:var(--blue);font-size:12px}
.ev{font-size:12px;color:var(--mut);border-left:2px solid var(--line);padding:4px 0 4px 10px;margin:6px 0}
svg text{fill:var(--mut);font-size:10px}
g.ptg{cursor:pointer}g.ptg:hover .pt{r:5}.pt-hit{fill:transparent}
.legend{font-size:11px;color:var(--mut);display:flex;gap:14px;flex-wrap:wrap;margin-top:6px}
.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:5px;vertical-align:middle}
.btn{background:var(--accent);color:#fff;border:none;border-radius:8px;padding:8px 15px;font-weight:600;cursor:pointer;font-size:13px;text-decoration:none}
.btn.alt{background:var(--btn-alt);color:var(--ink)}.btn:hover{filter:brightness(1.05)}
/* donut */
.donut{display:flex;align-items:center;gap:18px}.lcol{font-size:13px}.lcol .lg{margin:5px 0}
/* word cloud */
.wc-wrap{display:flex;flex-wrap:wrap;gap:4px 12px;align-items:center;line-height:1.3}.wc{font-weight:600}
/* heatmap */
.heat{display:flex;flex-direction:column;gap:3px}.hrow{display:flex;align-items:center;gap:3px}
.hlab{width:30px;font-size:10px;color:var(--mut)}.hcell{flex:1;min-width:7px;height:14px;border-radius:2px;box-shadow:inset 0 0 0 1px rgba(40,55,90,.08)}
/* author bars */
.abar{height:7px;background:var(--btn-alt);border-radius:4px;overflow:hidden}.abar span{display:block;height:100%;background:var(--accent)}
/* mentions feed */
.mention{display:flex;gap:11px;padding:11px 0;border-bottom:1px solid var(--line)}.mention:last-child{border:none}
.av{width:34px;height:34px;border-radius:50%;flex-shrink:0;color:#fff;font-weight:700;display:flex;align-items:center;justify-content:center;font-size:14px;position:relative;overflow:hidden}
.av img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}
.mb{min-width:0}.mh{font-size:12px;font-weight:600}.mt{margin:2px 0}.mm{font-size:11px}
.sdot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-left:5px;vertical-align:middle}
.bar{height:8px;border-radius:4px;background:var(--btn-alt);overflow:hidden;display:flex}
#tip{position:absolute;display:none;z-index:60;background:#fff;border:1px solid var(--line);border-radius:8px;padding:8px 11px;font-size:12px;pointer-events:none;box-shadow:0 8px 24px rgba(20,30,60,.16);max-width:220px}
#tip .nm{color:var(--mut);font-size:11px;text-transform:uppercase;letter-spacing:.05em}
#tip .vv{font-size:18px;font-weight:700;color:var(--ink)}#tip .wn{color:var(--blue);font-size:12px}
.warnbox{border:1px solid var(--warn);background:#fff7e6;border-radius:12px;padding:13px 15px;margin-bottom:14px;font-size:13px}
.infobox{display:flex;gap:14px;align-items:flex-start;border:1px solid rgba(59,130,246,.28);background:linear-gradient(180deg,rgba(59,130,246,.06),rgba(59,130,246,.02));border-radius:14px;padding:14px 18px;margin-bottom:18px;font-size:13.5px;color:var(--ink)}
.infobox .ibi{display:flex;align-items:center;justify-content:center;width:34px;height:34px;border-radius:50%;background:rgba(59,130,246,.14);color:var(--accent);flex-shrink:0;margin-top:1px}
.infobox .ibi svg{width:18px;height:18px}
.infobox .ibt{font-size:13px;font-weight:700;letter-spacing:.02em;color:var(--ink);margin:0 0 2px}
.infobox .ibd{color:var(--mut);line-height:1.5;font-size:13px}
.infobox .ibchips{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}
.infobox .ibchip{font-size:11px;padding:2px 9px;border-radius:999px;background:var(--btn-alt);color:var(--mut);font-weight:500}
.infobox .ibchip.on{background:rgba(34,197,94,.14);color:#15803d}
html[data-theme="dark"] .infobox .ibchip.on{color:#86efac}
@media (prefers-color-scheme: dark){html:not([data-theme="light"]) .infobox .ibchip.on{color:#86efac}}
.appfoot{position:fixed;left:0;right:0;bottom:0;z-index:50;display:flex;align-items:center;gap:12px;padding:3px 26px;color:var(--ink);font-size:12px;line-height:1.2;background:linear-gradient(180deg,rgba(255,255,255,.38),rgba(255,255,255,.16));-webkit-backdrop-filter:blur(16px) saturate(180%);backdrop-filter:blur(2px) saturate(180%) url(#glassFoot);border-top:1px solid rgba(255,255,255,.7);box-shadow:0 -8px 30px rgba(20,30,60,.14),inset 0 1px 0 rgba(255,255,255,.85),inset 0 -1px 0 rgba(255,255,255,.25)}
.appfoot .fbrand{font-weight:600;color:var(--ink)}
.appfoot .built{margin:0 auto;position:relative;display:inline-flex;align-items:center;gap:8px;cursor:default}
.appfoot .built .xlink{display:inline-flex;border-radius:50%;transition:transform .15s,box-shadow .15s}
.appfoot .built .xlink:hover{transform:scale(1.12);box-shadow:0 0 0 3px rgba(59,130,246,.35)}
.appfoot .built img{display:block;width:16px;height:16px;border-radius:50%;object-fit:cover;border:1px solid var(--line);cursor:pointer}
.appfoot .built .ftip{position:absolute;bottom:150%;left:50%;transform:translateX(-50%);white-space:nowrap;background:#1d2540;color:#fff;padding:7px 11px;border-radius:8px;font-size:12px;opacity:0;pointer-events:none;transition:opacity .15s;box-shadow:0 6px 20px rgba(20,30,60,.25)}
.appfoot .built .ftip::after{content:"";position:absolute;top:100%;left:50%;transform:translateX(-50%);border:5px solid transparent;border-top-color:#1d2540}
.appfoot .built:hover .ftip{opacity:1}
.appfoot .live{margin-left:auto;display:inline-flex;align-items:center;gap:7px}
.appfoot .live .dot{width:9px;height:9px;border-radius:50%;background:var(--good);box-shadow:0 0 0 3px rgba(34,197,94,.18)}
.appfoot:hover{cursor:none}
/* Theme swap: CoD safe-zone-style diagonal reveal from top-right corner */
::view-transition-old(root){animation:none;z-index:1}
::view-transition-new(root){animation:hi-wipe-corner 720ms cubic-bezier(.65,.05,.36,1);z-index:2}
@keyframes hi-wipe-corner{from{clip-path:circle(0% at 100% 0%)}to{clip-path:circle(150% at 100% 0%)}}
@media (prefers-reduced-motion: reduce){::view-transition-new(root){animation-duration:.01ms}}
/* liquid-glass water bubble that trails the cursor over the footer (Chromium refraction; baked-in "Thick glass" params) */
#gbubble{position:fixed;left:0;top:0;width:54px;height:54px;border-radius:50%;pointer-events:none;z-index:60;opacity:0;transform:translate(-50%,-50%) scale(.5);transition:opacity .2s ease,transform .2s cubic-bezier(.2,.9,.3,1.2);-webkit-backdrop-filter:blur(.5px) brightness(1.05);backdrop-filter:blur(.4px) brightness(1.06) saturate(115%) url(#gbubbleFilter);box-shadow:inset 1.6px 1.6px 5px rgba(255,255,255,.75),inset -2px -2px 7px rgba(0,0,0,.22),0 8px 20px rgba(20,30,60,.28);border:1px solid rgba(255,255,255,.4)}
#gbubble.on{opacity:1;transform:translate(-50%,-50%) scale(1)}
#gbubble::after{content:"";position:absolute;top:18%;left:24%;width:30%;height:22%;border-radius:50%;background:radial-gradient(circle at 35% 35%,rgba(255,255,255,.95),rgba(255,255,255,0) 70%);filter:blur(.4px)}
@media print{.sidebar,.topbar,#gbubble{display:none!important}.content{max-width:none;padding-bottom:0}body{background:#fff}.card{break-inside:avoid}
  a[href]{color:#1d4ed8!important;text-decoration:underline}
  .appfoot .built .xlink{box-shadow:none!important;transform:none!important}
  .appfoot{position:static;margin-top:26px;padding:10px 0 2px;background:none!important;color:#555;border-top:1px solid #ccc;-webkit-backdrop-filter:none!important;backdrop-filter:none!important;box-shadow:none;-webkit-print-color-adjust:exact;print-color-adjust:exact}
  .appfoot .fbrand{color:#111}.appfoot .built{color:#333}.appfoot .built .ftip{display:none}
  .appfoot .built img{width:18px;height:18px;-webkit-print-color-adjust:exact;print-color-adjust:exact}}
</style></head><body>
<div class="app">
  <div id="sbScrim" class="sbscrim"></div>
  <aside class="sidebar">
    <div class="sbtop">
      <button id="sbToggle" class="sbtoggle" type="button" aria-label="Toggle sidebar" title="Collapse sidebar"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="16" rx="2"/><line x1="9" y1="4" x2="9" y2="20"/></svg></button>
      <div class="brand"><img class="logo" src="public/log.png" alt="ℏIntel"><span><span class="h">ℏ</span>Intel</span></div>
    </div>
    <nav class="nav" id="nav">
      <a data-v="dashboard" class="active"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="9" rx="1"/><rect x="14" y="3" width="7" height="5" rx="1"/><rect x="14" y="12" width="7" height="9" rx="1"/><rect x="3" y="16" width="7" height="5" rx="1"/></svg><span class="t">Dashboard</span> <span class="cnt" id="c-dash"></span></a>
      <a data-v="mentions"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="4"/><path d="M16 8v5a3 3 0 0 0 6 0v-1a10 10 0 1 0-4 8"/></svg><span class="t">Mentions</span> <span class="cnt" id="c-ment"></span></a>
      <a data-v="moderation"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="M12 8v4"/><path d="M12 16h.01"/></svg><span class="t">Moderation</span> <span class="cnt" id="c-mod"></span></a>
      <a data-v="trends"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/></svg><span class="t">Trends</span> <span class="cnt" id="c-tr"></span></a>
    </nav>
    <div id="sbCtrlMount" class="sbctrls"></div>
    <div class="sbnote">intels.app · r/Hedera community intelligence<br>Source: Arctic-Shift archive<br>Generated __GENERATED__ · since __TRACKERSTART__</div>
  </aside>
  <div class="main">
    <div class="topbar">
      <button id="mOpen" class="topmenu" type="button" aria-label="Open sidebar" title="Open sidebar"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="16" rx="2"/><line x1="9" y1="4" x2="9" y2="20"/></svg></button>
      <h2 id="viewTitle">Dashboard</h2>
      <div class="tbctrls" id="tbctrls">
        <span class="sub" id="periodHint"></span>
        <button class="rangebtn" id="periodBtn" type="button"><svg class="rb-i" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg><span class="rb-l">Period</span><svg class="rb-c" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg></button>
        <span class="sub" id="compareHint"></span>
        <button class="rangebtn" id="compareBtn" type="button"><svg class="rb-i" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18M6 12h12M10 18h4"/></svg><span class="rb-l">Compare</span><svg class="rb-c" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg></button>
        <button class="theme-toggle" id="themeBtn" type="button" title="Toggle theme" aria-label="Toggle theme"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg></button>
        <a class="btn alt" href="weekly.html">📋 Weekly</a>
        <button class="btn" onclick="exportPDF()">⬇ PDF</button>
      </div>
    </div>
    <div id="rangePop" class="rpop" style="display:none">
      <div class="rpop-presets" id="rpopPresets"></div>
      <div class="rpop-cal" id="rpopCal" style="display:none">
        <div class="rpop-tabs"><button class="rpop-tab active" data-tab="start" type="button">Start</button><button class="rpop-tab" data-tab="end" type="button">End</button></div>
        <div class="rpop-cal-nav"><button id="rpopPrev" type="button" aria-label="Previous">‹</button><button id="rpopNext" type="button" aria-label="Next">›</button></div>
        <div id="rpopMonths" class="rpop-months"></div>
        <div class="rpop-actions"><button id="rpopApply" type="button" class="rpop-apply">Apply</button></div>
      </div>
    </div>
    <div class="content"><div id="view"></div>
      <p class="sub" style="margin-top:24px">Soft/keyword metrics (risk, themes, sentiment) are regex proxies over titles + comment bodies — not verified mod actions. Bans/reports/peak-online require the Reddit mod dashboard.</p>
      <div class="appfoot">
        <span class="fbrand"><span class="h">ℏ</span>Intel · © 2026</span>
        <span class="built"><span class="ftip">Report issue or suggest ideas to henry</span>Built by henry <a class="xlink" href="https://x.com/harryfiedwrld" target="_blank" rel="noopener" aria-label="henry on X"><img src="public/henry.jpg" alt="henry" loading="lazy"></a></span>
        <span class="live"><span class="dot"></span>Live Data</span>
      </div>
    </div>
  </div>
</div>
<!-- displacement-map housing for the liquid-glass footer (refracts the backdrop; Chromium only) -->
<svg id="glassFootSvg" width="0" height="0" style="position:fixed;bottom:0;pointer-events:none" aria-hidden="true"></svg>
<!-- cursor-following liquid-glass water bubble (shown only over the footer) -->
<div id="gbubble" aria-hidden="true"></div>
<svg id="gbubbleSvg" width="0" height="0" style="position:fixed;pointer-events:none" aria-hidden="true"></svg>
<script>
// Water-bubble cursor for the footer. A small circular lens refracts the live backdrop through an
// feDisplacementMap (Chromium); it smoothly trails the pointer with a gentle float so it reads like
// a floating drop of liquid glass. Glass params are HARD-SET to the "Thick glass" preset — not tunable.
(function(){
  const foot=document.querySelector('.appfoot'), b=document.getElementById('gbubble'), svg=document.getElementById('gbubbleSvg');
  if(!foot||!b||!svg) return;
  // baked-in "Thick glass": depth(scale) 120 · splay(rim) 2 · feather 30 · curve 3 · glint 60
  const D=54, RIM=2, FEATHER=30, CURVE=3, SCALE=120, BOOST=.8, c255=v=>v<0?0:v>255?255:v;
  (function buildFilter(){
    const cv=document.createElement('canvas'); cv.width=cv.height=D;
    const ctx=cv.getContext('2d'), img=ctx.createImageData(D,D), px=img.data, cx=D/2, cy=D/2, r=D/2-1;
    const sdf=(x,y)=>Math.hypot(x-cx,y-cy)-r;                 // circle edge
    for(let y=0;y<D;y++)for(let x=0;x<D;x++){
      const s=sdf(x+.5,y+.5);
      const gx=sdf(x+1.5,y+.5)-sdf(x-.5,y+.5), gy=sdf(x+.5,y+1.5)-sdf(x+.5,y-.5);
      const len=Math.hypot(gx,gy)||1, nx=gx/len, ny=gy/len;
      const span=s<0?RIM+FEATHER:RIM;
      let amt=Math.max(0,1-Math.abs(s)/span);
      amt=amt*amt*amt*(amt*(amt*6-15)+10);                   // smootherstep
      amt=Math.pow(amt,CURVE);
      const i=(y*D+x)*4;
      px[i]=c255(Math.round(127.5-nx*amt*127*BOOST));
      px[i+1]=c255(Math.round(127.5-ny*amt*127*BOOST));
      px[i+2]=128; px[i+3]=255;
    }
    ctx.putImageData(img,0,0);
    const url=cv.toDataURL('image/png');
    svg.innerHTML=`<defs><filter id="gbubbleFilter" x="-20%" y="-20%" width="140%" height="140%" filterUnits="userSpaceOnUse" color-interpolation-filters="sRGB">`+
      `<feImage href="${url}" x="0" y="0" width="${D}" height="${D}" preserveAspectRatio="none" result="m"/>`+
      `<feDisplacementMap in="SourceGraphic" in2="m" scale="${SCALE}" xChannelSelector="R" yChannelSelector="G"/></filter></defs>`;
  })();
  // smooth trailing + gentle float so it feels like liquid, not a hard-locked cursor
  let tx=0,ty=0,cxp=0,cyp=0,active=false,raf=0;
  function tick(t){
    cxp+=(tx-cxp)*.22; cyp+=(ty-cyp)*.22;                   // ease toward pointer (watery lag)
    const bob=Math.sin(t/420)*2.2;                          // gentle vertical float
    b.style.left=cxp+'px'; b.style.top=(cyp+bob)+'px';
    raf=active?requestAnimationFrame(tick):0;
  }
  foot.addEventListener('pointerenter',e=>{tx=cxp=e.clientX; ty=cyp=e.clientY; active=true; b.classList.add('on'); if(!raf)raf=requestAnimationFrame(tick);});
  foot.addEventListener('pointermove',e=>{tx=e.clientX; ty=e.clientY;});
  foot.addEventListener('pointerleave',()=>{active=false; b.classList.remove('on');});
})();
</script>
<script>
// Liquid-glass footer: build a rounded-rect edge normal-map sized to the footer, feed it to an
// feDisplacementMap, and apply via backdrop-filter:url() so the live page refracts through the bar.
// Renders in Chromium; Safari/Firefox fall back to the frosted -webkit-backdrop-filter blur above.
(function(){
  const foot=document.querySelector('.appfoot'), svg=document.getElementById('glassFootSvg');
  if(!foot||!svg) return;
  const RADIUS=18, RIM=26, CURVE=1.6, SCALE=22, c255=v=>v<0?0:v>255?255:v;
  function buildMap(w,h){
    const cv=document.createElement('canvas'); cv.width=w; cv.height=h;
    const ctx=cv.getContext('2d'), img=ctx.createImageData(w,h), px=img.data;
    const hx=w/2, hy=h/2, r=Math.min(RADIUS,hy-1);
    const sdf=(x,y)=>{const qx=Math.abs(x-hx)-(hx-r),qy=Math.abs(y-hy)-(hy-r);
      const ox=Math.max(qx,0),oy=Math.max(qy,0);return Math.hypot(ox,oy)+Math.min(Math.max(qx,qy),0)-r;};
    for(let y=0;y<h;y++)for(let x=0;x<w;x++){
      const s=sdf(x+0.5,y+0.5);
      const gx=sdf(x+1.5,y+0.5)-sdf(x-0.5,y+0.5), gy=sdf(x+0.5,y+1.5)-sdf(x+0.5,y-0.5);
      const len=Math.hypot(gx,gy)||1, nx=gx/len, ny=gy/len;
      let amt=Math.max(0,1-Math.abs(s)/RIM);
      amt=amt*amt*amt*(amt*(amt*6-15)+10);            // smootherstep
      amt=Math.pow(amt,CURVE);
      const i=(y*w+x)*4;
      px[i]=c255(Math.round(127.5-nx*amt*127));        // R = x displacement
      px[i+1]=c255(Math.round(127.5-ny*amt*127));      // G = y displacement
      px[i+2]=128; px[i+3]=255;
    }
    ctx.putImageData(img,0,0); return cv.toDataURL('image/png');
  }
  let lastW=0,lastH=0;
  function build(){
    const w=Math.round(foot.offsetWidth), h=Math.round(foot.offsetHeight);
    if(!w||!h||(w===lastW&&h===lastH)) return; lastW=w; lastH=h;
    const url=buildMap(w,h);
    svg.innerHTML=`<defs><filter id="glassFoot" x="0" y="0" width="100%" height="100%" filterUnits="userSpaceOnUse" color-interpolation-filters="sRGB">`+
      `<feImage href="${url}" x="0" y="0" width="${w}" height="${h}" preserveAspectRatio="none" result="m"/>`+
      `<feDisplacementMap in="SourceGraphic" in2="m" scale="${SCALE}" xChannelSelector="R" yChannelSelector="G"/></filter></defs>`;
  }
  build();
  let t; addEventListener('resize',()=>{clearTimeout(t);t=setTimeout(build,150);});
})();
</script>
<script>
const DATA = __DATA__;
const $ = s => document.querySelector(s);
const esc = s => (s==null?'':String(s)).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const rlink = p => p && p!=='nan' && p!=='' ? 'https://reddit.com'+p : null;

// -------------------------------------------------- Common Room–style range picker
// Selection model: each "slot" (period / compare) holds either
//   { kind:'preset', idx:i }                        → DATA.presets[i]
//   { kind:'custom', start:'YYYY-MM-DD', end:... }  → computeRange(start,end)
//   { kind:'none' }   (compare slot only)
const FMT = d => { const dt = new Date(d+'T12:00:00'); return dt.toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric'}); };
const dayStr = d => d.toISOString().slice(0,10);
const $$ = s => document.querySelectorAll(s);

// Build a metrics-shaped object from daily buckets for any [start..end] range.
function computeRange(start, end){
  const dates = [], a = new Date(start+'T12:00:00'), b = new Date(end+'T12:00:00');
  for(let t = +a; t <= +b; t += 86400000) dates.push(dayStr(new Date(t)));
  let posts=0, comments=0, sp=0, sn=0, urs=0, urc=0;
  const authP = new Set(), authC = new Set(), tm = {}, daily = [], heatTemp = Array(7).fill(0).map(()=>Array(24).fill(0));
  const authorAgg = {}; const topAll = [];
  dates.forEach(d => {
    const bk = DATA.daily[d]; if(!bk) { daily.push({d: d.slice(5), c: 0}); return; }
    posts += bk.p; comments += bk.c; sp += bk.sp; sn += bk.sn; urs += bk.urs; urc += bk.urc;
    bk.ap.forEach(a => authP.add(a)); bk.ac.forEach(a => authC.add(a));
    Object.entries(bk.tm).forEach(([k,v]) => tm[k] = (tm[k]||0) + v);
    Object.entries(bk.au || {}).forEach(([a,v]) => {
      if(!authorAgg[a]) authorAgg[a] = {author:a, posts:0, score:0};
      authorAgg[a].posts += v.posts; authorAgg[a].score += v.score;
    });
    (bk.tp||[]).forEach(p => topAll.push(p));
    daily.push({d: d.slice(5), c: bk.p});
    const wd = new Date(d+'T12:00:00').getUTCDay(); const dow = (wd + 6) % 7;
    if(bk.p) heatTemp[dow][12] += bk.p;
  });
  authC.delete('[deleted]'); authP.delete('[deleted]');
  const contribs = new Set([...authP, ...authC]);
  let newCount = 0;
  contribs.forEach(a => { const fs = DATA.author_first_seen[a]; if(fs && fs >= start) newCount++; });
  const returning = contribs.size - newCount;
  const totP = Math.max(posts, 1);
  topAll.sort((x,y) => y.score - x.score);
  const topAuthors = Object.values(authorAgg).sort((x,y) => y.posts - x.posts || y.score - x.score).slice(0, 8);
  return {
    start, end, days: dates.length, label: FMT(start)+' – '+FMT(end),
    posts, comments,
    posts_per_day: Math.round((posts/dates.length)*10)/10,
    comments_per_post: posts ? Math.round((comments/posts)*10)/10 : 0,
    avg_upvote_ratio: urc ? Math.round((urs/urc)*1000)/10 : 0,
    contributors: contribs.size, new_to_tracker: newCount, returning,
    sentiment: {pos: Math.round(sp/totP*100), neu: Math.round((totP-sp-sn)/totP*100), neg: Math.round(sn/totP*100)},
    type_mix: tm, daily, heat: heatTemp, heat_max: Math.max(...heatTemp.flat(), 0),
    top_authors: topAuthors,
    top_posts: topAll.slice(0,5), top_post: topAll[0] || null,
    theme_weights: [], feed: topAll.slice(0,16).map(p => ({author:p.author,date:p.date,title:p.title,score:p.score,comments:p.comments,link:p.link,sentiment:p.sentiment,avatar:''})),
    issues_tracked: 0, resolved: 0, resolution_rate: 0, escalation_count: 0, escalation_rows: [], avg_response_hrs: null,
    sdk_questions: 0, code_posts: 0, docs_links: 0, github_links: 0, ai_studio: 0, hackathon: 0,
    recurring: [], gaps: [], risks: [], risk_evidence: {}, posts_removed: 0,
    health: 'MODERATE', risk_level: 'LOW',
    pct_zero: 0, growth_pct: 0, avg_post_upvotes: 0, avg_post_comments: 0, mod_upvoted_100: false,
    themes: [], comment_data: true, custom: true,
  };
}

let periodSel = {kind:'preset', idx: DATA.default_preset};
let compareSel = {kind:'none'};
function scopeOf(sel){
  if(!sel || sel.kind === 'none') return null;
  if(sel.kind === 'preset') return DATA.presets[sel.idx];
  if(sel.kind === 'custom') return computeRange(sel.start, sel.end);
  return null;
}
function selLabel(sel){
  if(!sel || sel.kind==='none') return 'No comparison';
  if(sel.kind==='preset') return DATA.presets[sel.idx].label;
  if(sel.kind==='custom') return FMT(sel.start)+' – '+FMT(sel.end);
}
function selHint(sel){ const s = scopeOf(sel); return s ? s.start+' → '+s.end : ''; }

function delta(cur,prev,goodUp=true,pct=false){
  if(prev===null||prev===undefined||prev===0||cur===null) return '';
  const d = cur-prev; if(Math.abs(d)<1e-9) return '<span class="delta flat">±0</span>';
  const dir = d>0; const good = goodUp?dir:!dir;
  const arrow = dir?'▲':'▼'; const cls = good?'up':'down';
  const val = pct? d.toFixed(1)+'pp' : (d>0?'+':'')+ (Number.isInteger(d)?d:d.toFixed(1));
  return `<span class="delta ${cls}">${arrow} ${val}</span>`;
}
function kpi(label,val,prev,suffix='',goodUp=true){
  return `<div class="card kpi"><div class="v">${val}${suffix}${delta(val,prev,goodUp)}</div><div class="l">${label}</div></div>`;
}
// interactive multi-period SVG line chart — hover any point to read its value
function trend(metricFn, label, color, suffix=''){
  const ys = DATA.periods.map(metricFn);
  const W=260,H=78,pad=18; const mx=Math.max(...ys,1),mn=Math.min(...ys,0);
  const X=i=>pad+i*((W-2*pad)/Math.max(ys.length-1,1));
  const Y=v=>H-pad-8-((v-mn)/Math.max(mx-mn,1))*(H-2*pad-8);
  const pts=ys.map((v,i)=>`${X(i)},${Y(v)}`).join(' ');
  const labs=DATA.periods.map((p,i)=>`<text x="${X(i)}" y="${H-3}" text-anchor="middle">${p.end.slice(5)}</text>`).join('');
  const groups=ys.map((v,i)=>{
    const p=DATA.periods[i];
    const meta=`data-name="${esc(label)}" data-win="${p.start} → ${p.end}" data-val="${v}${suffix}"`;
    return `<g class="ptg"><circle class="pt-hit" cx="${X(i)}" cy="${Y(v)}" r="11" ${meta}/><circle class="pt" cx="${X(i)}" cy="${Y(v)}" r="2.7" fill="${color}" ${meta}/></g>`;
  }).join('');
  return `<div class="card"><h3>${label}</h3><svg viewBox="0 0 ${W} ${H}" width="100%"><polyline fill="none" stroke="${color}" stroke-width="2" points="${pts}"/>${groups}${labs}</svg></div>`;
}
// "This week vs annual average" — one card per metric: week value, the year's
// mean, and the % gap so a mod instantly sees if a week is above/below the norm.
function annualCard(label,weekVal,annVal,suffix='',goodUp=true){
  let badge='';
  if(annVal!==undefined&&annVal!==null&&annVal!==0){
    const pct=((weekVal-annVal)/Math.abs(annVal))*100;
    const dir=pct>0; const good=goodUp?dir:!dir;
    const cls=Math.abs(pct)<1?'flat':(good?'up':'down');
    const arrow=Math.abs(pct)<1?'±':(dir?'▲':'▼');
    badge=`<span class="delta ${cls}">${arrow} ${Math.abs(pct).toFixed(0)}% vs yr avg</span>`;
  }
  return `<div class="card kpi"><div class="v">${weekVal}${suffix}${badge}</div>
    <div class="l">${label}<br><span class="muted">yr avg ${annVal!==undefined?annVal+suffix:'—'}</span></div></div>`;
}
// Year-over-year overlay: semi-monthly series plotted by day-of-year so the two
// years' periods line up on a shared Jan→Dec axis, one line per year.
function yoy(metricFn,label,suffix=''){
  const years=Object.keys(DATA.annual).sort();
  const cols=['#a855f7','#818cf8','#34d399','#fbbf24','#f472b6'];
  const byYear={}; years.forEach(y=>byYear[y]=[]);
  DATA.periods.forEach(p=>{const y=p.end.slice(0,4); if(byYear[y]){
    const d=new Date(p.end); const doy=Math.round((d-new Date(+y,0,1))/864e5);
    byYear[y].push([doy,metricFn(p),p.start.slice(5)+'→'+p.end.slice(5)]);}});
  const all=DATA.periods.map(metricFn); const mx=Math.max(...all,1),mn=Math.min(...all,0);
  const W=540,H=120,pad=24;
  const X=w=>pad+(w/365)*(W-2*pad);
  const Y=v=>H-pad-((v-mn)/Math.max(mx-mn,1))*(H-2*pad);
  let lines='',grp='',leg='';
  years.forEach((y,yi)=>{const c=cols[yi%cols.length];
    const pts=byYear[y].sort((a,b)=>a[0]-b[0]).map(([w,v])=>`${X(w).toFixed(1)},${Y(v).toFixed(1)}`).join(' ');
    if(byYear[y].length) lines+=`<polyline fill="none" stroke="${c}" stroke-width="2" points="${pts}"/>`;
    byYear[y].forEach(([w,v,lbl])=>{const meta=`data-name="${esc(label)} ${y}" data-win="${lbl} · ${y}" data-val="${v}${suffix}"`;
      grp+=`<g class="ptg"><circle class="pt-hit" cx="${X(w)}" cy="${Y(v)}" r="9" ${meta}/><circle class="pt" cx="${X(w)}" cy="${Y(v)}" r="2.4" fill="${c}" ${meta}/></g>`;});
    leg+=`<span><span class="dot" style="background:${c}"></span>${y}</span>`;});
  const ax=[[0,'Jan'],[90,'Apr'],[181,'Jul'],[273,'Oct'],[365,'Dec']].map(([w,m])=>`<text x="${X(w)}" y="${H-6}" text-anchor="middle">${m}</text>`).join('');
  return `<div class="card"><h3>${label} — year over year</h3>
    <svg viewBox="0 0 ${W} ${H}" width="100%">${lines}${grp}${ax}</svg>
    <div class="legend">${leg}</div></div>`;
}
// Hedera-style section header: small purple eyebrow + large thin heading.
function sec(eyebrow,title){return `<div class="eyebrow">${eyebrow}</div><div class="section-title">${title}</div>`;}
function evBlock(rows){
  if(!rows||!rows.length) return '<div class="muted" style="font-size:12px">No matches.</div>';
  return rows.map(r=>{const l=rlink(r.link);return `<div class="ev"><b>${esc(r.date)}</b> · u/${esc(r.author)} · ${r.where}${l?` · <a href="${l}" target="_blank">link</a>`:''}<br>“${esc(r.text)}”</div>`;}).join('');
}
const CPAL=['#3b82f6','#8b5cf6','#22c55e','#f59e0b','#ec4899','#14b8a6'];
function avColor(s){let h=0;for(const c of (s||'?')) h=(h*31+c.charCodeAt(0))%360;return `hsl(${h},52%,55%)`;}

// hero area chart from daily post counts
function area(daily){
  if(!daily||!daily.length) return '<div class="muted">No daily data.</div>';
  const ys=daily.map(d=>d.c); const W=1000,H=140,pad=6; const mx=Math.max(...ys,1);
  const X=i=>pad+i*((W-2*pad)/Math.max(daily.length-1,1));
  const Y=v=>H-20-(v/mx)*(H-34);
  const line=daily.map((d,i)=>`${X(i).toFixed(1)},${Y(d.c).toFixed(1)}`).join(' ');
  const fill=`${X(0).toFixed(1)},${H-20} ${line} ${X(daily.length-1).toFixed(1)},${H-20}`;
  const grp=daily.map((d,i)=>`<g class="ptg"><circle class="pt-hit" cx="${X(i)}" cy="${Y(d.c)}" r="9" data-name="Posts" data-win="${esc(d.d)}" data-val="${d.c}"/><circle class="pt" cx="${X(i)}" cy="${Y(d.c)}" r="2.4" fill="#3b82f6" data-name="Posts" data-win="${esc(d.d)}" data-val="${d.c}"/></g>`).join('');
  const labs=daily.map((d,i)=>i%Math.ceil(daily.length/7||1)===0?`<text x="${X(i)}" y="${H-5}" text-anchor="middle">${esc(d.d)}</text>`:'').join('');
  return `<svg viewBox="0 0 ${W} ${H}" width="100%"><defs><linearGradient id="ag" x1="0" x2="0" y1="0" y2="1">
    <stop offset="0" stop-color="#3b82f6" stop-opacity=".30"/><stop offset="1" stop-color="#3b82f6" stop-opacity="0"/></linearGradient></defs>
    <polygon points="${fill}" fill="url(#ag)"/><polyline points="${line}" fill="none" stroke="#3b82f6" stroke-width="2"/>${grp}${labs}</svg>`;
}
function donut(title,segs,centerVal,centerSub){
  const total=segs.reduce((a,s)=>a+s.value,0)||1; const R=40,C=2*Math.PI*R; let off=0;
  const cv=centerVal!==undefined?centerVal:total; const cs=centerSub||'total';
  const rings=segs.filter(s=>s.value>0).map(s=>{const len=s.value/total*C;
    const c=`<circle r="${R}" cx="60" cy="60" fill="none" stroke="${s.color}" stroke-width="15" stroke-dasharray="${len.toFixed(2)} ${(C-len).toFixed(2)}" stroke-dashoffset="${(-off).toFixed(2)}" transform="rotate(-90 60 60)"/>`;
    off+=len; return c;}).join('');
  const leg=segs.map(s=>`<div class="lg"><span class="dot" style="background:${s.color}"></span>${esc(s.label)} <b>${Math.round(s.value/total*100)}%</b></div>`).join('');
  return `<div class="card"><h3>${esc(title)}</h3><div class="donut">
    <svg viewBox="0 0 120 120" width="106" height="106"><circle r="${R}" cx="60" cy="60" fill="none" stroke="#eef2fb" stroke-width="15"/>${rings}
    <text x="60" y="57" text-anchor="middle" style="fill:var(--ink);font-size:21px;font-weight:700">${cv}</text>
    <text x="60" y="73" text-anchor="middle" style="fill:var(--mut);font-size:9px">${esc(cs)}</text></svg>
    <div class="lcol">${leg}</div></div></div>`;
}
function wordcloud(tw){
  if(!tw||!tw.length) return '<div class="muted">No keywords.</div>';
  const mx=Math.max(...tw.map(x=>x.n),1);
  return '<div class="wc-wrap">'+tw.map((x,i)=>{const sz=13+Math.round((x.n/mx)*15);
    return `<span class="wc" style="font-size:${sz}px;color:${CPAL[i%CPAL.length]}" title="${x.n} mentions">${esc(x.t)}</span>`;}).join('')+'</div>';
}
function heatmap(heat,mx){
  const days=['Mon','Tue','Wed','Thu','Fri','Sat','Sun']; let h='<div class="heat">';
  heat.forEach((row,di)=>{h+=`<div class="hrow"><span class="hlab">${days[di]}</span>`;
    row.forEach((c,hi)=>{const a=mx?c/mx:0;const bg=a?`rgba(37,99,235,${(0.35+Math.sqrt(a)*0.65).toFixed(2)})`:'#e2e8f5';
      h+=`<span class="hcell" style="background:${bg}" title="${days[di]} ${hi}:00 · ${c} posts"></span>`;});h+='</div>';});
  h+='</div><div class="muted" style="font-size:11px;margin-top:7px">Posts by day-of-week × hour (UTC) · darker = busier</div>';
  return h;
}
function authorsList(a){
  if(!a||!a.length) return '<div class="muted">No authors.</div>';
  const mx=Math.max(...a.map(x=>x.posts),1);
  return '<table><tbody>'+a.map(x=>`<tr><td>u/${esc(x.author)}</td>
    <td style="width:46%"><div class="abar"><span style="width:${Math.round(x.posts/mx*100)}%"></span></div></td>
    <td class="num">${x.posts}</td><td class="muted" style="text-align:right">${x.score}↑</td></tr>`).join('')+'</tbody></table>';
}
function feedList(feed){
  if(!feed||!feed.length) return '<div class="muted">No mentions.</div>';
  const sc={positive:'#22c55e',negative:'#ef4444',neutral:'#94a3b8'};
  return feed.map(f=>{const l=rlink(f.link);const nm=(f.author||'?').replace('[deleted]','?');
    const img=f.avatar?`<img src="${esc(f.avatar)}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.remove()">`:'';
    return `<div class="mention"><div class="av" style="background:${avColor(nm)}">${esc(nm.slice(0,1).toUpperCase())}${img}</div>
    <div class="mb"><div class="mh">u/${esc(f.author)} <span class="muted">· ${esc(f.date)}</span><span class="sdot" style="background:${sc[f.sentiment]||'#94a3b8'}"></span></div>
    <div class="mt">${l?`<a href="${l}" target="_blank">${esc(f.title)}</a>`:esc(f.title)}</div>
    <div class="mm muted">${f.score}↑ · ${f.comments}💬</div></div></div>`;}).join('');
}
function topPostsTable(p){
  if(!(p.top_posts||[]).length) return '<div class="muted">No posts.</div>';
  return '<table><thead><tr><th>Title</th><th style="text-align:right">↑</th><th style="text-align:right">💬</th></tr></thead><tbody>'+
    p.top_posts.map(r=>{const l=rlink(r.link);return `<tr><td>${l?`<a href="${l}" target="_blank">${esc(r.title)}</a>`:esc(r.title)}</td><td class="num">${r.score}</td><td class="num">${r.comments}</td></tr>`;}).join('')+'</tbody></table>';
}
function partialBanner(p,q,cmp){
  if(p.comment_data && !(cmp&&!q.comment_data)) return '';
  const which=[!p.comment_data?'selected period':null,(cmp&&!q.comment_data)?'comparison period':null].filter(Boolean).join(' & ');
  return `<div class="warnbox"><b style="color:#b45309">⚠ Partial data — interpret with care.</b>
    <span class="muted">The ${which} has incomplete archived comments (Arctic-Shift gap / still backfilling), so comment-based metrics
    (Comments, Comments/post, Resolution, Escalations) read low and are <b>not</b> a real decline. Post & upvote metrics remain reliable.</span></div>`;
}

// ---------------- views ----------------
function viewDashboard(p,q,cmp){
  let h=partialBanner(p,q,cmp);
  h+=`<div class="card hero"><div class="hl"><div class="muted">Posts this period</div>
    <div class="hv">${p.posts}${delta(p.posts,q.posts)}</div>
    <div class="muted">${p.posts_per_day}/day · ${p.start} → ${p.end}</div></div>
    <div class="hc">${area(p.daily)}</div></div>`;
  h+='<div class="grid g4" style="margin-top:14px">';
  h+=kpi('Avg upvote ratio',p.avg_upvote_ratio,q.avg_upvote_ratio,'%');
  h+=kpi('Contributors',p.contributors,q.contributors);
  h+=kpi('Comments',p.comments,q.comments);
  h+=kpi('Resolution rate',p.resolution_rate,q.resolution_rate,'%');
  h+='</div>';
  h+='<div class="grid g3" style="margin-top:14px">';
  h+=donut('Sentiment',[{label:'Positive',value:p.sentiment.pos,color:'#22c55e'},{label:'Neutral',value:p.sentiment.neu,color:'#94a3b8'},{label:'Negative',value:p.sentiment.neg,color:'#ef4444'}],p.posts,'posts');
  h+=donut('Post type',Object.entries(p.type_mix||{}).map(([k,v],i)=>({label:k,value:v,color:CPAL[i%CPAL.length]})),p.posts,'posts');
  h+=donut('Contributors',[{label:'New',value:p.new_to_tracker,color:'#8b5cf6'},{label:'Returning',value:p.returning,color:'#3b82f6'}],p.contributors,'people');
  h+='</div>';
  h+='<div class="grid g2" style="margin-top:14px">';
  h+=`<div class="card"><h3>Topic cloud</h3>${wordcloud(p.theme_weights)}</div>`;
  h+=`<div class="card"><h3>Activity heatmap</h3>${heatmap(p.heat,p.heat_max)}</div>`;
  h+='</div>';
  h+='<div class="grid g2" style="margin-top:14px">';
  h+=`<div class="card"><h3>Top authors</h3>${authorsList(p.top_authors)}</div>`;
  h+=`<div class="card"><h3>Top posts by upvotes</h3>${topPostsTable(p)}</div>`;
  h+='</div>';
  return h;
}
function viewMentions(p){
  let h='<div class="grid" style="grid-template-columns:1.7fr 1fr;gap:14px">';
  h+=`<div class="card"><h3>Mentions feed — most recent posts</h3>${feedList(p.feed)}</div>`;
  h+=`<div class="card"><h3>Recurring / duplicate questions</h3>`+
    (p.recurring.length?'<table><tbody>'+p.recurring.map(r=>`<tr><td>${esc(r.title)}</td><td style="text-align:right"><span class="pill warn">×${r.count}</span></td></tr>`).join('')+'</tbody></table>':'<div class="muted">No repeated question topics.</div>')+'</div>';
  h+='</div>';
  return h;
}
function viewModeration(p,q,cmp){
  let h=partialBanner(p,q,cmp);
  h+='<div class="grid g4" style="margin-bottom:14px">';
  h+=`<div class="card kpi"><div class="v"><span class="pill s-${p.health}">${p.health}</span></div><div class="l">Community health</div></div>`;
  h+=`<div class="card kpi"><div class="v"><span class="pill s-${p.risk_level}">${p.risk_level}</span></div><div class="l">Overall risk level</div></div>`;
  h+=kpi('Issues tracked',p.issues_tracked,q.issues_tracked);
  h+=kpi('Resolution rate',p.resolution_rate,q.resolution_rate,'%');
  h+='</div>';
  const risksSorted=[...p.risks].sort((a,b)=>b.rank-a.rank);
  h+='<div class="card"><h3>Risk & moderation — severity · evidence · suggested action</h3><table><thead><tr><th>Risk</th><th>Severity</th><th style="text-align:right">Hits</th><th>Suggested action</th></tr></thead><tbody>';
  risksSorted.forEach(r=>{h+=`<tr><td><b>${esc(r.label)}</b><details><summary>evidence (${r.count})</summary>${evBlock(p.risk_evidence[r.key])}</details></td>
    <td><span class="pill s-${r.level}">${r.level}</span></td><td class="num">${r.count}</td><td class="muted">${esc(r.action)}</td></tr>`;});
  h+=`<tr><td>Posts removed (deleted/removed)</td><td>—</td><td class="num">${p.posts_removed}</td><td class="muted">Review removal reasons; confirm against mod log.</td></tr>`;
  h+='</tbody></table></div>';
  h+=`<div class="card" style="margin-top:14px"><h3>Escalation queue — unanswered question-posts &gt;24h (${p.escalation_count})</h3>`;
  if(p.escalation_rows.length){h+='<table><thead><tr><th>Date</th><th>Author</th><th>Question post</th></tr></thead><tbody>';
    p.escalation_rows.forEach(r=>{const l=rlink(r.link);h+=`<tr><td>${esc(r.date)}</td><td>u/${esc(r.author)}</td><td>${l?`<a href="${l}" target="_blank">${esc(r.title)}</a>`:esc(r.title)}</td></tr>`;});h+='</tbody></table>';}
  else h+='<div class="muted">Nothing pending — all tracked questions received a reply.</div>';
  h+=`<div class="sub" style="margin-top:8px">“Answered” = received ≥1 captured comment. Avg first-response: ${p.avg_response_hrs!==null?p.avg_response_hrs+' hrs':'n/a'}.</div></div>`;
  h+='<div class="card" style="margin-top:14px"><h3>Gaps identified</h3>'+(p.gaps.length?'<table><tbody>'+p.gaps.map(g=>`<tr><td><b>${esc(g.gap)}</b><div class="muted">${esc(g.detail)}</div></td><td class="muted">${esc(g.action)}</td></tr>`).join('')+'</tbody></table>':'<div class="muted">No major gaps flagged.</div>')+'</div>';
  return h;
}
function viewTrends(p,q,cmp){
  let h=''; const yr=p.end.slice(0,4); const ann=DATA.annual[yr];
  if(ann){const a=ann.avg;
    h+=`<div class="card" style="margin-bottom:14px"><h3>This period vs ${yr} average (${ann.weeks} periods · ${ann.total_posts} posts)</h3><div class="grid g4">`+
      [annualCard('Posts / day',p.posts_per_day,a.posts_per_day),annualCard('Comments / post',p.comments_per_post,a.comments_per_post),
       annualCard('Avg upvote ratio',p.avg_upvote_ratio,a.avg_upvote_ratio,'%'),annualCard('Contributors',p.contributors,a.contributors),
       annualCard('Resolution rate',p.resolution_rate,a.resolution_rate,'%'),annualCard('Issues tracked',p.issues_tracked,a.issues_tracked),
       annualCard('Escalations',p.escalation_count,a.escalation_count,'',false),annualCard('Negative sentiment',p.sentiment.neg,a.sentiment_neg,'%',false)].join('')+'</div></div>';
  }
  h+='<div class="grid g4">'+trend(x=>x.posts_per_day,'Posts / day','#3b82f6')+trend(x=>x.avg_upvote_ratio,'Upvote ratio %','#22c55e','%')+
     trend(x=>x.contributors,'Contributors','#8b5cf6')+trend(x=>x.resolution_rate,'Resolution %','#f59e0b','%')+'</div>';
  if(Object.keys(DATA.annual).length>1){
    h+='<div class="grid g2" style="margin-top:14px">'+yoy(x=>x.posts_per_day,'Posts / day')+yoy(x=>x.avg_upvote_ratio,'Upvote ratio','%')+'</div>';}
  return h;
}

let view='dashboard';
const TITLES={dashboard:'Dashboard',mentions:'Mentions',moderation:'Moderation',trends:'Trends'};
function setCnt(id,v){const e=document.getElementById(id);if(e)e.textContent=v;}
function render(){
  const p = scopeOf(periodSel);
  const q = scopeOf(compareSel) || {};
  const cmp = compareSel.kind !== 'none';
  $('#periodBtn').querySelector('.rb-l').textContent = selLabel(periodSel);
  $('#periodHint').textContent = selHint(periodSel);
  $('#compareBtn').querySelector('.rb-l').textContent = compareSel.kind==='none' ? 'Compare' : selLabel(compareSel);
  $('#compareHint').textContent = cmp ? 'vs ' + selHint(compareSel) : '';
  $('#viewTitle').textContent = TITLES[view];
  const riskTot=(p.risks||[]).reduce((a,r)=>a+(r.count||0),0);
  setCnt('c-dash',p.posts); setCnt('c-ment',(p.feed||[]).length); setCnt('c-mod',riskTot+(p.escalation_count||0)); setCnt('c-tr',DATA.periods.length);
  let h;
  if(view==='dashboard') h=viewDashboard(p,q,cmp);
  else if(view==='mentions') h=viewMentions(p);
  else if(view==='moderation') h=viewModeration(p,q,cmp);
  else h=viewTrends(p,q,cmp);
  $('#view').innerHTML=h;
  if(p.custom){
    const note=document.createElement('div');note.className='infobox';
    note.innerHTML=`<div class="ibi"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg></div>
      <div style="flex:1;min-width:0">
        <div class="ibt">Custom date range — live computation</div>
        <div class="ibd">Headline KPIs, sentiment, top authors, top posts and the activity series above are computed on the fly from per-day aggregates for this exact window.</div>
        <div class="ibchips">
          <span class="ibchip on">Posts &amp; comments</span>
          <span class="ibchip on">Sentiment</span>
          <span class="ibchip on">Top authors / posts</span>
          <span class="ibchip on">Activity chart</span>
          <span class="ibchip">Risk breakdown · cohort only</span>
          <span class="ibchip">Escalation queue · cohort only</span>
          <span class="ibchip">Topic cloud · cohort only</span>
        </div>
      </div>`;
    $('#view').insertBefore(note, $('#view').firstChild);
  }
}
document.querySelectorAll('#nav a').forEach(a=>a.onclick=()=>{
  view=a.dataset.v; document.querySelectorAll('#nav a').forEach(x=>x.classList.toggle('active',x===a)); render();
  if(mqMobile.matches) appEl.classList.remove('sb-open');
});

// Range-picker popover, used by both Period and Compare buttons
const rpop = $('#rangePop');
let pickerRole = null; let calTab = 'start'; let calStart = null, calEnd = null; let calBaseMonth = null;
const MONTHS_FULL = ['January','February','March','April','May','June','July','August','September','October','November','December'];
function renderPresets(){
  const wrap = $('#rpopPresets'); wrap.innerHTML='';
  const cur = pickerRole==='period' ? periodSel : compareSel;
  if(pickerRole==='compare'){
    const b=document.createElement('button');b.textContent='No comparison';b.className=cur.kind==='none'?'sel':'';
    b.onclick=()=>{compareSel={kind:'none'};closePop();render()};wrap.appendChild(b);
    const div=document.createElement('div');div.className='div';wrap.appendChild(div);
  }
  DATA.presets.forEach((p,i)=>{
    const b=document.createElement('button');b.textContent=p.label;b.className=(cur.kind==='preset'&&cur.idx===i)?'sel':'';
    b.onclick=()=>{ if(pickerRole==='period') periodSel={kind:'preset',idx:i}; else compareSel={kind:'preset',idx:i}; closePop(); render(); };
    wrap.appendChild(b);
  });
  const div=document.createElement('div');div.className='div';wrap.appendChild(div);
  const btn=document.createElement('button');btn.innerHTML='Date range <span style="opacity:.6">›</span>';btn.className=(cur.kind==='custom'?'sel':'');
  btn.onclick=()=>openCalendar();wrap.appendChild(btn);
}
function positionPop(role){
  const anchor = $('#'+role+'Btn'); const r = anchor.getBoundingClientRect();
  rpop.style.display='block';
  const wantsWide = $('#rpopCal').style.display !== 'none';
  const w = wantsWide ? 600 : 240;
  let left = r.left;
  if(left + w > window.innerWidth - 12) left = Math.max(12, window.innerWidth - w - 12);
  rpop.style.left = left + 'px'; rpop.style.top = (r.bottom + 6) + 'px';
}
function openPicker(role){ pickerRole = role; $('#rpopCal').style.display='none'; renderPresets(); positionPop(role); }
function openCalendar(){
  const cur = pickerRole==='period' ? periodSel : compareSel;
  if(cur.kind==='custom'){ calStart=cur.start; calEnd=cur.end; } else { calStart=null; calEnd=null; }
  calTab='start';
  calBaseMonth = new Date(DATA.latest.slice(0,7)+'-01T12:00:00');
  calBaseMonth.setMonth(calBaseMonth.getMonth()-1);
  $('#rpopCal').style.display='block'; renderCalendar(); positionPop(pickerRole);
}
function renderCalendar(){
  $$('.rpop-tab').forEach(t => t.classList.toggle('active', t.dataset.tab===calTab));
  const earliest = DATA.earliest, latest = DATA.latest;
  const months = [calBaseMonth, new Date(calBaseMonth.getFullYear(), calBaseMonth.getMonth()+1, 1)];
  $('#rpopMonths').innerHTML = months.map(m => {
    const y = m.getFullYear(), mi = m.getMonth();
    const first = new Date(y, mi, 1); const last = new Date(y, mi+1, 0);
    let cells = '';
    ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'].forEach(d => cells += `<div class="rpop-dh">${d}</div>`);
    for(let i=0;i<first.getDay();i++) cells += '<div></div>';
    for(let d=1; d<=last.getDate(); d++){
      const ds = `${y}-${String(mi+1).padStart(2,'0')}-${String(d).padStart(2,'0')}`;
      const disabled = ds < earliest || ds > latest;
      let cls = 'rpop-d';
      if(disabled) cls += ' dis';
      if(ds === calStart || ds === calEnd) cls += ' sel';
      else if(calStart && calEnd && ds > (calStart<calEnd?calStart:calEnd) && ds < (calStart>calEnd?calStart:calEnd)) cls += ' in-range';
      cells += `<div class="${cls}" data-d="${ds}">${d}</div>`;
    }
    return `<div class="rpop-m"><h4>${MONTHS_FULL[mi]} ${y}</h4><div class="rpop-grid">${cells}</div></div>`;
  }).join('');
  $$('.rpop-d:not(.dis)').forEach(d => d.onclick = ()=>pickDate(d.dataset.d));
  $('#rpopApply').disabled = !(calStart && calEnd);
}
function pickDate(ds){
  if(calTab==='start'){ calStart = ds; if(calEnd && calEnd < calStart) calEnd = null; calTab='end'; }
  else { if(calStart && ds < calStart){ calEnd = calStart; calStart = ds; } else calEnd = ds; }
  renderCalendar();
}
$$('.rpop-tab').forEach(t => t.onclick = ()=>{ calTab=t.dataset.tab; renderCalendar(); });
$('#rpopPrev').onclick = ()=>{ calBaseMonth = new Date(calBaseMonth.getFullYear(), calBaseMonth.getMonth()-1, 1); renderCalendar(); };
$('#rpopNext').onclick = ()=>{ calBaseMonth = new Date(calBaseMonth.getFullYear(), calBaseMonth.getMonth()+1, 1); renderCalendar(); };
$('#rpopApply').onclick = ()=>{
  if(!calStart || !calEnd) return;
  const [s,e] = calStart <= calEnd ? [calStart, calEnd] : [calEnd, calStart];
  const sel = {kind:'custom', start:s, end:e};
  if(pickerRole==='period') periodSel = sel; else compareSel = sel;
  closePop(); render();
};
function closePop(){ rpop.style.display='none'; pickerRole=null; }
$('#periodBtn').onclick = e => { e.stopPropagation(); if(pickerRole==='period') closePop(); else openPicker('period'); };
$('#compareBtn').onclick = e => { e.stopPropagation(); if(pickerRole==='compare') closePop(); else openPicker('compare'); };
// Stop clicks INSIDE the popover from reaching the document close-on-outside handler.
// (Without this, a date click that triggers innerHTML re-render leaves e.target detached;
// rpop.contains(target) then returns false and the popover wrongly closes.)
rpop.addEventListener('click', e => e.stopPropagation());
document.addEventListener('click', e => { if(!rpop.contains(e.target)) closePop(); });

// Theme toggle (light/dark) with CoD safe-zone-style curtain reveal on click
const themeKey = 'hintel-theme';
function applyTheme(t){
  if(t==='dark' || t==='light') document.documentElement.setAttribute('data-theme', t);
  else document.documentElement.removeAttribute('data-theme');
}
applyTheme(localStorage.getItem(themeKey) || 'auto');
$('#themeBtn').onclick = ()=>{
  const cur = localStorage.getItem(themeKey) || 'auto';
  const next = cur==='auto' ? 'dark' : (cur==='dark' ? 'light' : 'auto');
  localStorage.setItem(themeKey, next);
  if(document.startViewTransition) document.startViewTransition(()=>applyTheme(next));
  else applyTheme(next);
};

render();

// --- collapsible / drawer sidebar (Gemini-style) ---
const appEl=document.querySelector('.app');
const mqMobile=matchMedia('(max-width:640px)');
$('#sbToggle').onclick=()=>{ mqMobile.matches ? appEl.classList.toggle('sb-open') : appEl.classList.toggle('sb-collapsed'); };
$('#mOpen').onclick=()=>appEl.classList.add('sb-open');
$('#sbScrim').onclick=()=>appEl.classList.remove('sb-open');
// tablets start collapsed to a rail; clear any collapsed state when dropping to phone width
if(matchMedia('(min-width:641px) and (max-width:980px)').matches) appEl.classList.add('sb-collapsed');
// move the Period/Compare/Weekly/PDF controls into the drawer on mobile, back to the top bar on desktop
const tbctrls=$('#tbctrls'), sbMount=$('#sbCtrlMount'), topbarEl=document.querySelector('.topbar');
function placeControls(){ (mqMobile.matches?sbMount:topbarEl).appendChild(tbctrls); }
placeControls();
mqMobile.addEventListener('change',e=>{ if(e.matches) appEl.classList.remove('sb-collapsed'); appEl.classList.remove('sb-open'); placeControls(); });

// Hover tooltip for trend charts — read each period's value as the cursor moves.
const tip=document.createElement('div'); tip.id='tip'; document.body.appendChild(tip);
document.addEventListener('mousemove',e=>{
  const t=e.target;
  if(t&&t.dataset&&t.dataset.val!==undefined){
    tip.innerHTML=`<div class="nm">${esc(t.dataset.name)}</div><div class="vv">${esc(t.dataset.val)}</div><div class="wn">${esc(t.dataset.win)}</div>`;
    tip.style.display='block';
    let x=e.pageX+14, y=e.pageY+14;
    if(x+230>window.scrollX+document.documentElement.clientWidth) x=e.pageX-230;
    tip.style.left=x+'px'; tip.style.top=y+'px';
  } else { tip.style.display='none'; }
});

// Export: expand all evidence so it prints, then open the print/PDF dialog.
function exportPDF(){
  const p=scopeOf(periodSel);
  [...document.querySelectorAll('details')].forEach(d=>d.open=true);
  const t=document.title; document.title='hIntel_'+p.start+'_to_'+p.end;
  setTimeout(()=>{ window.print(); document.title=t; }, 150);
}
</script></body></html>"""

out_html = (TEMPLATE
            .replace('__DATA__', json.dumps(DATA))
            .replace('__GENERATED__', DATA['generated'])
            .replace('__TRACKERSTART__', DATA['tracker_start']))
with open(OUT, 'w', encoding='utf-8') as f:
    f.write(out_html)
print(f'Dashboard written: {OUT}')
print('Periods:', [f"{p['start']}..{p['end']} ({p['posts']}p/{p['comments']}c)" for p in DATA['periods']])
