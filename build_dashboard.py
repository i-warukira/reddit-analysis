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

# Cohorts auto-generate as rolling 7-day weeks, anchored to the first report
# boundary (2026-04-28) and extending through the latest data each rebuild — so
# the trend lines keep growing automatically as refresh_dashboard.py adds data.
WEEK_ANCHOR = '2026-04-28'   # Monday aligning with the original report cadence

def weekly_cohorts(latest):
    start = datetime.strptime(WEEK_ANCHOR, '%Y-%m-%d')
    out = []
    while start.date() <= latest.date():
        end = start + timedelta(days=6)
        out.append((start.strftime('%Y-%m-%d'), end.strftime('%Y-%m-%d')))
        start += timedelta(days=7)
    return out

# ---------------------------------------------------------------- load
P = pd.read_csv(POSTS_CSV)
C = pd.read_csv(COMMENTS_CSV)
P['created_utc'] = pd.to_datetime(P['created_utc'].astype(str).str.replace('T', ' '), errors='coerce')
C['created_utc'] = pd.to_datetime(C['created_utc'].astype(str).str.replace('T', ' '), errors='coerce')
P = P.dropna(subset=['created_utc'])
C = C.dropna(subset=['created_utc'])
TRACKER_START = min(P['created_utc'].min(), C['created_utc'].min()).strftime('%Y-%m-%d')

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

    return {
        'start': start, 'end': end, 'days': ndays,
        'posts': n_posts, 'comments': n_comments,
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

LATEST = max(P['created_utc'].max(), C['created_utc'].max())
COHORTS = weekly_cohorts(LATEST)
DATA = {'tracker_start': TRACKER_START, 'generated': datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC'),
        'periods': [metrics(s, e) for s, e in COHORTS]}

# ---------------------------------------------------------------- HTML
TEMPLATE = r"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Hedera Moderator Intelligence Dashboard</title>
<style>
:root{--bg:#0b0f17;--card:#151b27;--card2:#1b2333;--ink:#e8eef7;--mut:#8b9bb4;--line:#28324a;
--accent:#7c5cff;--good:#23c552;--warn:#f5a623;--bad:#ff5470;--blue:#3da9fc;}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 system-ui,Segoe UI,Roboto,sans-serif}
header{padding:20px 28px;border-bottom:1px solid var(--line);display:flex;align-items:center;gap:16px;flex-wrap:wrap}
header h1{font-size:18px;margin:0;font-weight:700}
.sub{color:var(--mut);font-size:12px}
.wrap{padding:22px 28px;max-width:1280px;margin:0 auto}
.controls{display:flex;gap:10px;align-items:center;margin:0 0 18px;flex-wrap:wrap}
select{background:var(--card2);color:var(--ink);border:1px solid var(--line);border-radius:8px;padding:8px 10px}
.grid{display:grid;gap:14px}.g4{grid-template-columns:repeat(4,1fr)}.g3{grid-template-columns:repeat(3,1fr)}
.g2{grid-template-columns:repeat(2,1fr)}
@media(max-width:900px){.g4,.g3,.g2{grid-template-columns:repeat(2,1fr)}}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px}
.card h3{margin:0 0 10px;font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:var(--mut)}
.kpi .v{font-size:26px;font-weight:700}.kpi .l{color:var(--mut);font-size:12px;margin-top:2px}
.delta{font-size:12px;font-weight:600;margin-left:8px}.up{color:var(--good)}.down{color:var(--bad)}.flat{color:var(--mut)}
table{width:100%;border-collapse:collapse;font-size:13px}th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--mut);font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:.05em}
.pill{display:inline-block;padding:2px 9px;border-radius:999px;font-size:11px;font-weight:700}
.s-None{background:#1d2b1f;color:var(--good)}.s-Low{background:#23351f;color:var(--good)}
.s-Medium{background:#3a2f17;color:var(--warn)}.s-High{background:#3a1c25;color:var(--bad)}
.s-HEALTHY,.s-LOW{background:#1d2b1f;color:var(--good)}.s-MODERATE,.s-MEDIUM{background:#3a2f17;color:var(--warn)}
.s-HIGH{background:#3a1c25;color:var(--bad)}
a{color:var(--blue);text-decoration:none}a:hover{text-decoration:underline}
.muted{color:var(--mut)}.tag{display:inline-block;background:var(--card2);border:1px solid var(--line);border-radius:6px;padding:3px 8px;margin:2px;font-size:12px}
details{margin-top:6px}summary{cursor:pointer;color:var(--blue);font-size:12px}
.ev{font-size:12px;color:var(--mut);border-left:2px solid var(--line);padding:4px 0 4px 10px;margin:6px 0}
.bar{height:8px;border-radius:4px;background:var(--card2);overflow:hidden;display:flex}
.section-title{font-size:13px;letter-spacing:.05em;text-transform:uppercase;color:var(--mut);margin:26px 0 10px;border-top:1px solid var(--line);padding-top:18px}
svg text{fill:var(--mut);font-size:10px}
g.ptg{cursor:pointer}g.ptg:hover .pt{r:5}.pt-hit{fill:transparent}
#tip{position:absolute;display:none;z-index:60;background:#0b0f17;border:1px solid var(--line);border-radius:8px;padding:8px 11px;font-size:12px;pointer-events:none;box-shadow:0 8px 24px rgba(0,0,0,.5);max-width:220px}
#tip .nm{color:var(--mut);font-size:11px;text-transform:uppercase;letter-spacing:.05em}
#tip .vv{font-size:18px;font-weight:700;color:var(--ink)}#tip .wn{color:var(--blue);font-size:12px}
.legend{font-size:11px;color:var(--mut);display:flex;gap:14px;flex-wrap:wrap;margin-top:6px}
.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:5px;vertical-align:middle}
.btn{margin-left:auto;background:var(--accent);color:#fff;border:none;border-radius:8px;padding:9px 16px;font-weight:600;cursor:pointer;font-size:13px}
.btn:hover{filter:brightness(1.1)}
@media print{
  @page{size:A4;margin:12mm}
  body{background:#fff;color:#111}
  header{border-color:#ccc}.btn,.controls{display:none!important}
  .card,.card2{background:#fff;border:1px solid #ccc;break-inside:avoid}
  .section-title{color:#444;border-color:#ccc}
  h1,.card h3,th{color:#111}.muted,.sub,td.muted{color:#555}
  svg text{fill:#555}
  details[open] summary{display:none}
  details{open:true}
  .pill{border:1px solid #999}
  a{color:#111;text-decoration:none}
}
</style></head><body>
<header>
  <h1>🛡️ Hedera Moderator Intelligence Dashboard</h1>
  <span class="sub">Auto-generated __GENERATED__ · tracker history since __TRACKERSTART__ · source: r/Hedera (Arctic-Shift archive)</span>
  <button class="btn" onclick="exportPDF()">⬇ Export / Print PDF</button>
</header>
<div class="wrap">
  <div class="controls">
    <label class="muted">Period</label>
    <select id="periodSel"></select>
    <label class="muted">Compare to</label>
    <select id="compareSel"></select>
    <span class="sub" id="winLabel"></span>
  </div>
  <div id="app"></div>
  <p class="sub" style="margin-top:28px">Soft/keyword metrics (risk, issues, themes) are proxies computed by word-bounded regex over titles + comment bodies, not verified mod actions — expand "evidence" to audit every count. Fields like bans/reports/peak-online require the Reddit mod dashboard.</p>
</div>
<script>
const DATA = __DATA__;
const $ = s => document.querySelector(s);
const esc = s => (s==null?'':String(s)).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const rlink = p => p && p!=='nan' && p!=='' ? 'https://reddit.com'+p : null;

function opts(sel){ DATA.periods.forEach((p,i)=>{ const o=document.createElement('option'); o.value=i; o.textContent=p.start+' → '+p.end; sel.appendChild(o);}); }
opts($('#periodSel')); opts($('#compareSel'));
$('#periodSel').value = DATA.periods.length-1;
$('#compareSel').value = Math.max(0, DATA.periods.length-2);

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
function mix(p){
  const cols={link:'#3da9fc',text:'#7c5cff',image:'#23c552',video:'#f5a623',gallery:'#ff5470'};
  const entries=Object.entries(p.type_mix||{});
  const bar=entries.map(([k,v])=>`<span style="width:${v}%;background:${cols[k]||'#888'}"></span>`).join('');
  const leg=entries.map(([k,v])=>`<span><span class="dot" style="background:${cols[k]||'#888'}"></span>${k} ${v}%</span>`).join('');
  return `<div class="card"><h3>Post type mix</h3><div class="bar">${bar}</div><div class="legend">${leg}</div></div>`;
}
function evBlock(rows){
  if(!rows||!rows.length) return '<div class="muted" style="font-size:12px">No matches.</div>';
  return rows.map(r=>{const l=rlink(r.link);return `<div class="ev"><b>${esc(r.date)}</b> · u/${esc(r.author)} · ${r.where}${l?` · <a href="${l}" target="_blank">link</a>`:''}<br>“${esc(r.text)}”</div>`;}).join('');
}

function render(){
  const i=+$('#periodSel').value, j=+$('#compareSel').value;
  const p=DATA.periods[i], q=DATA.periods[j];
  $('#winLabel').textContent = `${p.days} days · vs ${q.start} → ${q.end}`;
  const risksSorted=[...p.risks].sort((a,b)=>b.rank-a.rank);
  let h='';

  // KPI row
  h+='<div class="section-title">Community health & growth</div><div class="grid g4">';
  h+=kpi('Posts',p.posts,q.posts);
  h+=kpi('Comments',p.comments,q.comments);
  h+=kpi('Posts / day',p.posts_per_day,q.posts_per_day);
  h+=kpi('Avg upvote ratio',p.avg_upvote_ratio,q.avg_upvote_ratio,'%');
  h+=kpi('Unique contributors',p.contributors,q.contributors);
  h+=kpi('New to tracker',p.new_to_tracker,q.new_to_tracker);
  h+=kpi('Returning',p.returning,q.returning);
  h+=kpi('Growth vs prior window',p.growth_pct,q.growth_pct,'%');
  h+='</div>';

  // health/risk status
  h+='<div class="grid g4" style="margin-top:14px">';
  h+=`<div class="card kpi"><div class="v"><span class="pill s-${p.health}">${p.health}</span></div><div class="l">Community health</div></div>`;
  h+=`<div class="card kpi"><div class="v"><span class="pill s-${p.risk_level}">${p.risk_level}</span></div><div class="l">Overall risk level</div></div>`;
  h+=kpi('Issues tracked',p.issues_tracked,q.issues_tracked);
  h+=kpi('Resolution rate',p.resolution_rate,q.resolution_rate,'%');
  h+='</div>';

  // trends
  h+='<div class="section-title">Trends across all periods</div><div class="grid g4">';
  h+=trend(p=>p.posts_per_day,'Posts / day','#3da9fc');
  h+=trend(p=>p.avg_upvote_ratio,'Upvote ratio %','#23c552','%');
  h+=trend(p=>p.contributors,'Contributors','#7c5cff');
  h+=trend(p=>p.resolution_rate,'Resolution %','#f5a623','%');
  h+='</div>';

  // RISK table
  h+='<div class="section-title">Risk & moderation — severity · evidence · suggested action</div>';
  h+='<div class="card"><table><thead><tr><th>Risk</th><th>Severity</th><th>Hits</th><th>Suggested action</th></tr></thead><tbody>';
  risksSorted.forEach(r=>{
    h+=`<tr><td><b>${esc(r.label)}</b><details><summary>evidence (${r.count})</summary>${evBlock(p.risk_evidence[r.key])}</details></td>
        <td><span class="pill s-${r.level}">${r.level}</span></td><td>${r.count}</td><td class="muted">${esc(r.action)}</td></tr>`;
  });
  h+=`<tr><td>Posts removed (deleted/removed)</td><td>—</td><td>${p.posts_removed}</td><td class="muted">Review removal reasons; confirm against mod log.</td></tr>`;
  h+='</tbody></table></div>';

  // Escalation queue
  h+=`<div class="section-title">Escalation queue — unanswered question-posts &gt;24h (${p.escalation_count})</div><div class="card">`;
  if(p.escalation_rows.length){
    h+='<table><thead><tr><th>Date</th><th>Author</th><th>Question post</th></tr></thead><tbody>';
    p.escalation_rows.forEach(r=>{const l=rlink(r.link);h+=`<tr><td>${esc(r.date)}</td><td>u/${esc(r.author)}</td><td>${l?`<a href="${l}" target="_blank">${esc(r.title)}</a>`:esc(r.title)}</td></tr>`;});
    h+='</tbody></table>';
  } else h+='<div class="muted">Nothing pending — all tracked questions received a reply.</div>';
  h+=`<div class="sub" style="margin-top:8px">“Answered” = received ≥1 captured comment. Avg first-response: ${p.avg_response_hrs!==null?p.avg_response_hrs+' hrs':'n/a'}.</div></div>`;

  // Content + sentiment themes
  h+='<div class="section-title">Content performance & sentiment</div><div class="grid g2">';
  h+=mix(p);
  h+=`<div class="card"><h3>Sentiment themes</h3>
      <div>pos <b style="color:var(--good)">${p.sentiment.pos}%</b> · neutral ${p.sentiment.neu}% · neg <b style="color:var(--bad)">${p.sentiment.neg}%</b></div>
      <div style="margin-top:8px">${(p.themes||[]).map(t=>`<span class="tag">${esc(t)}</span>`).join('')}</div></div>`;
  h+='</div>';
  h+='<div class="card" style="margin-top:14px"><h3>Top posts by upvotes</h3><table><thead><tr><th>Title</th><th>↑</th><th>💬</th></tr></thead><tbody>';
  (p.top_posts||[]).forEach(r=>{const l=rlink(r.link);h+=`<tr><td>${l?`<a href="${l}" target="_blank">${esc(r.title)}</a>`:esc(r.title)}</td><td>${r.score}</td><td>${r.comments}</td></tr>`;});
  h+='</tbody></table></div>';

  // Dev funnel + gaps + recurring
  h+='<div class="section-title">Developer & support funnel</div><div class="grid g4">';
  h+=kpi('SDK/API questions',p.sdk_questions,q.sdk_questions);
  h+=kpi('Code-snippet posts',p.code_posts,q.code_posts);
  h+=kpi('docs.hedera.com links',p.docs_links,q.docs_links);
  h+=kpi('GitHub/Hiero links',p.github_links,q.github_links);
  h+='</div>';
  h+='<div class="grid g2" style="margin-top:14px">';
  h+='<div class="card"><h3>Gaps identified</h3>'+(p.gaps.length?'<table><tbody>'+p.gaps.map(g=>`<tr><td><b>${esc(g.gap)}</b><div class="muted">${esc(g.detail)}</div></td><td class="muted">${esc(g.action)}</td></tr>`).join('')+'</tbody></table>':'<div class="muted">No major gaps flagged.</div>')+'</div>';
  h+='<div class="card"><h3>Recurring / duplicate questions</h3>'+(p.recurring.length?'<table><tbody>'+p.recurring.map(r=>`<tr><td>${esc(r.title)}</td><td><span class="pill s-Medium">×${r.count}</span></td></tr>`).join('')+'</tbody></table>':'<div class="muted">No repeated question topics.</div>')+'</div>';
  h+='</div>';

  $('#app').innerHTML=h;
}
$('#periodSel').onchange=render; $('#compareSel').onchange=render; render();

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
  const p=DATA.periods[+$('#periodSel').value];
  const opened=[...document.querySelectorAll('details')];
  opened.forEach(d=>d.open=true);
  const t=document.title; document.title='Hedera_Mod_Dashboard_'+p.start+'_to_'+p.end;
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
