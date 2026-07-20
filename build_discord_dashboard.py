# -*- coding: utf-8 -*-
"""
Build discord.html — ℏIntel community dashboard for the Hedera Discord,
mirroring the r/Hedera page: activity, contributors, channels, hourly heatmap,
sentiment (same hybrid classifier), and a negative-message attention list.

Reads data/discord_hedera/messages.csv (produced by fetch_discord.py).
With no data yet it writes a setup page, so the dashboard link never 404s.

Run:  python -X utf8 build_discord_dashboard.py [--days 14]
"""
import argparse, html, json, os, re
from datetime import datetime, timedelta

import pandas as pd

import hintel_sentiment as hs

CSV_PATH = 'data/discord_hedera/messages.csv'
OUT = 'discord.html'
E = lambda s: html.escape(str(s), quote=True)

THEME_CSS = """
:root{--bg:#f3f5fa;--card:#ffffff;--ink:#1d2540;--mut:#7a85a3;--line:#e7ebf3;--accent:#5865F2;--good:#22c55e;--warn:#f59e0b;--bad:#ef4444;--blue:#3b82f6;--tag-bg:#eef2fb;--logo-bg:#fff}
html[data-theme="dark"]{--bg:#0f1217;--card:#181c24;--ink:#e6e9f0;--mut:#8b95a8;--line:#262b35;--tag-bg:#262b35;--logo-bg:#262b35}
@media (prefers-color-scheme: dark){html:not([data-theme="light"]){--bg:#0f1217;--card:#181c24;--ink:#e6e9f0;--mut:#8b95a8;--line:#262b35;--tag-bg:#262b35;--logo-bg:#262b35}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14.5px/1.55 Inter,system-ui,Segoe UI,Roboto,sans-serif;letter-spacing:-.005em}
.wrap{max-width:1060px;margin:0 auto;padding:30px 26px 80px}
.top{display:flex;align-items:center;gap:14px;flex-wrap:wrap;margin-bottom:6px}
h1{font-size:26px;font-weight:600;letter-spacing:-.01em;margin:0}
.meta{color:var(--mut);font-size:13px;margin-bottom:20px}
.pswitch{margin-left:auto;display:inline-flex;border:1px solid var(--line);border-radius:8px;overflow:hidden}
.pswitch a{padding:8px 15px;font:600 13px Inter,system-ui;color:var(--mut);text-decoration:none}
.pswitch a:hover{background:var(--tag-bg);color:var(--ink)}
.pswitch a.on{background:var(--accent);color:#fff}
.theme-toggle{background:transparent;border:1px solid var(--line);color:var(--mut);border-radius:8px;padding:7px;cursor:pointer;display:inline-flex;margin-left:8px}
.theme-toggle svg{width:16px;height:16px}.theme-toggle:hover{color:var(--accent);border-color:var(--accent)}
.grid{display:grid;gap:14px}.g4{grid-template-columns:repeat(4,1fr)}.g2{grid-template-columns:repeat(2,1fr)}
@media(max-width:760px){.g4{grid-template-columns:1fr 1fr}.g2{grid-template-columns:1fr}}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px;box-shadow:0 1px 3px rgba(20,30,60,.05)}
.card h3{margin:0 0 14px;font:700 15px Inter,system-ui;color:var(--ink)}
.kpi .v{font-size:28px;font-weight:700;font-variant-numeric:tabular-nums}
.kpi .l{color:var(--mut);font-size:12.5px;margin-top:2px}
.delta{font-size:12px;font-weight:600;margin-left:7px}.up{color:var(--good)}.down{color:var(--bad)}
.hbar{display:flex;align-items:center;gap:10px;margin:7px 0;font-size:13px}
.hbar .nm{width:150px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.hbar .bar{flex:1;height:8px;border-radius:4px;background:var(--tag-bg);overflow:hidden}
.hbar .bar span{display:block;height:100%;background:var(--accent);border-radius:4px}
.hbar .n{width:56px;text-align:right;font-variant-numeric:tabular-nums;color:var(--mut)}
.heat{display:flex;flex-direction:column;gap:3px}.hrow{display:flex;align-items:center;gap:3px}
.hlab{width:32px;font-size:10px;color:var(--mut)}.hcell{flex:1;min-width:7px;height:14px;border-radius:2px}
.sbar{display:flex;height:12px;border-radius:6px;overflow:hidden;background:var(--tag-bg);margin:6px 0 10px}
.msg{padding:11px 0;border-bottom:1px solid var(--line);font-size:13.5px}.msg:last-child{border:none}
.msg .mh{color:var(--mut);font-size:12px;margin-bottom:3px}.msg .mh b{color:var(--ink)}
.chip{display:inline-block;background:var(--tag-bg);border-radius:999px;padding:2px 9px;font-size:11px;color:var(--mut);margin-left:8px}
.setup li{margin:8px 0}
.foot{color:var(--mut);font-size:12px;margin-top:34px;border-top:1px solid var(--line);padding-top:16px}
a{color:var(--blue);text-decoration:none}a:hover{text-decoration:underline}
"""

