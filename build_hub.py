# -*- coding: utf-8 -*-
"""
Build index.html — the ℏIntel hub. A platform picker that treats each source
(Reddit, Discord, …) as an equal citizen, each with a card of live headline
stats and a link into its full dashboard.

Reads data/hub/*.json (emitted by build_dashboard.py and build_discord_dashboard.py).
A platform with no json yet renders as "Not connected — set up".

Run:  python -X utf8 build_hub.py
"""
import glob, html, json, os
from datetime import datetime

OUT = 'index.html'
E = lambda s: html.escape(str(s), quote=True)

# platforms in display order; icon is inline SVG so it themes + never 404s
PLATFORMS = [
    ('reddit', 'r/Hedera', '#ff4500',
     '<circle cx="12" cy="12" r="9"/><circle cx="8.5" cy="12" r="1.3" fill="currentColor" stroke="none"/>'
     '<circle cx="15.5" cy="12" r="1.3" fill="currentColor" stroke="none"/>'
     '<path d="M8.5 15c1 .8 2.2 1.2 3.5 1.2S14.5 15.8 15.5 15"/><circle cx="18" cy="6.5" r="1.4"/>'),
    ('discord', 'Hedera Discord', '#5865F2',
     '<path d="M7.5 7.2C9 6.6 10.5 6.3 12 6.3s3 .3 4.5.9"/>'
     '<path d="M8 17.7c-1.9-.4-3.5-1.2-4.6-2.2.2-3 1-5.9 2.6-8.5C7.2 6.2 8.6 5.7 10 5.5"/>'
     '<path d="M16 17.7c1.9-.4 3.5-1.2 4.6-2.2-.2-3-1-5.9-2.6-8.5-1.2-.8-2.6-1.3-4-1.5"/>'
     '<circle cx="9" cy="12.5" r="1"/><circle cx="15" cy="12.5" r="1"/>'),
]

CSS = """
:root{--bg:#f3f5fa;--card:#ffffff;--ink:#1d2540;--mut:#7a85a3;--line:#e7ebf3;--accent:#3b82f6;--good:#22c55e;--logo-bg:#fff;--shadow:0 1px 3px rgba(20,30,60,.06);--shadow-lg:0 20px 50px rgba(20,30,60,.14)}
html[data-theme="dark"]{--bg:#0f1217;--card:#181c24;--ink:#e6e9f0;--mut:#8b95a8;--line:#262b35;--logo-bg:#262b35;--shadow:0 1px 3px rgba(0,0,0,.3);--shadow-lg:0 24px 60px rgba(0,0,0,.6)}
@media (prefers-color-scheme: dark){html:not([data-theme="light"]){--bg:#0f1217;--card:#181c24;--ink:#e6e9f0;--mut:#8b95a8;--line:#262b35;--logo-bg:#262b35;--shadow:0 1px 3px rgba(0,0,0,.3);--shadow-lg:0 24px 60px rgba(0,0,0,.6)}}
*{box-sizing:border-box}body{margin:0;min-height:100vh;background:var(--bg);color:var(--ink);font:15px/1.55 Inter,system-ui,Segoe UI,Roboto,sans-serif;letter-spacing:-.005em;display:flex;flex-direction:column}
.wrap{max-width:940px;margin:0 auto;padding:64px 26px 40px;width:100%}
.hdr{display:flex;align-items:center;gap:14px;margin-bottom:6px}
.hdr img{width:44px;height:44px;border-radius:11px;background:var(--logo-bg);padding:4px}
.hdr h1{font-size:30px;font-weight:600;letter-spacing:-.02em;margin:0}.hdr .h{font-weight:400}
.theme-toggle{margin-left:auto;background:transparent;border:1px solid var(--line);color:var(--mut);border-radius:9px;padding:8px;cursor:pointer;display:inline-flex}
.theme-toggle svg{width:17px;height:17px}.theme-toggle:hover{color:var(--accent);border-color:var(--accent)}
.sub{color:var(--mut);font-size:15px;margin:0 0 34px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:18px}
.pcard{display:block;text-decoration:none;color:inherit;background:var(--card);border:1px solid var(--line);border-radius:18px;padding:22px 24px;box-shadow:var(--shadow);transition:transform .16s ease,box-shadow .16s ease,border-color .16s ease}
.pcard:hover{transform:translateY(-3px);box-shadow:var(--shadow-lg);border-color:var(--accent)}
.pcard.off{opacity:.85}
.pc-top{display:flex;align-items:center;gap:13px;margin-bottom:20px}
.pc-ico{width:44px;height:44px;border-radius:12px;display:flex;align-items:center;justify-content:center;flex-shrink:0}
.pc-ico svg{width:24px;height:24px;fill:none;stroke:#fff;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}
.pc-name{font:700 18px Inter,system-ui}.pc-win{color:var(--mut);font-size:12.5px;margin-top:2px}
.pc-stats{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}
.pc-stat .v{font:700 21px Inter,system-ui;font-variant-numeric:tabular-nums}
.pc-stat .k{color:var(--mut);font-size:11.5px;margin-top:1px}
.pc-go{margin-top:20px;display:inline-flex;align-items:center;gap:6px;color:var(--accent);font:600 13.5px Inter,system-ui}
.pc-setup{margin-top:6px;color:var(--mut);font-size:13.5px}
.foot{margin-top:auto;text-align:center;color:var(--mut);font-size:12.5px;padding:26px}
.foot a{color:var(--accent);text-decoration:none}
"""

