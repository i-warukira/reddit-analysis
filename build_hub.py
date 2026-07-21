# -*- coding: utf-8 -*-
"""
Build index.html — the ℏIntel unified dashboard.

Not a picker: this is the cross-platform overview. It rolls Reddit + Discord
(and any future source) into combined headline metrics, charts both platforms
on one timeline, and breaks the numbers out per platform. Platform buttons in
the top bar open each source's own full dashboard (sidebar tabs, Compare,
Weekly, PDF live there).

Reads data/hub/*.json emitted by build_dashboard.py / build_discord_dashboard.py.
Add a platform by dropping in another data/hub/<name>.json — no code change.

Run:  python -X utf8 build_hub.py
"""
import html, json, os
from datetime import datetime

OUT = 'index.html'
E = lambda s: html.escape(str(s), quote=True)

# display order + brand colour; icon path comes from each platform's json
# (key, community label, colour, dashboard title). The community label still names the
# source in charts; the dashboard title is what the landing page shows.
ORDER = [('reddit', 'r/Hedera', '#ff4500', 'Reddit Dashboard'),
         ('discord', 'Hedera Discord', '#5865F2', 'Discord Dashboard')]

CSS = """
:root{--bg:#f7f8fd;--card:#ffffff;--ink:#1e2340;--mut:#8b90a8;--line:#eceef6;--accent:#6366f1;--c1:#6366f1;--c2:#8b5cf6;--c3:#2dd4bf;--c4:#f59e0b;--c5:#ec4899;--c-idle:#cbd5e1;
--good:#10b981;--bad:#ef4444;--warn:#f59e0b;--logo-bg:#fff;--hover:#eef0fb;--btn-alt:#eef0fb;
--shadow:0 1px 3px rgba(20,30,60,.06);--shadow-lg:0 18px 44px rgba(20,30,60,.13)}
html[data-theme="dark"]{--bg:#0f1217;--card:#181c24;--ink:#e6e9f0;--mut:#8b95a8;--line:#262b35;
--logo-bg:#262b35;--hover:#262b35;--btn-alt:#262b35;--shadow:0 1px 3px rgba(0,0,0,.3);--shadow-lg:0 22px 55px rgba(0,0,0,.55)}
@media (prefers-color-scheme: dark){html:not([data-theme="light"]){--bg:#0f1217;--card:#181c24;--ink:#e6e9f0;--mut:#8b95a8;
--line:#262b35;--logo-bg:#262b35;--hover:#262b35;--btn-alt:#262b35;--shadow:0 1px 3px rgba(0,0,0,.3);--shadow-lg:0 22px 55px rgba(0,0,0,.55)}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.55 Plus Jakarta Sans,Inter,system-ui,Segoe UI,Roboto,sans-serif,Segoe UI,Roboto,sans-serif;letter-spacing:-.005em}
/* no nav bar on the landing page — branding sits in the hero, theme toggle floats */
.brand{display:inline-flex;align-items:center;gap:10px;text-decoration:none;color:var(--ink);margin-bottom:26px}
.brand img{width:34px;height:34px;border-radius:9px;background:var(--logo-bg);padding:3px}
.brand b{font:600 19px Plus Jakarta Sans,Inter,system-ui,Segoe UI,Roboto,sans-serif}.brand .h{font-weight:400}
.pbtn{display:inline-flex;align-items:center;gap:8px;border:1px solid var(--line);border-radius:9px;
padding:7px 14px;text-decoration:none;color:var(--ink);font:600 13.5px Plus Jakarta Sans,Inter,system-ui,Segoe UI,Roboto,sans-serif;background:var(--card);transition:all .15s}
.pbtn img{width:17px;height:17px}
.pbtn:hover{border-color:var(--accent);transform:translateY(-1px);box-shadow:var(--shadow)}
.pbtn.off{opacity:.6}
.tt{background:transparent;border:1px solid var(--line);color:var(--mut);border-radius:9px;padding:7px;cursor:pointer;display:inline-flex}
.tt svg{width:16px;height:16px}.tt:hover{color:var(--accent);border-color:var(--accent)}
.wrap{max-width:1180px;margin:0 auto;padding:26px 26px 70px}
/* Hero: copy in the content column, artwork bleeds off the right edge and rides up
   toward the nav. Clip on html AND body so nothing produces a horizontal scrollbar. */
html,body{overflow-x:hidden;max-width:100%}
/* ── HERO ARTWORK KNOBS ──────────────────────────────────────────────────────
   Tune these three values to size/position the mockup. It is absolutely
   positioned so it is NOT limited by the height of the text column — that's
   what lets it run from the top of the page down past the fold.
     --art-w : how wide the artwork is (vw = % of window width). Bigger = larger.
     --art-x : where its left edge starts (% across the window). Bigger = further right.
     --art-y : vertical offset (px). Negative pushes it up off the top.
   The text column is --copy-w wide; keep --art-x above roughly that width so
   only the artwork's transparent corner overlaps the copy.

   Width is the smaller of two limits, so the whole mockup is visible without
   scrolling on any window shape:
     --art-w    : the width we would like (share of window width)
     --art-fit  : the width that still fits the fold, derived from the image's
                  own aspect ratio (1367/1151 = 1.1877) and the space below the
                  hero top. On a wide-but-short window this one wins.
   `left` is then computed from the resulting width rather than being a fixed
   percentage, so --art-cut stays an exact quarter whichever limit applies.     */
:root{--art-w:70vw;--art-cut:.12;--art-ratio:1.1877;--art-y:-10px;--copy-w:600px;
--wrap-max:1180px;--wrap-pad:26px;
--art-fit:calc((100vh - 60px) * var(--art-ratio));
--art-actual:min(var(--art-w), var(--art-fit));
/* .art is absolute inside .hero, so `left` resolves against .hero -- not the
   viewport. .hero sits inside the centred .wrap, so subtract that offset or the
   artwork lands one gutter too far right. */
--gap-left:calc(max(0px, (100vw - var(--wrap-max)) / 2) + var(--wrap-pad))}
.hero{position:relative;min-height:660px;margin:30px 0 12px}
.hero-left{max-width:var(--copy-w);position:relative;z-index:2}
.hero h1{font:700 50px/1.07 Plus Jakarta Sans,Inter,system-ui,Segoe UI,Roboto,sans-serif;letter-spacing:-.035em;margin:0 0 20px}
.hero p{color:var(--mut);margin:0 0 28px;font-size:16.5px;line-height:1.6}
.hero .art{position:absolute;top:var(--art-y);width:var(--art-actual);
/* Never let the artwork intrude on the copy column: on narrower windows the
   crop-derived position would slide left over the feature text, which renders
   above it and would sit on the mockup's dark sidebar. Legibility wins, so the
   artwork is pushed right (cropping a little more) instead. */
left:max(var(--copy-w),
         calc(100vw - (1 - var(--art-cut)) * var(--art-actual) - var(--gap-left)));
z-index:1;pointer-events:none}
/* Shadow is cast back toward the copy (negative X), so the artwork reads as lifted
   above the text column rather than just floating over a flat page. Two layers: a
   wide soft one for the lift, a tight one to seat the near edge. */
.hero .art img{width:100%;max-width:none;height:auto;display:block;
filter:drop-shadow(-30px 26px 52px rgba(20,30,60,.22)) drop-shadow(-6px 10px 18px rgba(20,30,60,.11))}
html[data-theme="dark"] .hero .art img{filter:drop-shadow(-30px 26px 58px rgba(0,0,0,.62)) drop-shadow(-6px 10px 18px rgba(0,0,0,.45))}
.herolinks{display:flex;gap:11px;flex-wrap:wrap;margin-bottom:44px}
.herolinks .pbtn{padding:11px 20px;font-size:14.5px}
/* feature grid sits inside the left column, so it stays clear of the artwork */
.feats{display:grid;grid-template-columns:1fr 1fr;gap:26px 30px;margin:0}
.feat{display:flex;gap:14px;align-items:flex-start}
.feat .fi{width:26px;height:26px;flex-shrink:0;color:var(--accent);margin-top:2px}
.feat .fi svg{width:26px;height:26px}
.feat h4{margin:0 0 6px;font:700 16.5px Plus Jakarta Sans,Inter,system-ui,Segoe UI,Roboto,sans-serif;letter-spacing:-.01em}
.feat p{margin:0;color:var(--mut);font-size:14.5px;line-height:1.55}
@media(max-width:1000px){
  .hero{min-height:0;margin-top:20px}
  .hero h1{font-size:34px}
  .herolinks{margin-bottom:28px}
  .hero .art{position:static;width:100%;margin:22px 0 6px}   /* stack under the copy */
  .feats{grid-template-columns:1fr;gap:22px}
}
.sec{font:700 12px Plus Jakarta Sans,Inter,system-ui,Segoe UI,Roboto,sans-serif;letter-spacing:.07em;text-transform:uppercase;color:var(--mut);margin:26px 0 12px}
.grid{display:grid;gap:14px}.g4{grid-template-columns:repeat(4,1fr)}.g2{grid-template-columns:repeat(2,1fr)}
@media(max-width:820px){.g4{grid-template-columns:1fr 1fr}.g2{grid-template-columns:1fr}}
.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:20px;box-shadow:var(--shadow)}
.card h3{margin:0 0 14px;font:700 15px Plus Jakarta Sans,Inter,system-ui,Segoe UI,Roboto,sans-serif}
.kpi .v{font:700 30px Plus Jakarta Sans,Inter,system-ui,Segoe UI,Roboto,sans-serif;font-variant-numeric:tabular-nums;letter-spacing:-.02em}
.kpi .l{color:var(--mut);font-size:12.5px;margin-top:3px}
.kpi .sub{color:var(--mut);font-size:11.5px;margin-top:7px;display:flex;gap:9px;flex-wrap:wrap}
.dot{width:8px;height:8px;border-radius:50%;display:inline-block;margin-right:5px}
.pcard{display:block;text-decoration:none;color:inherit;background:var(--card);border:1px solid var(--line);
border-radius:18px;padding:22px;box-shadow:var(--shadow);transition:all .16s}
.pcard:hover{transform:translateY(-3px);box-shadow:var(--shadow-lg);border-color:var(--accent)}
.pc-top{display:flex;align-items:center;gap:12px;margin-bottom:16px}
.pc-top img{width:38px;height:38px;border-radius:10px}
.pc-name{font:700 17px Plus Jakarta Sans,Inter,system-ui,Segoe UI,Roboto,sans-serif}.pc-win{color:var(--mut);font-size:12.5px;margin-top:1px}
.pc-stats{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}
.pc-stat .v{font:700 20px Plus Jakarta Sans,Inter,system-ui,Segoe UI,Roboto,sans-serif;font-variant-numeric:tabular-nums}
.pc-stat .k{color:var(--mut);font-size:11.5px}
.pc-go{margin-top:16px;color:var(--accent);font:600 13px Plus Jakarta Sans,Inter,system-ui,Segoe UI,Roboto,sans-serif}
.pc-setup{color:var(--mut);font-size:13.5px}
.sbar{display:flex;height:12px;border-radius:6px;overflow:hidden;background:var(--btn-alt);margin:4px 0 10px}
.donut{display:flex;align-items:center;gap:20px}.donut svg{flex-shrink:0}
.lcol{font-size:13.5px}.lcol .lgr{margin:6px 0;display:flex;align-items:center;gap:2px;color:var(--ink)}
.lcol .lgr b{margin-left:6px}
.lg{display:flex;gap:16px;flex-wrap:wrap;color:var(--mut);font-size:12.5px;margin-top:8px}
.foot{color:var(--mut);font-size:12.5px;text-align:center;padding:24px;border-top:1px solid var(--line);margin-top:34px}
"""