THEME_JS = """
<script>(function(){var k='hintel-theme';function a(v){if(v==='dark'||v==='light')document.documentElement.setAttribute('data-theme',v);else document.documentElement.removeAttribute('data-theme');}
a(localStorage.getItem(k)||'auto');document.addEventListener('DOMContentLoaded',function(){var b=document.getElementById('themeBtn');if(!b)return;
b.onclick=function(){var c=localStorage.getItem(k)||'auto';var n=c==='auto'?'dark':(c==='dark'?'light':'auto');localStorage.setItem(k,n);a(n);};});
window.addEventListener('storage',function(e){if(e.key===k)a(e.newValue||'auto');});})();</script>
"""

HEADER = """<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ℏIntel — Hedera Discord</title><link rel="icon" href="public/log.png">
<style>{css}</style>{js}</head><body><div class="wrap">
<div class="top"><a href="index.html" title="ℏIntel hub"><img src="public/log.png" alt="ℏIntel" style="width:34px;height:34px;border-radius:8px;background:var(--logo-bg);padding:3px"></a>
<h1><span style="font-weight:400">ℏ</span>Intel <span style="color:var(--mut);font-weight:400;font-size:19px">— Hedera Discord</span></h1>
<span class="pswitch"><a href="reddit.html">Reddit</a><a class="on" href="discord.html">Discord</a></span>
<button class="theme-toggle" id="themeBtn" type="button" title="Toggle theme" style="margin-left:8px"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg></button></div>
"""

FOOT = ('<div class="foot">ℏIntel · Discord data via official Bot API (fetch_discord.py) · '
        'sentiment uses the same hybrid classifier as the Reddit dashboard.</div>')

def _page_password():
    try:
        return (json.load(open('discord_config.json', encoding='utf-8')).get('page_password') or '').strip()
    except Exception:
        return ''

def _encrypt_gate(inner_html):
    """AES-GCM encrypt the sensitive body; the page ships a lock screen + a Web-Crypto
    decryptor. Without the password the source contains only ciphertext (real protection,
    works on static hosting). PBKDF2-SHA256(210k) -> AES-256-GCM, matching SubtleCrypto."""
    import base64, os as _os
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    pw = _page_password().encode()
    salt, iv = _os.urandom(16), _os.urandom(12)
    key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=210000).derive(pw)
    ct = AESGCM(key).encrypt(iv, inner_html.encode('utf-8'), None)
    b64 = lambda x: base64.b64encode(x).decode()
    blob = json.dumps({'s': b64(salt), 'i': b64(iv), 'c': b64(ct), 'n': 210000})
    return ('<div id="lock" style="max-width:420px;margin:12vh auto;padding:0 20px;text-align:center">'
            '<div style="font:600 18px Inter,system-ui;color:var(--ink);margin-bottom:6px">🔒 Moderators only</div>'
            '<div class="meta" style="margin-bottom:18px">This Discord dashboard contains member names and messages. '
            'Enter the moderator password to view.</div>'
            '<input id="pw" type="password" placeholder="Password" style="width:100%;padding:11px 13px;border:1px solid var(--line);'
            'border-radius:9px;background:var(--card);color:var(--ink);font:15px Inter,system-ui" '
            'onkeydown="if(event.key===\'Enter\')unlock()">'
            '<div id="err" style="color:var(--bad);font-size:13px;margin-top:8px;min-height:18px"></div>'
            '<button onclick="unlock()" style="margin-top:6px;width:100%;padding:11px;border:none;border-radius:9px;'
            'background:var(--accent);color:#fff;font:600 14px Inter,system-ui;cursor:pointer">Unlock</button></div>'
            '<div id="content"></div>'
            f'<script>var BLOB={blob};'
            'async function unlock(){var pw=document.getElementById("pw").value;var e=document.getElementById("err");e.textContent="";'
            'try{var dec=new TextDecoder(),enc=new TextEncoder();var b=function(s){return Uint8Array.from(atob(s),function(c){return c.charCodeAt(0)})};'
            'var km=await crypto.subtle.importKey("raw",enc.encode(pw),"PBKDF2",false,["deriveKey"]);'
            'var key=await crypto.subtle.deriveKey({name:"PBKDF2",salt:b(BLOB.s),iterations:BLOB.n,hash:"SHA-256"},km,{name:"AES-GCM",length:256},false,["decrypt"]);'
            'var pt=await crypto.subtle.decrypt({name:"AES-GCM",iv:b(BLOB.i)},key,b(BLOB.c));'
            'document.getElementById("lock").style.display="none";document.getElementById("content").innerHTML=dec.decode(pt);'
            'try{sessionStorage.setItem("hintel-dpw",pw)}catch(_){}}catch(err){e.textContent="Wrong password."}}'
            'var saved=sessionStorage.getItem("hintel-dpw");if(saved){document.getElementById("pw").value=saved;unlock();}'
            '</script>')

