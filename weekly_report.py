"""
Weekly staff update — r/Hedera activity between meetings.

Produces a concise, meeting-ready Markdown briefing for an arbitrary date window
(default: last meeting -> today). This is the lightweight "what happened since we
last met" companion to the twice-monthly evaluation dashboard (build_dashboard.py),
built from the same CSVs so the numbers reconcile.

Run:  python -X utf8 weekly_report.py 2026-06-08 2026-06-16
"""
import sys, re
import pandas as pd
from datetime import datetime, timedelta

POSTS_CSV = 'data/r_Hedera/posts.csv'
COMMENTS_CSV = 'data/r_Hedera/comments.csv'

start = datetime.strptime(sys.argv[1], '%Y-%m-%d') if len(sys.argv) > 1 else datetime(2026, 6, 8)
end = datetime.strptime(sys.argv[2], '%Y-%m-%d') if len(sys.argv) > 2 else datetime.utcnow()
end = end.replace(hour=23, minute=59, second=59)
days = (end.date() - start.date()).days + 1

P = pd.read_csv(POSTS_CSV, low_memory=False)
C = pd.read_csv(COMMENTS_CSV, low_memory=False)
P['created_utc'] = pd.to_datetime(P['created_utc'].astype(str).str.replace('T', ' '), errors='coerce')
C['created_utc'] = pd.to_datetime(C['created_utc'].astype(str).str.replace('T', ' '), errors='coerce')
P = P.dropna(subset=['created_utc']); C = C.dropna(subset=['created_utc'])

COMMENTS_THROUGH = C['created_utc'].max()

def window(df, s, e):
    return df[(df.created_utc >= s) & (df.created_utc <= e)].copy()

pp = window(P, start, end)
cp = window(C, start, end)
# prior equal-length window for a simple "vs the week before" read
ps, pe = start - timedelta(days=days), start - timedelta(seconds=1)
pp_prev = window(P, ps, pe)

def pct(cur, prev):
    if not prev: return ''
    d = (cur - prev) / prev * 100
    return f" ({'+' if d>=0 else ''}{d:.0f}% vs prior {days}d)"

n_posts, n_comments = len(pp), len(cp)
posts_per_day = n_posts / days
upr = pp['upvote_ratio'].mean() * 100 if n_posts else 0
authors = (set(pp['author'].dropna()) | set(cp['author'].dropna())); authors.discard('[deleted]')
prior_all = set(P[P.created_utc < start]['author'].dropna()) | set(C[C.created_utc < start]['author'].dropna())
new_auth = authors - prior_all
returning = authors & prior_all

# sentiment (from precomputed post labels)
spos = int((pp.get('sentiment_label') == 'positive').sum())
sneg = int((pp.get('sentiment_label') == 'negative').sum())
tot = max(n_posts, 1)

# top posts
top = pp.nlargest(5, 'score')[['title', 'score', 'num_comments', 'permalink']] if n_posts else pd.DataFrame()

# question / support posts + escalations
q_mask = pp['title'].fillna('').str.contains(r'how|help|issue|error|problem|question|\?', case=False, regex=True)
qposts = pp[q_mask]
commented = set(cp['post_id'].astype(str)) if 'post_id' in cp else set()
escal = qposts[~qposts['id'].astype(str).isin(commented)]

# recurring near-duplicate question titles
norm = qposts['title'].fillna('').str.lower().str.replace(r'[^a-z0-9 ]', '', regex=True).str.strip()
recurring = [(k, v) for k, v in norm.value_counts().items() if v >= 2][:6]

# themes
toks = re.findall(r'\b[a-z]{4,}\b', ' '.join(pp['title'].fillna('').tolist()).lower())
stop = {'that','this','with','have','from','they','will','what','your','about','when','also','like',
        'just','more','some','into','than','then','them','these','there','their','which','would',
        'hedera','hbar','going','really','people','think','need','does','want','help'}
freq = {}
for t in toks:
    if t not in stop: freq[t] = freq.get(t, 0) + 1
themes = sorted(freq, key=freq.get, reverse=True)[:8]