THEME_JS = ("<script>(function(){var k='hintel-theme';function a(v){if(v==='dark'||v==='light')"
            "document.documentElement.setAttribute('data-theme',v);else document.documentElement.removeAttribute('data-theme');}"
            "a(localStorage.getItem(k)||'dark');document.addEventListener('DOMContentLoaded',function(){var b=document.getElementById('themeBtn');if(!b)return;"
            "b.onclick=function(){var c=localStorage.getItem(k)||'dark';var n=c==='auto'?'dark':(c==='dark'?'light':'auto');localStorage.setItem(k,n);a(n);};});"
            "window.addEventListener('storage',function(e){if(e.key===k)a(e.newValue||'dark');});})();</script>")


def load(p):
    try:
        return json.load(open(f'data/hub/{p}.json', encoding='utf-8'))
    except Exception:
        return None


def fmt(n):
    n = float(n)
    if n >= 1_000_000: return f'{n/1_000_000:.1f}M'.replace('.0M', 'M')
    if n >= 10_000:    return f'{n/1000:.0f}K'
    if n >= 1000:      return f'{n/1000:.1f}K'.replace('.0K', 'K')
    return f'{int(n):,}'


def multi_area(series, height=190):
    """One chart, one line per platform (shared date axis, own colour)."""
    dates = sorted({d for s in series for d, _ in s['daily']})
    if not dates: return '<div class="pc-setup">No data.</div>'
    W, padL, padR, padT, padB = 1000, 8, 8, 12, 26
    mx = max((v for s in series for _, v in s['daily']), default=1) or 1
    X = lambda i: padL + i * ((W - padL - padR) / max(len(dates) - 1, 1))
    Y = lambda v: height - padB - (v / mx) * (height - padT - padB)
    out, legend = '', ''
    for s in series:
        m = dict(s['daily'])
        pts = [(X(i), Y(m.get(d, 0))) for i, d in enumerate(dates)]
        path = f'M{pts[0][0]:.1f},{pts[0][1]:.1f}'
        for i in range(1, len(pts)):
            (px, py), (x, y) = pts[i-1], pts[i]
            cx = (px + x) / 2
            path += f' C{cx:.1f},{py:.1f} {cx:.1f},{y:.1f} {x:.1f},{y:.1f}'
        gid = 'g' + s['key']
        out += (f'<defs><linearGradient id="{gid}" x1="0" x2="0" y1="0" y2="1">'
                f'<stop offset="0" stop-color="{s["color"]}" stop-opacity=".22"/>'
                f'<stop offset="1" stop-color="{s["color"]}" stop-opacity="0"/></linearGradient></defs>'
                f'<path d="{path} L{pts[-1][0]:.1f},{height-padB} L{pts[0][0]:.1f},{height-padB} Z" fill="url(#{gid})"/>'
                f'<path d="{path}" fill="none" stroke="{s["color"]}" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>')
        legend += f'<span><span class="dot" style="background:{s["color"]}"></span>{E(s["label"])}</span>'
    step = max(1, len(dates) // 8)
    labs = ''.join(f'<text x="{X(i):.0f}" y="{height-7}" text-anchor="middle" style="fill:var(--mut);font-size:10px">{d[5:]}</text>'
                   for i, d in enumerate(dates) if i % step == 0)
    return (f'<svg viewBox="0 0 {W} {height}" width="100%">{out}{labs}</svg>'
            f'<div class="lg">{legend}</div>')



def donut_html(segs, center_val, center_sub='total'):
    """Same donut the Reddit and Discord dashboards draw, so the three pages agree.
    `segs` values may be percentages or raw counts -- they are normalised either way.
    The track uses var(--btn-alt) so it stays legible in both themes."""
    import math as _m
    total = sum(v for _, v, _ in segs) or 1
    R = 40; C = 2 * _m.pi * R; off = 0.0; rings = ''
    for _, v, col in segs:
        if v <= 0:
            continue
        ln = v / total * C
        rings += (f'<circle r="{R}" cx="60" cy="60" fill="none" stroke="{col}" stroke-width="15" '
                  f'stroke-dasharray="{ln:.2f} {C-ln:.2f}" stroke-dashoffset="{-off:.2f}" '
                  f'transform="rotate(-90 60 60)"/>')
        off += ln
    leg = ''.join(f'<div class="lgr"><span class="dot" style="background:{col}"></span>'
                  f'{E(lab)} <b>{round(v/total*100)}%</b></div>' for lab, v, col in segs)
    return (f'<div class="donut"><svg viewBox="0 0 120 120" width="106" height="106">'
            f'<circle r="{R}" cx="60" cy="60" fill="none" stroke="var(--btn-alt)" stroke-width="15"/>{rings}'
            f'<text x="60" y="57" text-anchor="middle" style="fill:var(--ink);font-size:21px;font-weight:700">{fmt(center_val)}</text>'
            f'<text x="60" y="73" text-anchor="middle" style="fill:var(--mut);font-size:9px">{E(center_sub)}</text></svg>'
            f'<div class="lcol">{leg}</div></div>')


def main():
    plats = []
    for key, default_label, color, dash_title in ORDER:
        d = load(key)
        if d: plats.append({**d, 'key': key, 'color': color,
                            'label': d.get('label', default_label),
                            'title': dash_title})
    live = [p for p in plats if p.get('connected', True) and p.get('stats')]

    # ---- combined rollup across every connected platform
    roll = {'activity': 0, 'people': 0, 'new_people': 0, 'attention': 0}
    pos_w = neg_w = wsum = 0
    for p in live:
        r = p.get('roll') or {}
        for k in roll: roll[k] += int(r.get(k, 0) or 0)
        a = int(r.get('activity', 0) or 0)
        pos_w += float(r.get('pos', 0) or 0) * a; neg_w += float(r.get('neg', 0) or 0) * a; wsum += a
    pos = (pos_w / wsum) if wsum else 0
    neg = (neg_w / wsum) if wsum else 0
    neu = max(0.0, 100 - pos - neg)

    # ---- top bar platform buttons
    btns = ''
    for p in plats:
        icon = p.get('icon', f'public/{p["key"]}_icon.png')
        off = '' if (p.get('connected', True) and p.get('stats')) else ' off'
        btns += (f'<a class="pbtn{off}" href="{E(p["href"])}"><img src="{E(icon)}" alt="">{E(p["title"])}</a>')

    # ---- hero
    hero_links = ''.join(f'<a class="pbtn" href="{E(p["href"])}"><img src="{E(p.get("icon",""))}" alt="">Open {E(p["title"])}</a>'
                         for p in plats)
    hero_open = (f'<section class="hero"><div class="hero-left">'
                 f'<a class="brand" href="index.html"><img src="public/log.png" alt="ℏIntel">'
                 f'<b><span class="h">ℏ</span>Intel</b></a>'
                 f'<h1>Hedera Community Intelligence</h1>'
                 f'<p>Track the conversation across Reddit and Discord in one place. Follow mentions, '
                 f'surface sentiment and catch moderation risks before they escalate.</p>'
                 f'<div class="herolinks">{hero_links}</div>')
    hero_close = ('</div><div class="art">'
                  '<img src="public/landing%20page.png" alt="ℏIntel dashboard" loading="eager"></div></section>')

    ICO = {
        'mentions': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>',
        'risk': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="M12 8v4"/><path d="M12 16h.01"/></svg>',
        'growth': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/></svg>',
        'report': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>',
    }
    FEATS = [
        ('mentions', 'Every mention, both platforms',
         'Reddit posts and Discord messages in one feed, so nothing is missed across sources.'),
        ('risk', 'Catch risks early',
         'Scams, impersonation and negative spikes are flagged into an action queue with links back to the source.'),
        ('growth', 'Understand growth',
         'Member joins, first-time posters and returning contributors tracked over time, per platform.'),
        ('report', 'Report without the busywork',
         'Weekly staff updates, period comparisons and PDF export generated straight from the data.'),
    ]
    feats = '<div class="feats">' + ''.join(
        f'<div class="feat"><span class="fi">{ICO[k]}</span><div><h4>{E(t)}</h4><p>{E(d)}</p></div></div>'
        for k, t, d in FEATS) + '</div>'

    # ---- combined KPIs
    split = ''.join(
        '<span><span class="dot" style="background:{c}"></span>{lbl} {v}</span>'.format(
            c=p['color'], lbl=E(p['label'].split()[-1]), v=fmt((p.get('roll') or {}).get('activity', 0)))
        for p in live)
    n_plat = f'across {len(live)} platform' + ('s' if len(live) != 1 else '')
    att_col = 'var(--bad)' if roll['attention'] else 'var(--good)'
    kpis = (f'<div class="grid g4">'
            f'<div class="card kpi"><div class="v">{fmt(roll["activity"])}</div>'
            f'<div class="l">Total activity · last 30 days</div><div class="sub">{split}</div></div>'
            f'<div class="card kpi"><div class="v">{fmt(roll["people"])}</div>'
            f'<div class="l">Active people</div><div class="sub">{n_plat}</div></div>'
            f'<div class="card kpi"><div class="v">{fmt(roll["new_people"])}</div>'
            f'<div class="l">New joiners &amp; first-time posters</div></div>'
            f'<div class="card kpi"><div class="v" style="color:{att_col}">{roll["attention"]}</div>'
            f'<div class="l">Flagged, needs attention</div></div></div>')

    # ---- combined activity chart + sentiment
    chart = multi_area([{'key': p['key'], 'label': p['label'], 'color': p['color'], 'daily': p.get('daily', [])}
                        for p in live if p.get('daily')])
    sentiment = (f'<div class="card"><h3>Community sentiment · combined</h3>'
                 + donut_html([('Positive', pos, '#10b981'), ('Neutral', neu, '#cbd5e1'),
                               ('Negative', neg, '#f43f5e')], roll['activity'], 'messages')
                 + f'<div class="pc-setup" style="margin-top:12px">Weighted by each platform\'s volume; '
                   f'same hybrid classifier across sources.</div></div>')

    # ---- per-platform breakdown
    cards = ''
    for p in plats:
        icon = p.get('icon', f'public/{p["key"]}_icon.png')
        connected = p.get('connected', True) and p.get('stats')
        top = (f'<div class="pc-top"><img src="{E(icon)}" alt=""><div>'
               f'<div class="pc-name">{E(p["title"])}</div>'
               f'<div class="pc-win">{E(p["label"])} · {E(p.get("window","—"))}</div></div></div>')
        if connected:
            body = ('<div class="pc-stats">' + ''.join(
                f'<div class="pc-stat"><div class="v">{E(s["v"])}</div><div class="k">{E(s["k"])}</div></div>'
                for s in p['stats'][:4]) + '</div><div class="pc-go">Open full dashboard →</div>')
        else:
            body = '<div class="pc-setup">Not connected yet — open to set up the feed.</div><div class="pc-go">Set up →</div>'
        cards += f'<a class="pcard" href="{E(p["href"])}">{top}{body}</a>'

    gen = datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')
    doc = f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Cache-Control" content="no-cache">
<title>ℏIntel — Hedera Community Intelligence</title><link rel="icon" href="public/log.png"><link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>{CSS}</style>{THEME_JS}</head><body>
<div class="wrap">
  {hero_open}{feats}{hero_close}
  <div class="sec">Across all platforms</div>
  {kpis}
  <div class="grid g2" style="margin-top:14px">
    <div class="card"><h3>Activity over time</h3>{chart}</div>
    {sentiment}
  </div>
  <div class="sec">By platform</div>
  <div class="grid g2">{cards}</div>
</div>
<div class="foot">ℏIntel · intels.app · generated {gen} · each platform has its own dashboard with Compare, Weekly and PDF</div>
</body></html>"""
    with open(OUT, 'w', encoding='utf-8') as f:
        f.write(doc)
    print(f'Hub written: {OUT}  ({len(live)} live platform(s))')


if __name__ == '__main__':
    main()