def write(body, gate=False):
    inner = _encrypt_gate(body + FOOT) if gate else (body + FOOT)
    with open(OUT, 'w', encoding='utf-8') as f:
        f.write(HEADER.format(css=THEME_CSS, js=THEME_JS) + inner + '</div></body></html>')
    print(f'Dashboard written: {OUT}' + (' (password-protected)' if gate else ''))

def setup_page():
    write("""
<div class="meta">No Discord data yet — this page activates automatically once the bot feed lands.</div>
<div class="card"><h3>Connect the Hedera Discord (one-time)</h3><ol class="setup">
<li>Create a bot at <b>discord.com/developers/applications</b> → New Application → Bot. Enable <b>Message Content Intent</b>. Copy the token.</li>
<li>Invite it to the server (OAuth2 → URL Generator: scope <b>bot</b>; permissions <b>View Channels</b> + <b>Read Message History</b>). A server admin must accept — same as the Notion connection, ask Abdoul/the Discord admin.</li>
<li>Save <b>discord_config.json</b> next to the scripts: <code>{"token":"BOT_TOKEN","guild_id":"SERVER_ID","channels":[]}</code></li>
<li>Run <code>python -X utf8 fetch_discord.py</code> then <code>python -X utf8 build_discord_dashboard.py</code>.</li>
</ol><div class="meta" style="margin-top:10px">Only the official Bot API is used — no user-token exports (Discord ToS).</div></div>""")
    try:
        os.makedirs('data/hub', exist_ok=True)
        json.dump({'platform': 'discord', 'label': 'Hedera Discord', 'href': 'discord.html',
                   'connected': False, 'window': 'Not connected yet', 'stats': []},
                  open('data/hub/discord.json', 'w', encoding='utf-8'))
    except Exception:
        pass