# risk signals (titles + any comment bodies in window)
RISK = [
    ('Scam / phishing', r'wallet drainer|connect your wallet|double your (?:money|hbar|crypto)|claim.{0,15}airdrop|free hbar|t\.me/|join.{0,10}telegram|\bdm me\b|giveaway'),
    ('Impersonation / fake accounts', r'impersonat|fake account|scam account|fake profile|posing as'),
    ('FUD / negative narrative', r'\bfud\b|spreading fear|\brug\s?pull\b|rugpull'),
    ('Compliance-sensitive (SEC/legal)', r'\bsec\b|\bcftc\b|regulation|lawsuit|compliance|legal action|\bbanned\b'),
]
risk_rows = []
for label, pat in RISK:
    hits = pp[pp['title'].fillna('').str.contains(pat, case=False, regex=True)]
    risk_rows.append((label, len(hits), hits))

def rlink(p): return f"https://reddit.com{p}" if isinstance(p, str) and p.startswith('/') else ''

L = []
L.append(f"# r/Hedera — Weekly Staff Update")
L.append(f"**Period covered:** {start:%a %d %b %Y} → {end:%a %d %b %Y}  ({days} days, since last meeting)")
L.append(f"**Prepared:** {datetime.utcnow():%Y-%m-%d %H:%M} UTC · source: r/Hedera (Arctic-Shift archive)\n")

if COMMENTS_THROUGH < start:
    L.append(f"> ⚠ **Data note:** the comment archive currently runs only through "
             f"**{COMMENTS_THROUGH:%d %b %Y}**, so this window has **no archived comment/reply data yet** "
             f"(it backfills on a lag). Figures below cover **submissions (posts)**, which are complete through "
             f"{P['created_utc'].max():%d %b}. Reply-based metrics (answers, resolution) will fill in at the next refresh.\n")

L.append("## TL;DR")
L.append(f"- **{n_posts} new posts** ({posts_per_day:.1f}/day){pct(n_posts, len(pp_prev))}.")
L.append(f"- **{len(authors)} active contributors** — {len(new_auth)} new to the tracker, {len(returning)} returning.")
L.append(f"- **Avg upvote ratio {upr:.0f}%** · sentiment {round(spos/tot*100)}% positive / {round(sneg/tot*100)}% negative.")
L.append(f"- **{len(qposts)} support/question posts**, of which **{len(escal)} still look unanswered** (see queue).")
top_risk = max(risk_rows, key=lambda r: r[1])
L.append(f"- **Risk:** " + (", ".join(f"{lab} ({n})" for lab, n, _ in risk_rows if n) or "no scam/impersonation/FUD signals flagged in titles.") )
L.append("")

L.append("## Activity")
L.append(f"| Metric | This period | Prior {days}d |")
L.append("|---|---|---|")
L.append(f"| New posts | {n_posts} | {len(pp_prev)} |")
L.append(f"| Posts / day | {posts_per_day:.1f} | {len(pp_prev)/days:.1f} |")
L.append(f"| Avg upvote ratio | {upr:.0f}% | {pp_prev['upvote_ratio'].mean()*100 if len(pp_prev) else 0:.0f}% |")
L.append(f"| Active contributors | {len(authors)} | — |")
L.append(f"| Archived comments in window | {n_comments} | — |")
L.append("")

if len(top):
    L.append("## Top posts this period")
    for r in top.itertuples():
        link = rlink(r.permalink)
        title = str(r.title)[:90].replace('|', '\\|')
        L.append(f"- **{int(r.score)}↑ / {int(r.num_comments)}💬** — " + (f"[{title}]({link})" if link else title))
    L.append("")

L.append("## What people were talking about")
L.append("Top title keywords: " + ", ".join(f"`{t}`" for t in themes) + "\n")
if recurring:
    L.append("**Recurring / repeated questions:**")
    for k, v in recurring:
        L.append(f"- ×{v} — {k[:90]}")
    L.append("")

L.append("## Support queue — needs a look")
if len(escal):
    L.append(f"{len(escal)} question-style posts in the window with no archived reply "
             f"(note: comment lag above means some may already be answered):")
    for _, r in escal.sort_values('created_utc').head(12).iterrows():
        link = rlink(r['permalink'])
        title = str(r['title'])[:90].replace('|', '\\|')
        L.append(f"- {r['created_utc']:%d %b} · u/{r['author']} — " + (f"[{title}]({link})" if link else title))
else:
    L.append("No unanswered question-posts flagged.")
L.append("")

L.append("## Risk & moderation")
any_risk = False
for label, n, hits in risk_rows:
    if n:
        any_risk = True
        L.append(f"**{label} — {n} flagged**")
        for _, r in hits.head(4).iterrows():
            link = rlink(r['permalink'])
            title = str(r['title'])[:90].replace('|', '\\|')
            L.append(f"  - {r['created_utc']:%d %b} · u/{r['author']} — " + (f"[{title}]({link})" if link else title))
