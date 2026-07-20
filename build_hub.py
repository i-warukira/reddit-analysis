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
ORDER = [('reddit', 'r/Hedera', '#ff4500'), ('discord', 'Hedera Discord', '#5865F2')]

CSS = """
:root{--bg:#f3f5fa;--card:#ffffff;--ink:#1d2540;--mut:#7a85a3;--line:#e7ebf3;--accent:#3b82f6;
--good:#22c55e;--bad:#ef4444;--warn:#f59e0b;--logo-bg:#fff;--hover:#eef2fb;--btn-alt:#eef2fb;
--shadow:0 1px 3px rgba(20,30,60,.06);--shadow-lg:0 18px 44px rgba(20,30,60,.13)}
html[data-theme="dark"]{--bg:#0f1217;--card:#181c24;--ink:#e6e9f0;--mut:#8b95a8;--line:#262b35;
--logo-bg:#262b35;--hover:#262b35;--btn-alt:#262b35;--shadow:0 1px 3px rgba(0,0,0,.3);--shadow-lg:0 22px 55px rgba(0,0,0,.55)}
@media (prefers-color-scheme: dark){html:not([data-theme="light"]){--bg:#0f1217;--card:#181c24;--ink:#e6e9f0;--mut:#8b95a8;
--line:#262b35;--logo-bg:#262b35;--hover:#262b35;--btn-alt:#262b35;--shadow:0 1px 3px rgba(0,0,0,.3);--shadow-lg:0 22px 55px rgba(0,0,0,.55)}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.55 Inter,system-ui,Segoe UI,Roboto,sans-serif;letter-spacing:-.005em}
.topbar{display:flex;align-items:center;gap:12px;padding:14px 26px;background:var(--card);
border-bottom:1px solid var(--line);position:sticky;top:0;z-index:30;flex-wrap:wrap}
.brand{display:flex;align-items:center;gap:10px;text-decoration:none;color:var(--ink);margin-right:auto}
.brand img{width:32px;height:32px;border-radius:8px;background:var(--logo-bg);padding:3px}
.brand b{font:600 18px Inter,system-ui}.brand .h{font-weight:400}
.pbtn{display:inline-flex;align-items:center;gap:8px;border:1px solid var(--line);border-radius:9px;
padding:7px 14px;text-decoration:none;color:var(--ink);font:600 13.5px Inter,system-ui;background:var(--card);transition:all .15s}
.pbtn img{width:17px;height:17px}
.pbtn:hover{border-color:var(--accent);transform:translateY(-1px);box-shadow:var(--shadow)}
.pbtn.off{opacity:.6}
.tt{background:transparent;border:1px solid var(--line);color:var(--mut);border-radius:9px;padding:7px;cursor:pointer;display:inline-flex}
.tt svg{width:16px;height:16px}.tt:hover{color:var(--accent);border-color:var(--accent)}
.wrap{max-width:1180px;margin:0 auto;padding:26px 26px 70px}
.hero{display:grid;grid-template-columns:1.05fr .95fr;gap:26px;align-items:center;margin-bottom:26px}
.hero h1{font:600 30px Inter,system-ui;letter-spacing:-.02em;margin:0 0 10px}
.hero p{color:var(--mut);margin:0 0 18px;font-size:15.5px;max-width:46ch}
.hero img{width:100%;height:auto;display:block;filter:drop-shadow(0 22px 40px rgba(20,30,60,.22))}
.herolinks{display:flex;gap:10px;flex-wrap:wrap}
@media(max-width:860px){.hero{grid-template-columns:1fr}.hero .art{order:-1}}
.sec{font:700 12px Inter,system-ui;letter-spacing:.07em;text-transform:uppercase;color:var(--mut);margin:26px 0 12px}
.grid{display:grid;gap:14px}.g4{grid-template-columns:repeat(4,1fr)}.g2{grid-template-columns:repeat(2,1fr)}
@media(max-width:820px){.g4{grid-template-columns:1fr 1fr}.g2{grid-template-columns:1fr}}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px;box-shadow:var(--shadow)}
.card h3{margin:0 0 14px;font:700 15px Inter,system-ui}
.kpi .v{font:700 30px Inter,system-ui;font-variant-numeric:tabular-nums;letter-spacing:-.02em}
.kpi .l{color:var(--mut);font-size:12.5px;margin-top:3px}
.kpi .sub{color:var(--mut);font-size:11.5px;margin-top:7px;display:flex;gap:9px;flex-wrap:wrap}
.dot{width:8px;height:8px;border-radius:50%;display:inline-block;margin-right:5px}
.pcard{display:block;text-decoration:none;color:inherit;background:var(--card);border:1px solid var(--line);
border-radius:16px;padding:20px;box-shadow:var(--shadow);transition:all .16s}
.pcard:hover{transform:translateY(-3px);box-shadow:var(--shadow-lg);border-color:var(--accent)}
.pc-top{display:flex;align-items:center;gap:12px;margin-bottom:16px}
.pc-top img{width:38px;height:38px;border-radius:10px}
.pc-name{font:700 17px Inter,system-ui}.pc-win{color:var(--mut);font-size:12.5px;margin-top:1px}
.pc-stats{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}
.pc-stat .v{font:700 20px Inter,system-ui;font-variant-numeric:tabular-nums}
.pc-stat .k{color:var(--mut);font-size:11.5px}
.pc-go{margin-top:16px;color:var(--accent);font:600 13px Inter,system-ui}
.pc-setup{color:var(--mut);font-size:13.5px}
.sbar{display:flex;height:12px;border-radius:6px;overflow:hidden;background:var(--btn-alt);margin:4px 0 10px}
.lg{display:flex;gap:16px;flex-wrap:wrap;color:var(--mut);font-size:12.5px;margin-top:8px}
.foot{color:var(--mut);font-size:12.5px;text-align:center;padding:24px;border-top:1px solid var(--line);margin-top:34px}
"""