def area_svg(daily, color='#5865F2'):
    if not daily: return '<div class="meta">No data.</div>'
    W, H, pad = 1000, 150, 8
    mx = max(c for _, c in daily) or 1
    X = lambda i: pad + i * ((W - 2 * pad) / max(len(daily) - 1, 1))
    Y = lambda v: H - 24 - (v / mx) * (H - 42)
    line = ' '.join(f'{X(i):.1f},{Y(c):.1f}' for i, (_, c) in enumerate(daily))
    fill = f'{X(0):.1f},{H-24} {line} {X(len(daily)-1):.1f},{H-24}'
    step = max(1, len(daily) // 8)
    labs = ''.join(f'<text x="{X(i):.0f}" y="{H-6}" text-anchor="middle" style="fill:var(--mut);font-size:10px">{d[5:]}</text>'
                   for i, (d, _) in enumerate(daily) if i % step == 0)
    return (f'<svg viewBox="0 0 {W} {H}" width="100%"><defs><linearGradient id="dg" x1="0" x2="0" y1="0" y2="1">'
            f'<stop offset="0" stop-color="{color}" stop-opacity=".28"/><stop offset="1" stop-color="{color}" stop-opacity="0"/></linearGradient></defs>'
            f'<polygon points="{fill}" fill="url(#dg)"/><polyline points="{line}" fill="none" stroke="{color}" stroke-width="2.4" '
            f'stroke-linecap="round" stroke-linejoin="round"/>{labs}</svg>')

def hbars(pairs, total):
    if not pairs: return '<div class="meta">No data.</div>'
    mx = max(n for _, n in pairs) or 1
    return ''.join(f'<div class="hbar"><span class="nm">{E(nm)}</span><span class="bar"><span style="width:{n/mx*100:.1f}%"></span></span>'
                   f'<span class="n">{n:,}</span></div>' for nm, n in pairs)

def heatmap(hm, mx):
    days = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun']
    out = '<div class="heat">'
    for di, row in enumerate(hm):
        out += f'<div class="hrow"><span class="hlab">{days[di]}</span>'
        for c in row:
            a = (c / mx) if mx else 0
            bg = f'rgba(88,101,242,{0.15 + a*0.85:.2f})' if a else 'var(--tag-bg)'
            out += f'<span class="hcell" style="background:{bg}"></span>'
        out += '</div>'
    return out + '</div><div class="meta" style="font-size:11px;margin-top:7px">Messages by day-of-week × hour (UTC) · darker = busier</div>'

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--days', type=int, default=14)
    args = ap.parse_args()

    if not os.path.exists(CSV_PATH):
        setup_page(); return
    raw = pd.read_csv(CSV_PATH, low_memory=False)
    if not len(raw):
        setup_page(); return
    raw['created_utc'] = pd.to_datetime(raw['created_utc'], errors='coerce')
    raw = raw.dropna(subset=['created_utc'])
    raw['channel'] = raw['channel'].astype(str)
    latest = raw['created_utc'].max()
    start = latest - timedelta(days=args.days - 1)
    prev_start = start - timedelta(days=args.days)

    # New members: each entry in the join-log channel is one join (embed, no text).
    JOIN_RE = raw['channel'].str.contains('join', case=False) & raw['channel'].str.contains('log', case=False)
    joins = raw[JOIN_RE]
    new_members = int(((joins['created_utc'] >= start)).sum())
    prev_members_j = int(((joins['created_utc'] >= prev_start) & (joins['created_utc'] < start)).sum())

    # Community view: humans only, and exclude bot-log / mod-internal / system channels
    EXCLUDE = re.compile(r'log|dyno|carl-?bot|wick|mods?-chat|user-join|audit|closed-\d|capture-the-flag', re.I)
    df = raw[(raw['bot'] != 1) & (~raw['channel'].str.contains(EXCLUDE))]
    w = df[df['created_utc'] >= start]
    pw = df[(df['created_utc'] >= prev_start) & (df['created_utc'] < start)]

    n, pn = len(w), len(pw)
    members, pmembers = w['author_id'].nunique(), pw['author_id'].nunique()
    reacts = int(w['reactions'].fillna(0).sum())
    per_day = n / max(args.days, 1)
    def delta(cur, prev):
        if not prev: return ''
        d = (cur - prev) / prev * 100
        cls = 'up' if d >= 0 else 'down'
        return f'<span class="delta {cls}">{"▲" if d>=0 else "▼"} {abs(d):.0f}%</span>'

    daily = w.set_index('created_utc').resample('D').size()
    daily = [(d.strftime('%Y-%m-%d'), int(v)) for d, v in daily.items()]
    chans = w.groupby('channel').size().sort_values(ascending=False)
    chan_pairs = [(f'#{c}', int(v)) for c, v in chans.head(10).items()]
    tops = w.groupby('author').size().sort_values(ascending=False)
    top_pairs = [(a, int(v)) for a, v in tops.head(10).items()]
    hm = [[0]*24 for _ in range(7)]
    for t in w['created_utc']:
        hm[t.weekday()][t.hour] += 1
    hmx = max(max(r) for r in hm) if n else 0

    texts = w['content'].fillna('').astype(str)
    labs = [hs.classify_text(t) if t.strip() else ('neutral', 0.0) for t in texts]
    w = w.assign(_lab=[l for l, _ in labs], _sc=[s for _, s in labs])
    pos = int((w['_lab'] == 'positive').sum()); neg = int((w['_lab'] == 'negative').sum())
    neu = n - pos - neg
    negs = w[w['_lab'] == 'negative'].sort_values('_sc').head(12)

    b = (f'<div class="meta">Window: <b>{start:%d %b %Y} → {latest:%d %b %Y}</b> ({args.days} days) · '
         f'community channels, humans only (bot-logs &amp; mod-internal channels excluded) · '
         f'generated {datetime.utcnow():%Y-%m-%d %H:%M} UTC</div>')
    b += '<div class="grid g4">'
    b += f'<div class="card kpi"><div class="v">{n:,}{delta(n,pn)}</div><div class="l">Messages · {per_day:.0f}/day</div></div>'
    b += f'<div class="card kpi"><div class="v">{members:,}{delta(members,pmembers)}</div><div class="l">Active members</div></div>'
    b += f'<div class="card kpi"><div class="v">{new_members:,}{delta(new_members,prev_members_j)}</div><div class="l">New members joined</div></div>'
    b += f'<div class="card kpi"><div class="v">{reacts:,}</div><div class="l">Reactions given</div></div>'
    b += '</div>'
    b += f'<div class="card" style="margin-top:14px"><h3>Daily activity</h3>{area_svg(daily)}</div>'
    b += '<div class="grid g2" style="margin-top:14px">'
    b += f'<div class="card"><h3>Busiest channels</h3>{hbars(chan_pairs, n)}</div>'
    b += f'<div class="card"><h3>Top contributors</h3>{hbars(top_pairs, n)}</div>'
    b += '</div>'
    b += '<div class="grid g2" style="margin-top:14px">'
    b += f'<div class="card"><h3>Activity heatmap</h3>{heatmap(hm, hmx)}</div>'
    pp_ = (pos / max(n,1)) * 100; np_ = (neg / max(n,1)) * 100; up = 100 - pp_ - np_
    b += (f'<div class="card"><h3>Sentiment</h3>'
          f'<div class="sbar"><span style="width:{pp_:.1f}%;background:var(--good)"></span>'
          f'<span style="width:{up:.1f}%;background:var(--tag-bg)"></span>'
          f'<span style="width:{np_:.1f}%;background:var(--bad)"></span></div>'
          f'<div class="meta">{pos:,} positive ({pp_:.0f}%) · {neu:,} neutral · {neg:,} negative ({np_:.0f}%)'
          f'<br>Same hybrid classifier as the Reddit dashboard (VADER + domain lexicon + phrase rules).</div></div>')
    b += '</div>'
    b += '<div class="card" style="margin-top:14px"><h3>Needs attention — most negative messages</h3>'
    if len(negs):
        for _, m in negs.iterrows():
            b += (f'<div class="msg"><div class="mh"><b>{E(m["author"])}</b> in #{E(m["channel"])}'
                  f'<span class="chip">{m["created_utc"]:%d %b %H:%M}</span></div>{E(str(m["content"])[:220])}</div>')
    else:
        b += '<div class="meta">No strongly negative messages in this window.</div>'
    b += '</div>'
    gate = bool(_page_password())
    if not gate:
        print('  WARNING: no "page_password" in discord_config.json — page will NOT be '
              'encrypted. Set one before deploying (it contains member names/messages).')
    write(b, gate=gate)

    # headline stats for the ℏIntel hub
    try:
        os.makedirs('data/hub', exist_ok=True)
        json.dump({'platform': 'discord', 'label': 'Hedera Discord',
                   'window': f'Last {args.days} days', 'generated': datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC'),
                   'href': 'discord.html', 'connected': True, 'icon': 'public/discord_icon.png',
                   'stats': [{'k': 'Messages', 'v': n}, {'k': 'Active', 'v': members},
                             {'k': 'New members', 'v': new_members}, {'k': 'Positive', 'v': f'{pp_:.0f}%'}],
                   'roll': {'activity': n, 'people': int(members), 'new_people': int(new_members),
                            'pos': round(pp_), 'neg': round(np_), 'attention': int(len(negs))},
                   'daily': [[d, c] for d, c in daily]},
                  open('data/hub/discord.json', 'w', encoding='utf-8'))
    except Exception:
        pass

if __name__ == '__main__':
    main()