if not any_risk:
    L.append("No scam, impersonation, FUD, or compliance signals detected in post titles this period.")
L.append("")
L.append("---")
L.append("_Soft/keyword metrics are regex proxies over titles; verify before acting. "
         "Full evaluation: twice-monthly dashboard (index.html)._")

out = "\n".join(L)
fname = f"STAFF_UPDATE_{end:%Y-%m-%d}.md"
with open(fname, 'w', encoding='utf-8') as f:
    f.write(out)

# ---------------------------------------------------------------- themed HTML view
import html as _html
def esc(s): return _html.escape(str(s))
def alink(permalink, text):
    u = rlink(permalink)
    return f'<a href="{u}" target="_blank">{esc(text)}</a>' if u else esc(text)

def card_sec(eyebrow, title, body):
    return (f'<div class="eyebrow">{esc(eyebrow)}</div><div class="sec-title">{title}</div>'
            f'<div class="card">{body}</div>')

# TL;DR pills
tldr = "".join(f'<li>{x}</li>' for x in [
    f"<b>{n_posts} new posts</b> ({posts_per_day:.1f}/day){esc(pct(n_posts, len(pp_prev)))}",
    f"<b>{len(authors)} active contributors</b> — {len(new_auth)} new, {len(returning)} returning",
    f"<b>{upr:.0f}%</b> avg upvote ratio",
    f"<b>{len(qposts)} question-posts</b>, {len(escal)} look unanswered",
    ("Risk: " + ", ".join(f"{esc(lab)} ({n})" for lab, n, _ in risk_rows if n)) if any(n for _,n,_ in risk_rows)
        else "No scam / impersonation / FUD signals in titles",
])

top_html = "<table><tbody>" + "".join(
    f'<tr><td class="num">{int(r.score)}↑ · {int(r.num_comments)}💬</td><td>{alink(r.permalink, str(r.title)[:110])}</td></tr>'
    for r in top.itertuples()) + "</tbody></table>" if len(top) else '<div class="muted">No posts.</div>'

themes_html = " ".join(f'<span class="tag">{esc(t)}</span>' for t in themes)
rec_html = ("".join(f'<div class="row"><span class="pill">×{v}</span> {esc(k[:110])}</div>' for k, v in recurring)
            if recurring else '<div class="muted">No repeated question topics.</div>')

if len(escal):
    queue_html = "".join(
        f'<div class="row"><span class="muted">{r["created_utc"]:%d %b}</span> · u/{esc(r["author"])} — {alink(r["permalink"], str(r["title"])[:110])}</div>'
        for _, r in escal.sort_values('created_utc').head(15).iterrows())
else:
    queue_html = '<div class="muted">No unanswered question-posts flagged.</div>'

risk_html = ""
for label, n, hits in risk_rows:
    if n:
        rows = "".join(f'<div class="row"><span class="muted">{r["created_utc"]:%d %b}</span> · u/{esc(r["author"])} — {alink(r["permalink"], str(r["title"])[:110])}</div>'
                       for _, r in hits.head(5).iterrows())
        risk_html += f'<div class="risk-h">{esc(label)} — <b>{n}</b></div>{rows}'
if not risk_html:
    risk_html = '<div class="muted">No scam, impersonation, FUD, or compliance signals in post titles this period.</div>'

note = ""
if COMMENTS_THROUGH < start:
    note = (f'<div class="note">⚠ <b>Data note:</b> the comment archive runs only through '
            f'<b>{COMMENTS_THROUGH:%d %b %Y}</b> — this window has <b>no archived comment data yet</b> (backfills on a lag). '
            f'Figures cover <b>submissions (posts)</b>, complete through {P["created_utc"].max():%d %b}. '
            f'Reply-based metrics fill in at the next refresh.</div>')