THEME_JS = ("<script>(function(){var k='hintel-theme';function a(v){if(v==='dark'||v==='light')"
            "document.documentElement.setAttribute('data-theme',v);else document.documentElement.removeAttribute('data-theme');}"
            "a(localStorage.getItem(k)||'auto');document.addEventListener('DOMContentLoaded',function(){var b=document.getElementById('themeBtn');if(!b)return;"
            "b.onclick=function(){var c=localStorage.getItem(k)||'auto';var n=c==='auto'?'dark':(c==='dark'?'light':'auto');localStorage.setItem(k,n);a(n);};});"
            "window.addEventListener('storage',function(e){if(e.key===k)a(e.newValue||'auto');});})();</script>")


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


def main():
    plats = []
    for key, default_label, color in ORDER:
        d = load(key)
        if d: plats.append({**d, 'key': key, 'color': color,
                            'label': d.get('label', default_label)})
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
        btns += (f'<a class="pbtn{off}" href="{E(p["href"])}"><img src="{E(icon)}" alt="">{E(p["label"])}</a>')

    # ---- hero
    hero_links = ''.join(f'<a class="pbtn" href="{E(p["href"])}"><img src="{E(p.get("icon",""))}" alt="">Open {E(p["label"])}</a>'
                         for p in plats)
    hero = (f'<div class="hero"><div><h1>Community intelligence, every platform in one place.</h1>'
            f'<p>ℏIntel tracks the Hedera community across Reddit and Discord — activity, sentiment, '
            f'moderation risks and growth — so nothing needing attention slips through.</p>'
            f'<div class="herolinks">{hero_links}</div></div>'
            f'<div class="art"><img src="public/hero.webp" alt="ℏIntel dashboard" loading="eager"></div></div>')

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
                 f'<div class="sbar"><span style="width:{pos:.1f}%;background:var(--good)"></span>'
                 f'<span style="width:{neu:.1f}%;background:var(--btn-alt)"></span>'
                 f'<span style="width:{neg:.1f}%;background:var(--bad)"></span></div>'
                 f'<div class="lg"><span><span class="dot" style="background:var(--good)"></span>{pos:.0f}% positive</span>'
                 f'<span><span class="dot" style="background:var(--mut)"></span>{neu:.0f}% neutral</span>'
                 f'<span><span class="dot" style="background:var(--bad)"></span>{neg:.0f}% negative</span></div>'
                 f'<div class="pc-setup" style="margin-top:10px">Weighted by each platform\'s volume; same hybrid classifier across sources.</div></div>')

    # ---- per-platform breakdown
    cards = ''
    for p in plats:
        icon = p.get('icon', f'public/{p["key"]}_icon.png')
        connected = p.get('connected', True) and p.get('stats')
        top = (f'<div class="pc-top"><img src="{E(icon)}" alt=""><div>'
               f'<div class="pc-name">{E(p["label"])}</div><div class="pc-win">{E(p.get("window","—"))}</div></div></div>')
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
<title>ℏIntel — Hedera Community Intelligence</title><link rel="icon" href="public/log.png">
<style>{CSS}</style>{THEME_JS}</head><body>
<div class="topbar">
  <a class="brand" href="index.html"><img src="public/log.png" alt="ℏIntel"><b><span class="h">ℏ</span>Intel</b></a>
  {btns}
  <button class="tt" id="themeBtn" type="button" title="Toggle theme"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg></button>
</div>
<div class="wrap">
  {hero}
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