THEME_JS = ("<script>(function(){var k='hintel-theme';function a(v){if(v==='dark'||v==='light')"
            "document.documentElement.setAttribute('data-theme',v);else document.documentElement.removeAttribute('data-theme');}"
            "a(localStorage.getItem(k)||'auto');document.addEventListener('DOMContentLoaded',function(){var b=document.getElementById('themeBtn');if(!b)return;"
            "b.onclick=function(){var c=localStorage.getItem(k)||'auto';var n=c==='auto'?'dark':(c==='dark'?'light':'auto');localStorage.setItem(k,n);a(n);};});"
            "window.addEventListener('storage',function(e){if(e.key===k)a(e.newValue||'auto');});})();</script>")


def load(platform):
    try:
        return json.load(open(f'data/hub/{platform}.json', encoding='utf-8'))
    except Exception:
        return None


def card(key, default_label, color, icon):
    d = load(key)
    connected = bool(d) and d.get('connected', True) and d.get('stats')
    label = (d or {}).get('label', default_label)
    href = (d or {}).get('href', f'{key}.html')
    top = (f'<div class="pc-top"><span class="pc-ico" style="background:{color}"><svg viewBox="0 0 24 24">{icon}</svg></span>'
           f'<div><div class="pc-name">{E(label)}</div><div class="pc-win">{E((d or {}).get("window","—"))}</div></div></div>')
    if connected:
        stats = ''.join(f'<div class="pc-stat"><div class="v">{E(s["v"])}</div><div class="k">{E(s["k"])}</div></div>'
                        for s in d['stats'][:4])
        body = (f'<div class="pc-stats">{stats}</div>'
                f'<div class="pc-go">Open dashboard →</div>')
    else:
        body = '<div class="pc-setup">Not connected yet — open to set up the feed.</div><div class="pc-go">Set up →</div>'
    cls = 'pcard' if connected else 'pcard off'
    return f'<a class="{cls}" href="{href}">{top}{body}</a>'


def main():
    cards = ''.join(card(k, lbl, col, ic) for k, lbl, col, ic in PLATFORMS)
    gen = datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')
    doc = f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Cache-Control" content="no-cache">
<title>ℏIntel — Community Intelligence</title><link rel="icon" href="public/log.png">
<style>{CSS}</style>{THEME_JS}</head><body>
<div class="wrap">
  <div class="hdr"><img src="public/log.png" alt="ℏIntel"><h1><span class="h">ℏ</span>Intel</h1>
    <button class="theme-toggle" id="themeBtn" type="button" title="Toggle theme"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg></button>
  </div>
  <p class="sub">Hedera community intelligence across platforms. Pick a source to open its full dashboard.</p>
  <div class="cards">{cards}</div>
</div>
<div class="foot">ℏIntel · intels.app · generated {gen} · each platform is monitored independently</div>
</body></html>"""
    with open(OUT, 'w', encoding='utf-8') as f:
        f.write(doc)
    print(f'Hub written: {OUT}')


if __name__ == '__main__':
    main()