HTML = f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ℏIntel — Weekly Staff Update</title><link rel="icon" href="public/log.png"><style>
:root{{--bg:#f3f5fa;--card:#ffffff;--ink:#1d2540;--mut:#7a85a3;--line:#e7ebf3;--accent:#3b82f6;--good:#22c55e;--warn:#f59e0b;--bad:#ef4444;--blue:#3b82f6}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 system-ui,Segoe UI,Roboto,sans-serif}}
.wrap{{max-width:880px;margin:0 auto;padding:30px 26px 80px}}
.top{{display:flex;align-items:center;gap:14px;flex-wrap:wrap;margin-bottom:8px}}
h1{{font-size:28px;font-weight:600;letter-spacing:-.01em;margin:0}}
.meta{{color:var(--mut);font-size:13px;margin-bottom:18px}}
.back{{margin-left:auto;background:var(--accent);color:#fff;text-decoration:none;border-radius:8px;padding:9px 16px;font-weight:600;font-size:13px}}
.eyebrow{{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--accent);font-weight:700;margin:34px 0 0;border-top:1px solid var(--line);padding-top:20px}}
.sec-title{{font-size:20px;font-weight:600;margin:6px 0 13px;color:var(--ink)}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px;box-shadow:0 1px 3px rgba(20,30,60,.05)}}
.muted{{color:var(--mut)}}.row{{padding:7px 0;border-bottom:1px solid var(--line)}}.row:last-child{{border:none}}
table{{width:100%;border-collapse:collapse}}td{{padding:7px 8px;border-bottom:1px solid var(--line);vertical-align:top}}
td.num{{color:var(--ink);font-weight:600;white-space:nowrap;font-variant-numeric:tabular-nums}}
a{{color:var(--blue);text-decoration:none}}a:hover{{text-decoration:underline}}
.tag{{display:inline-block;background:#eef2fb;border:1px solid var(--line);border-radius:6px;padding:3px 9px;margin:2px;font-size:13px}}
.pill{{display:inline-block;background:#fef3c7;color:#92600a;border-radius:999px;padding:1px 9px;font-size:12px;font-weight:700;margin-right:6px}}
.risk-h{{color:#b91c1c;margin:10px 0 4px;font-size:14px;font-weight:600}}.risk-h:first-child{{margin-top:0}}
.tldr li{{margin:6px 0}}.tldr{{margin:0;padding-left:18px}}
.note{{background:#fff7e6;border:1px solid var(--warn);border-radius:12px;padding:13px 15px;margin:6px 0 4px;font-size:14px;color:#1d2540}}
.foot{{color:var(--mut);font-size:12px;margin-top:34px;border-top:1px solid var(--line);padding-top:16px}}
</style></head><body><div class="wrap">
<div class="top"><img src="public/log.png" alt="ℏIntel" style="width:34px;height:34px;border-radius:8px;background:#fff;padding:3px;object-fit:contain">
<h1><span style="font-weight:400">ℏ</span>Intel <span style="color:var(--mut);font-weight:400;font-size:20px">— Weekly Staff Update</span></h1>
<a class="back" href="index.html">← Dashboard</a></div>
<div class="meta">Period covered: <b>{start:%a %d %b %Y} → {end:%a %d %b %Y}</b> · {days} days, since last meeting · prepared {datetime.utcnow():%Y-%m-%d %H:%M} UTC</div>
{note}
<div class="eyebrow">TL;DR</div><div class="sec-title">At a glance</div><div class="card"><ul class="tldr">{tldr}</ul></div>
{card_sec("Activity", "Submission volume", f'<table><tbody>'
    f'<tr><td>New posts</td><td class="num">{n_posts}</td><td class="muted">prior {days}d: {len(pp_prev)}</td></tr>'
    f'<tr><td>Posts / day</td><td class="num">{posts_per_day:.1f}</td><td class="muted">prior {days}d: {len(pp_prev)/days:.1f}</td></tr>'
    f'<tr><td>Avg upvote ratio</td><td class="num">{upr:.0f}%</td><td></td></tr>'
    f'<tr><td>Active contributors</td><td class="num">{len(authors)}</td><td class="muted">{len(new_auth)} new</td></tr>'
    f'<tr><td>Archived comments in window</td><td class="num">{n_comments}</td><td></td></tr>'
    f'</tbody></table>')}
{card_sec("Top content", "Top posts this period", top_html)}
{card_sec("Themes", "What people were talking about", f'<div>{themes_html}</div><div style="margin-top:12px">{rec_html}</div>')}
{card_sec("Queue", f"Support queue — {len(escal)} need a look", queue_html)}
{card_sec("Moderation", "Risk & moderation", risk_html)}
<div class="foot">Soft/keyword metrics are regex proxies over titles — verify before acting. Full evaluation: the twice-monthly <a href="index.html">dashboard</a>.</div>
</div></body></html>"""

with open('weekly.html', 'w', encoding='utf-8') as f:
    f.write(HTML)

print(out)
print(f"\n\n[written: {fname}  +  weekly.html]")
