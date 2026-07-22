# -*- coding: utf-8 -*-
"""
Build discord.html — ℏIntel community dashboard for the Hedera Discord,
mirroring the r/Hedera page: activity, contributors, channels, hourly heatmap,
sentiment (same hybrid classifier), and a negative-message attention list.

Reads data/discord_hedera/messages.csv (produced by fetch_discord.py).
With no data yet it writes a setup page, so the dashboard link never 404s.

Run:  python -X utf8 build_discord_dashboard.py [--days 14]
"""
import argparse, html, json, math, os, re
from datetime import datetime, timedelta

import pandas as pd

import hintel_sentiment as hs

CSV_PATH = 'data/discord_hedera/messages.csv'
OUT = 'discord.html'
E = lambda s: html.escape(str(s), quote=True)

THEME_CSS = """
:root{--bg:#f7f8fd;--card:#ffffff;--ink:#1e2340;--mut:#8b90a8;--line:#eceef6;--accent:#6366f1;--good:#10b981;--warn:#f59e0b;--bad:#ef4444;--blue:#6366f1;--tag-bg:#eef0fb;--logo-bg:#fff;--shadow:0 1px 3px rgba(20,30,60,.06);--shadow-lg:0 10px 30px rgba(20,30,60,.10);--c1:#6366f1;--c2:#8b5cf6;--c3:#2dd4bf;--c4:#f59e0b;--c5:#ec4899;--c-idle:#cbd5e1;
/* Sidebar is dark in both themes -- navy in light mode, near-black in dark mode so
   it sits with the dark surfaces rather than glowing against them. It is never
   white: the light-mode value below is the navy, not a light panel. */
--sb:#2A3A4A;--sb-ink:#aeb9c9;--sb-brand:#ffffff;--sb-active-ink:#ffffff;--sb-hover:rgba(255,255,255,.07);--sb-cnt-bg:rgba(255,255,255,.12);--sb-border:rgba(255,255,255,.09);--sb-note:#93a1b5;--sb-logo-bg:#ffffff}
html[data-theme="dark"]{--bg:#0f1217;--card:#181c24;--ink:#e6e9f0;--mut:#8b95a8;--line:#262b35;--tag-bg:#262b35;--logo-bg:#262b35;--sb:#13161c;--sb-ink:#a8b1c4;--sb-hover:rgba(255,255,255,.06);--sb-cnt-bg:rgba(255,255,255,.1);--sb-border:rgba(255,255,255,.08);--sb-note:#8b95b6}
@media (prefers-color-scheme: dark){html:not([data-theme="light"]){--bg:#0f1217;--card:#181c24;--ink:#e6e9f0;--mut:#8b95a8;--line:#262b35;--tag-bg:#262b35;--logo-bg:#262b35;--sb:#13161c;--sb-ink:#a8b1c4;--sb-hover:rgba(255,255,255,.06);--sb-cnt-bg:rgba(255,255,255,.1);--sb-border:rgba(255,255,255,.08);--sb-note:#8b95b6}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14.5px/1.55 Plus Jakarta Sans,Inter,system-ui,Segoe UI,Roboto,sans-serif,Segoe UI,Roboto,sans-serif;letter-spacing:-.005em}
/* ---- app shell: sidebar + main, mirroring the Reddit dashboard ---- */
.app{display:flex;min-height:100vh}
.sidebar{width:218px;flex-shrink:0;background:var(--sb);color:var(--sb-ink);position:sticky;top:0;height:100vh;padding:22px 0;overflow:auto;border-right:1px solid var(--sb-border);display:flex;flex-direction:column}
.sbtop{display:flex;align-items:center;gap:8px;padding:0 14px 18px}
.brand{display:flex;align-items:center;gap:10px;color:var(--sb-brand);font-weight:600;font-size:17px;text-decoration:none;flex:1;min-width:0}
.brand .logo{width:30px;height:30px;border-radius:8px;object-fit:contain;background:var(--sb-logo-bg);padding:3px}
.brand .h{font-weight:400}
.sbtoggle{display:flex;align-items:center;justify-content:center;width:34px;height:34px;flex-shrink:0;border:none;border-radius:9px;background:var(--sb-hover);color:var(--sb-ink);cursor:pointer}
.sbtoggle svg{width:19px;height:19px}.sbtoggle:hover{background:var(--sb-cnt-bg);color:var(--sb-active-ink)}
.nav a{display:flex;align-items:center;gap:12px;margin:2px 12px;padding:11px 14px;border-radius:12px;color:var(--sb-ink);text-decoration:none;font-size:14px;font-weight:500;cursor:pointer;transition:background .14s,color .14s}
.nav a svg{width:18px;height:18px;flex-shrink:0;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}
.nav a:hover{background:var(--sb-hover);color:var(--sb-active-ink)}
.nav a.active{background:rgba(99,102,241,.16);color:#fff;font-weight:600}
.nav .cnt{margin-left:auto;background:var(--sb-cnt-bg);border-radius:999px;padding:1px 9px;font-size:11px;font-variant-numeric:tabular-nums}
.nav .cnt.warn{background:var(--bad);color:#fff}
.sbnote{color:var(--sb-note);font-size:11px;padding:18px 22px 0;border-top:1px solid var(--sb-border);margin-top:auto}
.app.sb-collapsed .sidebar{width:64px}
.app.sb-collapsed .brand span,.app.sb-collapsed .nav a .t,.app.sb-collapsed .nav .cnt,.app.sb-collapsed .sbnote{display:none}
.app.sb-collapsed .nav a{justify-content:center;margin:2px 8px;padding:11px 0}
/* ── Gemini-style sidebar header ──────────────────────────────────────────────
   Collapsed shows the logo alone. Hovering the header fades the logo out and the
   toggle in, in its place, so the control only appears when reached for. Expanded
   shows logo + wordmark with the toggle parked on the right. */
.sidebar{transition:width .22s cubic-bezier(.4,0,.2,1)}
.sbtop{position:relative}
.brand,.sbtoggle{transition:opacity .15s ease}
.app.sb-collapsed .sbtop{justify-content:center;padding-left:0;padding-right:0}
.app.sb-collapsed .sbtop .brand{display:flex;opacity:1;flex:0 0 auto;justify-content:center;width:100%;margin:0;padding:0}
.app.sb-collapsed .sbtoggle{position:absolute;left:50%;top:0;transform:translateX(-50%);opacity:0;pointer-events:none}
.app.sb-collapsed .sbtop:hover .brand{opacity:0}
.app.sb-collapsed .sbtop:hover .sbtoggle{opacity:1;pointer-events:auto}
/* the arrow points the way the click will move the panel */
.sbtoggle .i-open{display:none}
.app.sb-collapsed .sbtoggle .i-open{display:block}
.app.sb-collapsed .sbtoggle .i-close{display:none}
/* ── rail tooltips + toggle arrow ─────────────────────────────────────────────
   The panel glyph sits empty at rest; the inner arrow only grows in on hover, and
   points the way the click will move the panel. Tooltips are pills to the right of
   the rail -- only useful while collapsed, since expanded shows the labels. */
.nav a,.sbtoggle{position:relative}
/* The rail tooltip cannot be a pseudo-element: .sidebar needs overflow:auto so it can
   scroll on short viewports, and that clips anything reaching past its right edge.
   It lives on <body> as a fixed-position node instead, placed by script on hover. */
.railtip{position:fixed;left:0;top:0;transform:translateY(-50%) translateX(-5px);
background:#e9eaee;color:#1f2330;font:500 13px Plus Jakarta Sans,Inter,system-ui,sans-serif;
letter-spacing:-.005em;padding:7px 13px;border-radius:10px;white-space:nowrap;opacity:0;
pointer-events:none;transition:opacity .14s ease,transform .14s ease;z-index:400;
box-shadow:0 6px 20px rgba(0,0,0,.30)}
.railtip.on{opacity:1;transform:translateY(-50%) translateX(0)}
.sbtoggle .arr{opacity:0;transition:opacity .13s ease}
.app.sb-collapsed .sbtoggle .arr-close{display:none}
.app:not(.sb-collapsed) .sbtoggle .arr-open{display:none}
.sbtoggle:hover .arr{opacity:1}
.main{flex:1;min-width:0;display:flex;flex-direction:column}
.topbar{display:flex;align-items:center;gap:10px;padding:14px 26px;background:var(--card);border-bottom:1px solid var(--line);flex-wrap:wrap;position:sticky;top:0;z-index:30}
.topbar h2{font:600 17px Plus Jakarta Sans,Inter,system-ui,Segoe UI,Roboto,sans-serif;letter-spacing:-.01em;margin:0}
.topmenu{display:none;align-items:center;justify-content:center;width:36px;height:36px;flex-shrink:0;margin-right:6px;border:1px solid var(--line);border-radius:9px;background:var(--card);color:var(--ink);cursor:pointer}
.topmenu svg{width:19px;height:19px}
.content{padding:22px 26px 70px;max-width:1200px;width:100%}
.view{display:none}.view.on{display:block}
/* ---- period / compare picker, ported from the Reddit dashboard ---- */
/* Cross-platform switch: one icon showing the dashboard you are NOT on. */
.pswap{display:inline-flex;align-items:center;justify-content:center;width:40px;height:40px;border-radius:11px;border:1px solid var(--line);background:var(--card);margin-left:12px;flex-shrink:0;transition:border-color .14s,box-shadow .14s}
.pswap:hover{border-color:var(--accent);box-shadow:0 2px 9px rgba(99,102,241,.20)}
.pswap img{width:26px;height:26px;border-radius:7px;display:block}
.tbctrls{margin-left:auto;display:flex;align-items:center;gap:9px;flex-wrap:wrap}
.tbctrls .sub{color:var(--mut);font-size:12.5px;font-variant-numeric:tabular-nums}
.rangebtn{display:inline-flex;align-items:center;gap:9px;background:rgba(99,102,241,.10);border:1px solid rgba(99,102,241,.32);color:var(--accent);border-radius:7px;padding:6px 11px 6px 10px;font:600 13px Plus Jakarta Sans,Inter,system-ui,Segoe UI,Roboto,sans-serif;cursor:pointer;transition:all 120ms;letter-spacing:-.01em}
.rangebtn:hover{background:rgba(99,102,241,.18);border-color:var(--accent)}
.rangebtn .rb-i{width:14px;height:14px;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}
.rangebtn .rb-c{width:13px;height:13px;opacity:.7;fill:none;stroke:currentColor;stroke-width:2}
.rpop{position:fixed;background:var(--card);border:1px solid var(--line);border-radius:10px;box-shadow:0 16px 50px rgba(20,30,60,.22);padding:6px;min-width:236px;max-height:70vh;overflow:auto;z-index:200;font:400 13px Plus Jakarta Sans,Inter,system-ui,Segoe UI,Roboto,sans-serif}
html[data-theme="dark"] .rpop{box-shadow:0 16px 50px rgba(0,0,0,.6)}
.rpop button{display:flex;align-items:center;justify-content:space-between;gap:14px;width:100%;background:transparent;border:none;color:var(--ink);padding:8px 12px;border-radius:6px;cursor:pointer;font:500 13px Plus Jakarta Sans,Inter,system-ui,Segoe UI,Roboto,sans-serif;text-align:left}
.rpop button:hover{background:var(--tag-bg)}
.rpop button.sel{background:var(--accent);color:#fff}
.rpop button .n{color:var(--mut);font-size:11.5px;font-variant-numeric:tabular-nums}
.rpop button.sel .n{color:rgba(255,255,255,.75)}
.rpop .div{height:1px;background:var(--line);margin:5px 6px}
.rpop .hd{color:var(--mut);font:600 10.5px Plus Jakarta Sans,Inter,system-ui,Segoe UI,Roboto,sans-serif;letter-spacing:.07em;text-transform:uppercase;padding:9px 12px 5px}
.rpop-cal{margin-top:4px;padding:10px 6px 6px;border-top:1px solid var(--line);min-width:0;width:100%}
.rpop-tabs{display:grid;grid-template-columns:1fr 1fr;border:1px solid var(--line);border-radius:8px;overflow:hidden;margin:0 4px 12px}
.rpop-tab{background:transparent;border:none;border-right:1px solid var(--line);color:var(--mut);padding:8px 0;font:600 12.5px Plus Jakarta Sans,Inter,system-ui;cursor:pointer;width:auto;justify-content:center}
.rpop-tab:last-child{border-right:none}
.rpop-tab.active{background:var(--tag-bg);color:var(--accent)}
.rpop-nav{display:flex;justify-content:space-between;align-items:center;margin:0 6px 4px}
.rpop-nav button{background:transparent;border:none;color:var(--mut);width:26px;height:26px;border-radius:6px;cursor:pointer;font-size:17px;line-height:1;padding:0;justify-content:center}
.rpop-nav button:hover{background:var(--tag-bg);color:var(--ink)}
.rpop-months{display:grid;grid-template-columns:1fr 1fr;gap:16px;padding:0 6px}
.rpop-m h4{margin:0 0 8px;text-align:center;font:600 13px Plus Jakarta Sans,Inter,system-ui;color:var(--ink)}
.rpop-grid{display:grid;grid-template-columns:repeat(7,1fr);gap:1px;font-size:12px;text-align:center;font-variant-numeric:tabular-nums}
.rpop-dh{color:var(--mut);font-weight:500;padding:4px 0;font-size:10.5px}
.rpop-d{padding:6px 0;border-radius:6px;cursor:pointer;color:var(--ink);user-select:none}
.rpop-d:hover{background:var(--tag-bg)}
.rpop-d.dis{color:var(--mut);opacity:.32;cursor:not-allowed}
.rpop-d.sel{background:var(--accent);color:#fff}
.rpop-d.inr{background:var(--tag-bg)}
.rpop-actions{display:flex;justify-content:flex-end;padding:10px 6px 2px}
/* ---- calendar: circular date pills ---------------------------------------- */
.rpop-m h4{margin:0 0 12px;text-align:center;font:700 15.5px Plus Jakarta Sans,Inter,system-ui;
letter-spacing:-.01em;color:var(--ink)}
.rpop-grid{display:grid;grid-template-columns:repeat(7,1fr);gap:3px 2px;text-align:center;
font-variant-numeric:tabular-nums}
.rpop-dh{color:var(--mut);font:600 10px Plus Jakarta Sans,Inter,system-ui;letter-spacing:.09em;
text-transform:uppercase;padding:2px 0 8px}
.rpop-d{width:34px;height:34px;line-height:34px;margin:0 auto;padding:0;border-radius:50%;
font:500 13.5px Plus Jakarta Sans,Inter,system-ui;cursor:pointer;user-select:none;
transition:background .13s ease,color .13s ease,transform .13s ease}
.rpop-d:hover{background:var(--tag-bg);transform:scale(1.06)}
.rpop-d.sel{background:var(--accent);color:#fff;font-weight:700;
box-shadow:0 3px 10px rgba(99,102,241,.42)}
.rpop-d.sel:hover{background:var(--accent);transform:scale(1.06)}
.rpop-d.in,.rpop-d.inr{background:rgba(99,102,241,.16);color:var(--ink);border-radius:50%}
.rpop-d.dis{opacity:.28;cursor:not-allowed;background:none;transform:none}
.rpop-d.dis:hover{background:none;transform:none}
.rpop-nav{padding:0 4px 2px}
.rpop-nav button{width:30px;height:30px;border-radius:50%;font-size:18px;line-height:1;
display:flex;align-items:center;justify-content:center;transition:background .13s ease}
.rpop-nav button:hover{background:var(--tag-bg);color:var(--ink)}
.rpop-months{gap:22px}
.rpop-tabs{border-radius:9px}
.rpop-tab{padding:9px 0;font-weight:600}
.rpop-apply{border-radius:9px;padding:9px 22px}
.rpop-apply{background:var(--accent);color:#fff;border:none;border-radius:8px;padding:8px 20px;font:600 13px Plus Jakarta Sans,Inter,system-ui;cursor:pointer;width:auto}
.rpop-apply[disabled]{opacity:.45;cursor:not-allowed}
.sbscrim{position:fixed;inset:0;background:rgba(8,12,24,.5);opacity:0;pointer-events:none;transition:opacity .25s;z-index:99}
@media(max-width:900px){
 .sidebar{position:fixed;left:0;top:0;height:100vh;width:266px;transform:translateX(-100%);transition:transform .25s ease;z-index:100;box-shadow:0 0 40px rgba(0,0,0,.45)}
 .app.sb-open .sidebar{transform:none}
 .app.sb-open .sbscrim{opacity:1;pointer-events:auto}
 .topmenu{display:inline-flex}
 .app.sb-collapsed .sidebar{width:266px}
 .app.sb-collapsed .brand span,.app.sb-collapsed .nav a .t,.app.sb-collapsed .nav .cnt,.app.sb-collapsed .sbnote{display:revert}
 /* The drawer is a full panel, so none of the collapsed-rail geometry should survive
    here. Centring is invisible on badged items (.cnt has margin-left:auto, which
    stretches the row) and only shows on the one item without a badge -- so override
    it explicitly rather than trusting it to look right. */
 .app.sb-collapsed .nav a{justify-content:flex-start;margin:2px 12px;padding:11px 14px}
 .app.sb-collapsed .sbtop{justify-content:flex-start;padding:0 14px 18px}
 .app.sb-collapsed .sbtop .brand{width:auto;justify-content:flex-start;opacity:1}
 .app.sb-collapsed .sbtoggle{position:static;transform:none;opacity:1;pointer-events:auto}
 .content{padding:18px 16px 60px}
 /* On mobile the period/compare controls move into the drawer rather than wrapping
    the top bar into three rows -- same arrangement as the Reddit dashboard. */
 .sbctrls .tbctrls{flex-direction:column;align-items:stretch;gap:9px;padding:12px 14px 4px;
 margin:8px 0 0;border-top:1px solid var(--sb-border)}
 .sbctrls .rangebtn{width:100%;justify-content:flex-start}
 .sbctrls .sub{color:var(--sb-note);font-size:11.5px}
 .sbctrls .theme-toggle{width:100%;justify-content:center}
 .sbctrls .pswap{margin-left:0}
}
h1{font-size:26px;font-weight:600;letter-spacing:-.01em;margin:0}
.meta{color:var(--mut);font-size:13px;margin-bottom:20px}
.pswitch{margin-left:auto;display:inline-flex;border:1px solid var(--line);border-radius:8px;overflow:hidden}
.pswitch a{padding:8px 15px;font:600 13px Plus Jakarta Sans,Inter,system-ui,Segoe UI,Roboto,sans-serif;color:var(--mut);text-decoration:none}
.pswitch a:hover{background:var(--tag-bg);color:var(--ink)}
.pswitch a.on{background:var(--accent);color:#fff}
.theme-toggle{background:transparent;border:1px solid var(--line);color:var(--mut);border-radius:8px;padding:7px;cursor:pointer;display:inline-flex;margin-left:8px}
.theme-toggle svg{width:16px;height:16px}.theme-toggle:hover{color:var(--accent);border-color:var(--accent)}
.grid{display:grid;gap:14px}.g4{grid-template-columns:repeat(4,minmax(0,1fr))}.g2{grid-template-columns:repeat(2,minmax(0,1fr))}
@media(max-width:760px){.g4{grid-template-columns:repeat(2,minmax(0,1fr))}.g2{grid-template-columns:minmax(0,1fr)}}
.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:20px;box-shadow:var(--shadow)}
.card h3{margin:0 0 14px;font:700 15px Plus Jakarta Sans,Inter,system-ui,Segoe UI,Roboto,sans-serif;letter-spacing:-.01em;color:var(--ink)}
/* tinted KPI tiles — same language as the Reddit dashboard */
.kpi{border:none;border-radius:18px;padding:20px 22px;box-shadow:none}
.kpi .kpi-top{display:flex;align-items:flex-start;justify-content:space-between;gap:12px}
.kpi .l{font:700 11px Plus Jakarta Sans,Inter,system-ui,Segoe UI,Roboto,sans-serif;letter-spacing:.075em;text-transform:uppercase;color:var(--kpi-k,#7c85a3);margin:0 0 7px}
.kpi .v{font:700 30px Plus Jakarta Sans,Inter,system-ui,Segoe UI,Roboto,sans-serif;letter-spacing:-.025em;line-height:1.05;color:var(--ink);font-variant-numeric:tabular-nums}
.kpi .kpi-ico{width:44px;height:44px;border-radius:50%;background:var(--kpi-ico-bg,#fff);display:flex;align-items:center;justify-content:center;flex-shrink:0;box-shadow:0 2px 8px rgba(30,35,64,.10)}
.kpi .kpi-ico svg{width:20px;height:20px;stroke:var(--kpi-ico,#6366f1);fill:none;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}
.kpi .kpi-d{margin-top:14px;font-size:12px;color:var(--mut);display:flex;align-items:center;gap:7px;flex-wrap:wrap}
.kpi .kpi-d .delta{margin:0;font-size:12.5px}
.kpi.t-blue{background:#eaeeff;--kpi-ico:#6366f1;--kpi-k:#5b6394}
.kpi.t-violet{background:#f2ecfe;--kpi-ico:#8b5cf6;--kpi-k:#6c5b96}
.kpi.t-green{background:#e3f7f1;--kpi-ico:#10b981;--kpi-k:#4a7566}
.kpi.t-amber{background:#fff4e3;--kpi-ico:#f59e0b;--kpi-k:#8a6a3d}
html[data-theme="dark"] .kpi.t-blue{background:#171f33;--kpi-ico-bg:#0f1420;--kpi-k:#7f8bb0}
html[data-theme="dark"] .kpi.t-violet{background:#1e1a33;--kpi-ico-bg:#0f1420;--kpi-k:#8d80b8}
html[data-theme="dark"] .kpi.t-green{background:#13241f;--kpi-ico-bg:#0f1420;--kpi-k:#6f9c8b}
html[data-theme="dark"] .kpi.t-amber{background:#241d13;--kpi-ico-bg:#0f1420;--kpi-k:#a98d63}
@media(prefers-color-scheme:dark){html:not([data-theme="light"]) .kpi.t-blue{background:#171f33;--kpi-ico-bg:#0f1420;--kpi-k:#7f8bb0}
html:not([data-theme="light"]) .kpi.t-violet{background:#1e1a33;--kpi-ico-bg:#0f1420;--kpi-k:#8d80b8}
html:not([data-theme="light"]) .kpi.t-green{background:#13241f;--kpi-ico-bg:#0f1420;--kpi-k:#6f9c8b}
html:not([data-theme="light"]) .kpi.t-amber{background:#241d13;--kpi-ico-bg:#0f1420;--kpi-k:#a98d63}}
.delta{font-size:12px;font-weight:600;margin-left:7px}.up{color:var(--good)}.down{color:var(--bad)}
.delta.flat{color:var(--mut);font-weight:500;cursor:help}
.hbar{display:flex;align-items:center;gap:10px;margin:7px 0;font-size:13px}
.hbar .nm{width:150px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.hbar .bar{flex:1;height:8px;border-radius:4px;background:var(--tag-bg);overflow:hidden}
.hbar .bar span{display:block;height:100%;background:var(--accent);border-radius:4px}
.hbar .n{width:56px;text-align:right;font-variant-numeric:tabular-nums;color:var(--mut)}
.heat{display:flex;flex-direction:column;gap:3px}.hrow{display:flex;align-items:center;gap:3px}
.hlab{width:32px;font-size:10px;color:var(--mut)}.hcell{flex:1;min-width:7px;height:14px;border-radius:2px}
/* GitHub-style hover capsule, matching the Reddit dashboard's #tip */
#tip{position:absolute;display:none;z-index:60;background:#1f242e;color:#f1f3f7;border:1px solid rgba(255,255,255,.08);border-radius:7px;padding:7px 11px;font:500 12px Plus Jakarta Sans,Inter,system-ui,Segoe UI,Roboto,sans-serif;pointer-events:none;box-shadow:0 6px 22px rgba(0,0,0,.35);max-width:280px;white-space:nowrap}
#tip::before{content:"";position:absolute;top:-5px;left:14px;width:9px;height:9px;background:#1f242e;border-top:1px solid rgba(255,255,255,.08);border-left:1px solid rgba(255,255,255,.08);transform:rotate(45deg)}
[data-tt]{cursor:default}
.hcell[data-tt]:hover{outline:1.5px solid var(--accent);outline-offset:-1px}
.hbar[data-tt]:hover .bar{filter:brightness(1.12)}
.dpt{cursor:default}
.donut circle[data-tt]:hover{filter:brightness(1.15)}
.donut{display:flex;align-items:center;gap:18px}.donut svg{flex-shrink:0}
/* Charts draw themselves in when scrolled into view, matching the Reddit page: the
   stroke unrolls via dashoffset while the fill fades up. */
@keyframes cdraw{from{stroke-dashoffset:1}to{stroke-dashoffset:0}}
@keyframes cfillin{from{opacity:0}to{opacity:1}}
.cdraw{stroke-dasharray:1;stroke-dashoffset:1}
.cfill{opacity:0}
.chart-in .cdraw{animation:cdraw 1.15s cubic-bezier(.45,.05,.2,1) forwards}
.chart-in .cfill{animation:cfillin 1.2s ease forwards}
@media (prefers-reduced-motion: reduce){.cdraw{stroke-dasharray:none;stroke-dashoffset:0}
.cfill{opacity:1}.chart-in .cdraw,.chart-in .cfill{animation:none}}
@media print{.cdraw{stroke-dashoffset:0!important}.cfill{opacity:1!important}}
.lcol{font-size:13px}.lcol .lg{margin:6px 0;display:flex;align-items:center;gap:7px}
.lcol .lgn{color:var(--mut);font-variant-numeric:tabular-nums}
.lcol .dot{width:9px;height:9px;border-radius:50%;display:inline-block;flex-shrink:0}
.sbar{display:flex;height:12px;border-radius:6px;overflow:hidden;background:var(--tag-bg);margin:6px 0 10px}
.msg{padding:11px 0;border-bottom:1px solid var(--line);font-size:13.5px}.msg:last-child{border:none}
.msg .mh{color:var(--mut);font-size:12px;margin-bottom:3px}.msg .mh b{color:var(--ink)}
.chip{display:inline-block;background:var(--tag-bg);border-radius:999px;padding:2px 9px;font-size:11px;color:var(--mut);margin-left:8px}
.sec{font:600 19px Plus Jakarta Sans,Inter,system-ui,Segoe UI,Roboto,sans-serif;letter-spacing:-.01em;margin:34px 0 14px;padding-top:20px;border-top:1px solid var(--line)}
.sec .sub{display:block;font:400 13px Plus Jakarta Sans,Inter,system-ui,Segoe UI,Roboto,sans-serif;color:var(--mut);margin-top:3px;letter-spacing:0}
.lb{width:100%;border-collapse:collapse;font-size:13.5px}
.lb th{text-align:left;color:var(--mut);font:600 11px Plus Jakarta Sans,Inter,system-ui,Segoe UI,Roboto,sans-serif;letter-spacing:.06em;text-transform:uppercase;padding:0 0 9px;border-bottom:1px solid var(--line)}
.lb td{padding:9px 0;border-bottom:1px solid var(--line);font-variant-numeric:tabular-nums}
.lb td:first-child{font-weight:600}.lb tr:last-child td{border:none}
.lb th:not(:first-child),.lb td:not(:first-child){text-align:right;width:112px}
.note{background:var(--tag-bg);border-radius:10px;padding:11px 13px;margin-top:12px;font-size:12.5px;color:var(--mut)}
.setup li{margin:8px 0}
.foot{color:var(--mut);font-size:12px;margin-top:34px;border-top:1px solid var(--line);padding-top:16px}
a{color:var(--blue);text-decoration:none}a:hover{text-decoration:underline}
"""

# Everything here is delegated off `document` rather than bound to elements, because
# the password gate injects the whole app via innerHTML -- scripts inside that blob
# never execute, and elements bound at DOMContentLoaded would not exist yet.
THEME_JS = """
<script>(function(){
var K='hintel-theme';
function theme(v){if(v==='dark'||v==='light')document.documentElement.setAttribute('data-theme',v);else document.documentElement.removeAttribute('data-theme');}
theme(localStorage.getItem(K)||'dark');
function app(){return document.querySelector('.app');}
/* Navigation only records which view is wanted; render() below owns the DOM, so the
   selected period and the selected tab always resolve through one code path. */
function show(v){
  var links=document.querySelectorAll('#nav a');if(!links.length)return false;
  var known=false;links.forEach(function(a){if(a.getAttribute('data-v')===v)known=true;});
  if(!known)v=links[0].getAttribute('data-v');
  try{history.replaceState(null,'','#'+v);}catch(_){}
  links.forEach(function(a){a.classList.toggle('active',a.getAttribute('data-v')===v);});
  render();
  return true;
}
document.addEventListener('click',function(e){
  if(!e.target.closest)return;
  var a=e.target.closest('#nav a');
  if(a){e.preventDefault();show(a.getAttribute('data-v'));var p=app();if(p)p.classList.remove('sb-open');return;}
  if(e.target.closest('#sbToggle')){var p1=app();if(!p1)return;
    if(mqSmall.matches){p1.classList.toggle('sb-open');return;}   /* drawer: close it */
    p1.classList.toggle('sb-collapsed');
    try{localStorage.setItem('hintel-sb',p1.classList.contains('sb-collapsed')?'1':'0');}catch(_){}return;}
  if(e.target.closest('#mOpen')){var p2=app();if(p2)p2.classList.add('sb-open');return;}
  if(e.target.closest('#sbScrim')){var p3=app();if(p3)p3.classList.remove('sb-open');return;}
  if(e.target.closest('#themeBtn')){var c=localStorage.getItem(K)||'dark';var n=c==='auto'?'dark':(c==='dark'?'light':'auto');localStorage.setItem(K,n);theme(n);return;}
});
window.addEventListener('hashchange',function(){show(location.hash.slice(1));});
function boot(){return show(location.hash.slice(1)||'dashboard');}
document.addEventListener('DOMContentLoaded',function(){
  if(boot())return;
  var mo=new MutationObserver(function(){if(boot())mo.disconnect();});
  mo.observe(document.body,{childList:true,subtree:true});
});
window.addEventListener('storage',function(e){if(e.key===K)theme(e.newValue||'dark');});
(function(){var n=null;function node(){if(!n){n=document.createElement('div');n.className='railtip';document.body.appendChild(n);}return n;}function hide(){if(n)n.classList.remove('on');}document.addEventListener('mouseover',function(e){if(!e.target.closest)return;var a=e.target.closest('#nav a,#sbToggle');if(!a){hide();return;}var sbEl=document.querySelector('.sidebar');if(sbEl&&getComputedStyle(sbEl).position==='fixed'){hide();return;}var app=document.querySelector('.app'),col=app&&app.classList.contains('sb-collapsed'),txt='';if(a.id==='sbToggle'){txt=col?'Open sidebar':'Close sidebar';}else{if(!col){hide();return;}var t=a.querySelector('.t');txt=t?t.textContent.trim():'';}if(!txt){hide();return;}var b=a.getBoundingClientRect(),el=node();el.textContent=txt;var sb=document.querySelector('.sidebar'),edge=sb?sb.getBoundingClientRect().right:b.right;el.style.left=(Math.max(b.right,edge)+12)+'px';el.style.top=(b.top+b.height/2)+'px';el.classList.add('on');});document.addEventListener('mouseout',function(e){if(e.target.closest&&e.target.closest('#nav a,#sbToggle'))hide();});window.addEventListener('scroll',hide,true);window.addEventListener('resize',hide);})();

/* ================= data-driven render layer (mirrors the Reddit dashboard) =========
   Every view below is a direct port of its Python renderer, so switching period
   re-renders client-side instead of needing a rebuild. DATA is read from the inert
   JSON block that ships inside the encrypted region. */
var ICO=__ICONS__;
var DATA=null, periodSel=null, compareSel={kind:'none'}, booted=false;
var TITLES={dashboard:'Dashboard',answers:'Answer Desk',helpers:'Helpers',coverage:'Coverage',attention:'Needs Attention',safety:'Safety',newcomers:'Newcomers',channels:'Channels'};
var PROX=30;
function esc(s){return String(s==null?'':s).replace(/[&<>"]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});}
function num(n){return (n==null?0:n).toLocaleString('en-US');}

/* ---- custom date range: rebuild a scope from the atoms ---------------------
   Returns the same shape scopeOf() gives for a preset, so render() and every view
   work unchanged. The equal-length window before the range is aggregated too, so
   the significance-tested deltas still have a baseline. */
function dstr(d){return d.toISOString().slice(0,10);}
function addDays(ds,n){var d=new Date(ds+'T12:00:00');d.setDate(d.getDate()+n);return dstr(d);}
function daysBetween(a,b){return Math.round((new Date(b+'T12:00:00')-new Date(a+'T12:00:00'))/864e5)+1;}
function inR(ds,a,b){return ds>=a&&ds<=b;}
function med(v){return v.length?(v.length%2?v[(v.length-1)/2]:(v[v.length/2-1]+v[v.length/2])/2):null;}

function rangeSlice(A,a,b){
  var out={messages:0,reactions:0,pos:0,neg:0,joins:0,members:{},contrib:{},chan:{},heat:[],daily:[]},i,k;
  for(i=0;i<7;i++)out.heat.push([0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]);
  for(var ds in A.daily){ if(!inR(ds,a,b))continue; var d=A.daily[ds];
    out.messages+=d.m; out.reactions+=d.r; out.pos+=d.p; out.neg+=d.n; out.joins+=(d.j||0);
    (d.a||[]).forEach(function(x){out.members[x]=1;});
    for(k in (d.u||{}))out.contrib[k]=(out.contrib[k]||0)+d.u[k];
    for(k in (d.c||{}))out.chan[k]=(out.chan[k]||0)+d.c[k];
    var wd=(new Date(ds+'T12:00:00').getDay()+6)%7;
    for(i=0;i<24;i++)out.heat[wd][i]+=(d.h?d.h[i]:0);
    out.daily.push([ds,d.m]); }
  out.daily.sort(function(x,y){return x[0]<y[0]?-1:1;});
  return out;
}

function computeRange(a,b){
  var A=DATA.atoms; if(!A)return null;
  var nd=daysBetween(a,b), pa=addDays(a,-nd), pb=addDays(a,-1);
  var cur=rangeSlice(A,a,b), prv=rangeSlice(A,pa,pb);
  var nm=function(i){return A.authors[i]||('#'+i);};
  var ch=function(i){return A.channels[i]||('#'+i);};
  var pairs=function(o,f){return Object.keys(o).map(function(k){return [f(+k),o[k]];})
    .sort(function(x,y){return y[1]-x[1];});};

  var q=A.q.filter(function(r){return inR(r[0],a,b);});
  var pq=A.q.filter(function(r){return inR(r[0],pa,pb);});
  var prompt=function(rs){return rs.filter(function(r){return r[4]>=0&&r[4]<=PROX;}).length;};
  var everR=function(rs){return rs.filter(function(r){return r[5]===1;});};
  var openQ=function(rs){return rs.filter(function(r){return r[5]!==1&&r[7]!==1;});};
  var queue=openQ(q).sort(function(x,y){return x[0]<y[0]?1:-1;});
  var waits=everR(q).map(function(r){return r[4];}).filter(function(w){return w>=0;}).sort(function(x,y){return x-y;});

  function cover(bucket){var m={},r=[],k;
    everR(q).forEach(function(x){if(x[4]<0)return;var kk=bucket(x[1]);(m[kk]=m[kk]||[]).push(x[4]);});
    for(k in m){var v=m[k].sort(function(p,s){return p-s;}); if(v.length>=5)r.push([+k,med(v),v.length]);}
    return r.sort(function(p,s){return p[0]-s[0];});}
  var cov=cover(function(h){return h;}), gran='hour';
  if(cov.length<4){var cb=cover(function(h){return Math.floor(h/4)*4;});
    if(cb.length>=2){cov=cb;gran='block';}else{cov=[];gran='none';}}

  var rw=A.rep.filter(function(r){return inR(r[0],a,b);});
  var prw=A.rep.filter(function(r){return inR(r[0],pa,pb);});
  var hm={};
  rw.forEach(function(r){var h=hm[r[1]]=hm[r[1]]||{n:0,who:{},lat:[]};h.n++;h.who[r[2]]=1;h.lat.push(r[3]);});
  var helpers=Object.keys(hm).map(function(i){var h=hm[i];var L=h.lat.sort(function(x,y){return x-y;});
    return {name:nm(+i),answers:h.n,helped:Object.keys(h.who).length,median:med(L)||0};})
    .sort(function(x,y){return y.answers-x.answers;});
  var phc={};prw.forEach(function(r){phc[r[1]]=1;});

  var arrived=[],k2;
  for(k2 in A.first)if(inR(A.first[k2],a,b))arrived.push(k2);
  var ret=arrived.filter(function(i){return (A.count[i]||0)>=2;});
  var reg=arrived.filter(function(i){return (A.count[i]||0)>=5;});
  var gaps=arrived.filter(function(i){return A.second[i];}).map(function(i){
    return (new Date(A.second[i]+'T12:00:00')-new Date(A.first[i]+'T12:00:00'))/36e5;})
    .sort(function(x,y){return x-y;});
  var introSet={};A.intro.forEach(function(i){introSet[i]=1;});
  var elseSet={};A.elsewhere.forEach(function(i){elseSet[i]=1;});
  var introIn=arrived.filter(function(i){return introSet[i];});

  var sfr=A.sf.filter(function(r){return inR(r[0],a,b);});
  var kwr=A.kw.filter(function(r){return inR(r[0],a,b);});
  var kwc={};kwr.forEach(function(r){kwc[r[1]]=(kwc[r[1]]||0)+1;});
  var rp={};sfr.forEach(function(r){rp[r[1]]=(rp[r[1]]||0)+1;});
  var negr=A.neg.filter(function(r){return inR(r[0],a,b);}).sort(function(x,y){return x[3]-y[3];});

  var chRows=pairs(cur.chan,ch), total=cur.messages||1;
  var uniq=Object.keys(cur.members).length, puniq=Object.keys(prv.members).length;

  return {custom:true,start:a,end:b,days:nd,label:a+' – '+b,
    messages:cur.messages,prev_messages:prv.messages,per_day:+(cur.messages/nd).toFixed(1),
    members:uniq,prev_members:puniq,new_members:cur.joins,prev_new_members:prv.joins,
    reactions:cur.reactions,prev_reactions:prv.reactions,
    pos:cur.pos,neg:cur.neg,neu:cur.messages-cur.pos-cur.neg,
    daily:cur.daily,
    channels:chRows.slice(0,10).map(function(r){return ['#'+r[0],r[1]];}),
    contributors:pairs(cur.contrib,nm).slice(0,10),
    heat:cur.heat,
    heat_max:Math.max.apply(null,cur.heat.map(function(r){return Math.max.apply(null,r);})),
    negatives:negr.slice(0,12).map(function(r){return {author:nm(r[1]),channel:ch(r[2]),when:r[5],text:A.texts[r[4]]};}),
    questions:q.length,prev_questions:pq.length,
    answered:prompt(q),prev_answered:prompt(pq),
    unanswered:queue.length,prev_unanswered:openQ(pq).length,
    median_wait:med(waits),
    answers_given:rw.length,prev_answers_given:prw.length,
    helper_count:helpers.length,prev_helper_count:Object.keys(phc).length,
    queue:queue.slice(0,15).map(function(r){return {author:nm(r[2]),channel:ch(r[3]),when:r[0],text:A.texts[r[6]]};}),
    queue_total:queue.length,helpers:helpers.slice(0,15),cover:cov,cover_gran:gran,
    sf_reports:sfr.length,sf_reporters:Object.keys(rp).length,sf_mentions:kwr.length,
    sf_mention_channels:pairs(kwc,ch).slice(0,8).map(function(r){return ['#'+r[0],r[1]];}),
    sf_recent:sfr.slice(-12).reverse().map(function(r){return {author:nm(r[1]),channel:ch(r[2]),when:r[4],text:A.texts[r[3]]};}),
    sf_top_reporters:pairs(rp,nm).slice(0,8),
    nc_arrived:arrived.length,nc_retained:ret.length,nc_regulars:reg.length,
    nc_oneshot:arrived.length-ret.length,nc_median_return_h:med(gaps),
    nc_intro:introIn.length,nc_intro_converted:introIn.filter(function(i){return elseSet[i];}).length,
    ch_rows:chRows.slice(0,20).map(function(r){return [r[0],r[1],0,+(100*r[1]/total).toFixed(1)];}),
    ch_total:chRows.length,
    ch_active:chRows.filter(function(r){return r[1]>=50;}).length,
    ch_quiet:chRows.filter(function(r){return r[1]>0&&r[1]<50;}).length,
    ch_top3_share:+(100*chRows.slice(0,3).reduce(function(t,r){return t+r[1];},0)/total).toFixed(1)};
}

function scopeOf(sel){if(!sel||sel.kind==='none'||!DATA)return null;
  if(sel.kind==='preset')return DATA.presets[sel.idx];
  if(sel.kind==='custom')return computeRange(sel.start,sel.end);return null;}
function selLabel(sel){if(!sel||sel.kind==='none')return 'Compare';
  if(sel.kind==='custom')return sel.start+' \u2013 '+sel.end;
  return DATA.presets[sel.idx].label;}
function selHint(sel){var s=scopeOf(sel);return s?s.start+' \\u2192 '+s.end:'';}

/* significance gate -- identical arithmetic to the Python side */
/* Windows being compared need not be the same length -- you can hold a 28-day period
   against a 12-week one. Comparing raw counts there would report the length difference
   as a collapse in activity. So this is a Poisson rate test with exposure: under equal
   rates cur ~ Binomial(cur+prev, t1/(t1+t2)), and the figure shown is the ratio of
   per-day rates. With t1 == t2 it reduces exactly to (cur-prev)/sqrt(cur+prev). */
function sigDelta(cur,prev,goodUp,t1,t2){goodUp=(goodUp!==false);
  t1=t1||1;t2=t2||t1;
  if(cur==null||prev==null||cur+prev===0)return '';
  var n=cur+prev,p0=t1/(t1+t2),sd=Math.sqrt(n*p0*(1-p0));
  if(!sd)return '';
  var z=(cur-n*p0)/sd;
  if(Math.abs(z)<1.96)return '<span class="delta flat" title="Change is within the noise floor for this sample size \\u2014 not a real move">\\u2248 flat</span>';
  if(!prev)return '<span class="delta up" title="No activity in the compared window">new</span>';
  var pct=((cur/t1)/(prev/t2)-1)*100,up=pct>=0,cls=goodUp?(up?'up':'down'):(up?'down':'up');
  var t=t1===t2?'z='+z.toFixed(1)+' \\u2014 clears the noise floor'
               :'z='+z.toFixed(1)+' \\u2014 per-day rate, windows are '+t1+'d vs '+t2+'d';
  return '<span class="delta '+cls+'" title="'+t+'">'+(up?'\\u25b2':'\\u25bc')+' '+Math.abs(pct).toFixed(0)+'%</span>';}
function sigRate(x1,n1,x2,n2,goodUp){goodUp=(goodUp!==false);
  if(!n1||!n2)return '';
  var p1=x1/n1,p2=x2/n2,p=(x1+x2)/(n1+n2),se=Math.sqrt(p*(1-p)*(1/n1+1/n2));
  if(!se)return '';var z=(p1-p2)/se;
  if(Math.abs(z)<1.96)return '<span class="delta flat" title="Change is within the noise floor for this sample size \\u2014 not a real move">\\u2248 flat</span>';
  var pts=(p1-p2)*100,up=pts>=0,cls=goodUp?(up?'up':'down'):(up?'down':'up');
  return '<span class="delta '+cls+'" title="z='+z.toFixed(1)+' \\u2014 clears the noise floor">'+(up?'\\u25b2':'\\u25bc')+' '+Math.abs(pts).toFixed(0)+' pts</span>';}
/* baseline: the compared scope when comparing, else the built-in previous window */
function base(p,q,cmp,key){return cmp?(q?q[key]:null):p['prev_'+key];}
function bdays(p,q,cmp){return cmp&&q?q.days:p.days;}
/* Distinct counts (unique members, unique helpers) do not scale linearly with window
   length -- the same people reappear, so a 12-week window does not hold three times
   the uniques of a 4-week one. Rate-normalising them across unequal windows would be
   unsound, so the delta is withheld instead of guessed. A small mismatch is fine --
   semi-monthly cohorts are 15 or 16 days -- so allow 15%. */
function sigUnique(cur,prev,goodUp,t1,t2){
  if(Math.abs(t1-t2)/Math.max(t1,t2)>0.15)
    return '<span class="delta flat" title="Windows are different lengths ('+t1+'d vs '+t2+'d). Unique-people counts do not scale with duration, so this comparison is not meaningful.">not comparable</span>';
  return sigDelta(cur,prev,goodUp,t1,t1);}

function dkpi(label,value,d,tint,icon){
  var sub=d?(d+'<span>'+(compareSel.kind==='none'?'vs previous window':'vs '+esc(selLabel(compareSel)))+'</span>'):'';
  return '<div class="kpi t-'+tint+'"><div class="kpi-top"><div><div class="l">'+label+'</div>'+
    '<div class="v">'+value+'</div></div><span class="kpi-ico"><svg viewBox="0 0 24 24">'+(ICO[icon]||ICO.msg)+'</svg></span></div>'+
    '<div class="kpi-d">'+sub+'</div></div>';}

function areaSvg(daily){
  if(!daily||!daily.length)return '<div class="meta">No data.</div>';
  var W=1000,H=150,pad=8,mx=0,i;
  for(i=0;i<daily.length;i++)mx=Math.max(mx,daily[i][1]);mx=mx||1;
  var X=function(i){return pad+i*((W-2*pad)/Math.max(daily.length-1,1));},
      Y=function(v){return H-24-(v/mx)*(H-42);},pts=[];
  for(i=0;i<daily.length;i++)pts.push(X(i).toFixed(1)+','+Y(daily[i][1]).toFixed(1));
  var line=pts.join(' '),fill=X(0).toFixed(1)+','+(H-24)+' '+line+' '+X(daily.length-1).toFixed(1)+','+(H-24);
  var step=Math.max(1,Math.floor(daily.length/8)),labs='';
  for(i=0;i<daily.length;i++)if(i%step===0)labs+='<text x="'+X(i).toFixed(0)+'" y="'+(H-6)+'" text-anchor="middle" style="fill:var(--mut);font-size:10px">'+esc(daily[i][0].slice(5))+'</text>';
  /* Each day owns a transparent vertical strip so the cursor never has to land on
     the 2px line itself -- same trick the Reddit charts use. */
  var bandW=(W-2*pad)/Math.max(daily.length-1,1),bands='';
  for(i=0;i<daily.length;i++){var bx=X(i)-bandW/2;
    bands+='<rect x="'+Math.max(0,bx).toFixed(1)+'" y="0" width="'+bandW.toFixed(1)+'" height="'+(H-20)+'" fill="transparent" '+
      'data-tt="'+esc(num(daily[i][1])+' messages on '+daily[i][0])+'"/>';
    bands+='<circle class="dpt" cx="'+X(i).toFixed(1)+'" cy="'+Y(daily[i][1]).toFixed(1)+'" r="3" fill="#6366f1" opacity="0" '+
      'data-tt="'+esc(num(daily[i][1])+' messages on '+daily[i][0])+'"><set attributeName="opacity" to="1" begin="mouseover" end="mouseout"/></circle>';}
  return '<svg viewBox="0 0 '+W+' '+H+'" width="100%"><defs><linearGradient id="dg" x1="0" x2="0" y1="0" y2="1">'+
    '<stop offset="0" stop-color="#6366f1" stop-opacity=".28"/><stop offset="1" stop-color="#6366f1" stop-opacity="0"/></linearGradient></defs>'+
    '<polygon class="cfill" points="'+fill+'" fill="url(#dg)"/>'+'<polyline class="cdraw" pathLength="1" points="'+line+'" fill="none" stroke="#6366f1" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>'+labs+bands+'</svg>';}

function hbars(pairs){
  if(!pairs||!pairs.length)return '<div class="meta">No data.</div>';
  var mx=0,i;for(i=0;i<pairs.length;i++)mx=Math.max(mx,pairs[i][1]);mx=mx||1;
  var h='',tot=0;for(i=0;i<pairs.length;i++)tot+=pairs[i][1];
  for(i=0;i<pairs.length;i++){var sh=tot?(pairs[i][1]/tot*100).toFixed(0):0;
    h+='<div class="hbar" data-tt="'+esc(pairs[i][0]+' · '+num(pairs[i][1])+' messages · '+sh+'% of shown')+'">'+
      '<span class="nm">'+esc(pairs[i][0])+'</span>'+
      '<span class="bar"><span style="width:'+(pairs[i][1]/mx*100).toFixed(1)+'%"></span></span><span class="n">'+num(pairs[i][1])+'</span></div>';}
  return h;}

/* Donut, ported from the Reddit dashboard so both pages read the same. The track uses
   var(--tag-bg) rather than Reddit's hard-coded #eef2fb, which would glow in dark mode. */
function donut(title,segs,centerVal,centerSub){
  var total=0,i;for(i=0;i<segs.length;i++)total+=segs[i].value;total=total||1;
  var R=40,C=2*Math.PI*R,off=0,rings='',leg='';
  for(i=0;i<segs.length;i++){var s=segs[i];if(s.value<=0)continue;
    var len=s.value/total*C;
    rings+='<circle r="'+R+'" cx="60" cy="60" fill="none" stroke="'+s.color+'" stroke-width="15" stroke-dasharray="'+
      len.toFixed(2)+' '+(C-len).toFixed(2)+'" stroke-dashoffset="'+(-off).toFixed(2)+'" transform="rotate(-90 60 60)" '+
      'data-tt="'+esc(s.label+' · '+num(s.value)+' ('+Math.round(s.value/total*100)+'%)')+'"/>';
    off+=len;}
  for(i=0;i<segs.length;i++)leg+='<div class="lg"><span class="dot" style="background:'+segs[i].color+'"></span>'+
    esc(segs[i].label)+' <b>'+Math.round(segs[i].value/total*100)+'%</b>'+
    ' <span class="lgn">('+num(segs[i].value)+')</span></div>';
  return '<div class="card"><h3>'+esc(title)+'</h3><div class="donut">'+
    '<svg viewBox="0 0 120 120" width="106" height="106"><circle r="'+R+'" cx="60" cy="60" fill="none" stroke="var(--tag-bg)" stroke-width="15"/>'+rings+
    '<text x="60" y="57" text-anchor="middle" style="fill:var(--ink);font-size:21px;font-weight:700">'+num(centerVal)+'</text>'+
    '<text x="60" y="73" text-anchor="middle" style="fill:var(--mut);font-size:9px">'+esc(centerSub||'total')+'</text></svg>'+
    '<div class="lcol">'+leg+'</div></div></div>';}

function heatmap(hm,mx){
  var days=['Mon','Tue','Wed','Thu','Fri','Sat','Sun'],out='<div class="heat">',d,c,a,bg;
  for(d=0;d<7;d++){out+='<div class="hrow"><span class="hlab">'+days[d]+'</span>';
    for(c=0;c<24;c++){a=mx?(hm[d][c]/mx):0;
      bg=a?'rgba(99,102,241,'+(0.15+a*0.85).toFixed(2)+')':'var(--tag-bg)';
      out+='<span class="hcell" style="background:'+bg+'" data-tt="'+
        esc(num(hm[d][c])+' messages · '+days[d]+' '+pad2(c)+':00 UTC')+'"></span>';}
    out+='</div>';}
  return out+'</div><div class="meta" style="font-size:11px;margin-top:7px">Messages by day-of-week \\u00d7 hour (UTC) \\u00b7 darker = busier</div>';}

function viewOverview(p,q,cmp){
  var n=p.messages,pos=p.pos,neg=p.neg,neu=p.neu;
  var pp=n?pos/n*100:0,np=n?neg/n*100:0,up=100-pp-np;
  var h='<div class="meta">Window: <b>'+p.start+' \\u2192 '+p.end+'</b> ('+p.days+' days) \\u00b7 community channels, humans only (bot-logs &amp; mod-internal channels excluded)</div>';
  h+='<div class="grid g4">';
  h+=dkpi('Messages \\u00b7 '+Math.round(p.per_day)+'/day',num(n),sigDelta(n,base(p,q,cmp,'messages'),true,p.days,bdays(p,q,cmp)),'blue','msg');
  h+=dkpi('Active members',num(p.members),sigUnique(p.members,base(p,q,cmp,'members'),true,p.days,bdays(p,q,cmp)),'violet','people');
  /* Joins and leaves are separable only when the log embeds were captured. Before
     that they are one indistinguishable stream, so report the combined churn
     rather than passing it off as growth. */
  if(p.split_ok){
    h+=dkpi('Members joined',num(p.joined),sigDelta(p.joined,base(p,q,cmp,'joined'),true,p.days,bdays(p,q,cmp)),'green','join');
  }else{
    h+=dkpi('Join/leave events',num(p.new_members),sigDelta(p.new_members,base(p,q,cmp,'new_members'),true,p.days,bdays(p,q,cmp)),'green','join');
  }
  h+=dkpi('Reactions given',num(p.reactions),sigDelta(p.reactions,base(p,q,cmp,'reactions'),true,p.days,bdays(p,q,cmp)),'amber','react');
  h+='</div>';
  if(p.split_ok){h+='<div class="grid g4" style="margin-top:14px">'
    +dkpi('Members left',num(p.left),sigDelta(p.left,base(p,q,cmp,'left'),false,p.days,bdays(p,q,cmp)),'amber','alert')
    +dkpi('Net change',(p.joined-p.left>=0?'+':'')+num(p.joined-p.left),'','violet','people')
    +'</div>';}
  h+='<div class="card" style="margin-top:14px"><h3>Daily activity</h3>'+areaSvg(p.daily)+'</div>';
  h+='<div class="grid g2" style="margin-top:14px"><div class="card"><h3>Busiest channels</h3>'+hbars(p.channels)+'</div>'+
     '<div class="card"><h3>Top contributors</h3>'+hbars(p.contributors)+'</div></div>';
  h+='<div class="grid g2" style="margin-top:14px"><div class="card"><h3>Activity heatmap</h3>'+heatmap(p.heat,p.heat_max)+'</div>';
  h+=donut('Sentiment',[{label:'Positive',value:pos,color:'#10b981'},
                        {label:'Neutral',value:neu,color:'#cbd5e1'},
                        {label:'Negative',value:neg,color:'#f43f5e'}],n,'messages');
  h+='</div>';
  return h;}

function viewAnswers(p,q,cmp){
  var pct=p.questions?p.answered/p.questions*100:0;
  var bq=base(p,q,cmp,'questions'),ba=base(p,q,cmp,'answered'),bu=base(p,q,cmp,'unanswered');
  var h='<div class="meta">Questions the community asked, and whether anyone actually answered them.</div><div class="grid g4">';
  h+=dkpi('Questions asked',num(p.questions),sigDelta(p.questions,bq,true,p.days,bdays(p,q,cmp)),'blue','ask');
  h+=dkpi('Answered in '+PROX+' min',pct.toFixed(0)+'%',sigRate(p.answered,p.questions,ba,bq),'green','check');
  h+=dkpi('Never answered',num(p.unanswered),sigDelta(p.unanswered,bu,false,p.days,bdays(p,q,cmp)),'amber','alert');
  h+=dkpi('Median first reply',p.median_wait==null?'\\u2014':Math.round(p.median_wait)+' min','','violet','clock');
  h+='</div><div class="card" style="margin-top:14px"><h3>Never answered \\u2014 no reply in 24 hours</h3>';
  if(p.queue&&p.queue.length){
    for(var i=0;i<p.queue.length;i++){var m=p.queue[i];
      h+='<div class="msg"><div class="mh"><b>'+esc(m.author)+'</b> in #'+esc(m.channel)+'<span class="chip">'+esc(m.when)+'</span></div>'+esc(m.text)+'</div>';}
    if(p.queue_total>p.queue.length)h+='<div class="meta" style="margin-top:10px">+ '+num(p.queue_total-p.queue.length)+' more unanswered.</div>';
  }else h+='<div class="meta">Every question in this window got a response.</div>';
  h+='<div class="note">An answer means a threaded reply or an @-mention of the asker. A plain inline reply with neither is not detectable, so treat this as a review list rather than a verdict.</div></div>';
  return h;}

function viewHelpers(p,q,cmp){
  var hl=p.helpers||[],h='<div class="meta">Who carries the answering load \\u2014 read straight off the reply graph, no roles data needed.</div>';
  if(!hl.length)return h+'<div class="card"><div class="meta">No replies in this window.</div></div>';
  var total=p.answers_given,share=total?hl[0].answers/total*100:0,reg=0,i;
  for(i=0;i<hl.length;i++)if(hl[i].answers>=10)reg++;
  h+='<div class="grid g4">';
  h+=dkpi('Answers given',num(total),sigDelta(total,base(p,q,cmp,'answers_given'),true,p.days,bdays(p,q,cmp)),'blue','msg');
  h+=dkpi('People answering',num(p.helper_count),sigUnique(p.helper_count,base(p,q,cmp,'helper_count'),true,p.days,bdays(p,q,cmp)),'violet','people');
  h+=dkpi('Carried by '+esc(hl[0].name).slice(0,18),share.toFixed(0)+'%','','amber','alert');
  h+=dkpi('Regulars (10+ answers)',num(reg),'','green','check');
  h+='</div><div class="card" style="margin-top:14px"><h3>Who answers \\u2014 '+p.start+' \\u2192 '+p.end+'</h3>'+
     '<table class="lb"><thead><tr><th>Member</th><th>Answers</th><th>People helped</th><th>Median reply</th></tr></thead><tbody>';
  for(i=0;i<hl.length;i++)h+='<tr><td>'+esc(hl[i].name)+'</td><td>'+num(hl[i].answers)+'</td><td>'+num(hl[i].helped)+'</td><td>'+Math.round(hl[i].median)+' min</td></tr>';
  h+='</tbody></table>';
  if(share>=25)h+='<div class="note">\\u26a0 '+esc(hl[0].name)+' answers '+share.toFixed(0)+'% of everything \\u2014 a single point of failure worth spreading.</div>';
  return h+'</div>';}

function pad2(n){return (n<10?'0':'')+n;}
function slotLabel(start,gran){return gran==='block'?pad2(start)+':00\\u2013'+pad2((start+3)%24)+':59':pad2(start)+':00';}
function viewCoverage(p){
  var c=p.cover||[],gran=p.cover_gran||'hour';
  var h='<div class="meta">How long a question waits before anyone answers, by when it was asked. This is a staffing picture: the slow slots are the gaps in cover.</div>';
  if(!c.length)return h+'<div class="card"><div class="meta">Not enough answered questions in this window to estimate coverage. Pick a longer period \\u2014 a quarter or more gives a stable read.</div></div>';
  var mx=0,wi=0,bi=0,i,tot=0;
  for(i=0;i<c.length;i++){mx=Math.max(mx,c[i][1]);tot+=c[i][2];
    if(c[i][1]>c[wi][1])wi=i;if(c[i][1]<c[bi][1])bi=i;}
  mx=mx||1;
  h+='<div class="grid g4">';
  h+=dkpi('Slowest slot',slotLabel(c[wi][0],gran),'','amber','alert');
  h+=dkpi('Wait then',Math.round(c[wi][1])+' min','','blue','clock');
  h+=dkpi('Fastest slot',slotLabel(c[bi][0],gran),'','green','check');
  h+=dkpi('Wait then',Math.round(c[bi][1])+' min','','violet','clock');
  h+='</div><div class="card" style="margin-top:14px"><h3>Median wait by time asked (UTC)</h3>';
  for(i=0;i<c.length;i++){var col=c[i][1]>=60?'var(--bad)':'var(--accent)';
    var tt=Math.round(c[i][1])+' min median wait \\u00b7 '+slotLabel(c[i][0],gran)+' \\u00b7 '+c[i][2]+' questions';
    h+='<div class="hbar" data-tt="'+esc(tt)+'"><span class="nm">'+slotLabel(c[i][0],gran)+'</span>'+
       '<span class="bar"><span style="width:'+(c[i][1]/mx*100).toFixed(1)+'%;background:'+col+'"></span></span>'+
       '<span class="n">'+Math.round(c[i][1])+'m</span></div>';}
  var note=gran==='block'
    ? 'Grouped into 4-hour blocks \\u2014 this window has too few answered questions ('+tot+') for a reliable hour-by-hour read.'
    : 'Hours with fewer than 5 answered questions are omitted.';
  return h+'<div class="meta" style="font-size:11px;margin-top:7px">'+note+' \\u00b7 red = an hour or worse</div></div>';}

function viewAttention(p){
  var g=p.negatives||[],h='<div class="meta">Messages the sentiment classifier scored most negative \\u2014 the flags worth a human read.</div>'+
    '<div class="card"><h3>Most negative messages</h3>';
  if(!g.length)return h+'<div class="meta">No strongly negative messages in this window.</div></div>';
  for(var i=0;i<g.length;i++)h+='<div class="msg"><div class="mh"><b>'+esc(g[i].author)+'</b> in #'+esc(g[i].channel)+
    '<span class="chip">'+esc(g[i].when)+'</span></div>'+esc(g[i].text)+'</div>';
  if(p.neg>g.length)h+='<div class="meta" style="margin-top:10px">Showing the '+g.length+' most negative of '+num(p.neg)+' flagged in this window.</div>';
  return h+'</div>';}

function fmtDur(h){
  if(h<1){var m=Math.round(h*60);return m+(m===1?' minute':' minutes');}
  if(h<48){var x=Math.round(h);return x+(x===1?' hour':' hours');}
  var d=Math.round(h/24);return d+(d===1?' day':' days');}
function viewSafety(p,q,cmp){
  var h='<div class="meta">Scam and abuse reporting \\u2014 the dedicated report channel, plus risk language showing up everywhere else.</div>';
  h+='<div class="grid g4">';
  h+=dkpi('Reports filed',num(p.sf_reports),sigDelta(p.sf_reports,base(p,q,cmp,'sf_reports'),false,p.days,bdays(p,q,cmp)),'amber','alert');
  h+=dkpi('People reporting',num(p.sf_reporters),'','violet','people');
  h+=dkpi('Risk mentions elsewhere',num(p.sf_mentions),sigDelta(p.sf_mentions,base(p,q,cmp,'sf_mentions'),false,p.days,bdays(p,q,cmp)),'blue','msg');
  h+=dkpi('Reports per week',(p.days?(p.sf_reports/(p.days/7)).toFixed(1):'0'),'','green','clock');
  h+='</div>';
  h+='<div class="grid g2" style="margin-top:14px">';
  h+='<div class="card"><h3>Where risk language appears</h3>'+hbars(p.sf_mention_channels||[])+
     '<div class="meta" style="font-size:11px;margin-top:7px">Messages mentioning scam, phishing, drain, seed phrase, private key, impersonation or giveaway \\u2014 outside the report channel these are unmoderated.</div></div>';
  h+='<div class="card"><h3>Most active reporters</h3>'+hbars(p.sf_top_reporters||[])+'</div>';
  h+='</div>';
  h+='<div class="card" style="margin-top:14px"><h3>Recent reports</h3>';
  var g=p.sf_recent||[];
  if(!g.length)h+='<div class="meta">No reports with message text in this window.</div>';
  for(var i=0;i<g.length;i++)h+='<div class="msg"><div class="mh"><b>'+esc(g[i].author)+'</b> in #'+esc(g[i].channel)+
    '<span class="chip">'+esc(g[i].when)+'</span></div>'+esc(g[i].text)+'</div>';
  return h+'</div>';}

function viewNewcomers(p,q,cmp){
  var a=p.nc_arrived||0,r=p.nc_retained||0,reg=p.nc_regulars||0,one=p.nc_oneshot||0;
  var rate=a?r/a*100:0;
  var h='<div class="meta">Everyone who spoke for the first time in this window, and whether they were ever heard from again. Retention is measured across the whole archive, not just this window.</div>';
  h+='<div class="grid g4">';
  h+=dkpi('First-time posters',num(a),sigDelta(a,base(p,q,cmp,'nc_arrived'),true,p.days,bdays(p,q,cmp)),'blue','join');
  h+=dkpi('Came back',rate.toFixed(0)+'%',sigRate(r,a,base(p,q,cmp,'nc_retained'),base(p,q,cmp,'nc_arrived')),'green','check');
  h+=dkpi('Never posted again',num(one),'','amber','alert');
  h+=dkpi('Became regulars (5+)',num(reg),'','violet','people');
  h+='</div>';
  /* Funnel: each stage as a share of arrivals, so the drop-off is the story. */
  var stages=[['Posted once',a],['Posted again',r],['Became a regular (5+ messages)',reg]];
  h+='<div class="card" style="margin-top:14px"><h3>Retention funnel</h3>';
  for(var i=0;i<stages.length;i++){var pc=a?stages[i][1]/a*100:0;
    h+='<div class="hbar" data-tt="'+esc(stages[i][0]+' \\u00b7 '+num(stages[i][1])+' of '+num(a)+' ('+pc.toFixed(0)+'%)')+'">'+
       '<span class="nm" style="width:210px">'+esc(stages[i][0])+'</span>'+
       '<span class="bar"><span style="width:'+pc.toFixed(1)+'%"></span></span>'+
       '<span class="n">'+num(stages[i][1])+'</span></div>';}
  h+='<div class="meta" style="font-size:11px;margin-top:7px">'+(a-r)+' of '+num(a)+' newcomers ('+
     (a?((a-r)/a*100).toFixed(0):0)+'%) said one thing and were never seen again.</div></div>';
  h+='<div class="card" style="margin-top:14px"><h3>Introductions</h3>';
  var ic=p.nc_intro||0,cv=p.nc_intro_converted||0;
  h+='<div class="meta">'+num(ic)+' of these newcomers posted in #introductions. <b>'+num(cv)+'</b> ('+
     (ic?(cv/ic*100).toFixed(0):0)+'%) went on to post anywhere else.</div>';
  if(p.nc_median_return_h!=null)
    h+='<div class="note">Those who did come back took a median of '+
       fmtDur(p.nc_median_return_h)+
       ' to post a second time \\u2014 the window where a welcome still lands.</div>';
  return h+'</div>';}

function viewChannels(p){
  var rows=p.ch_rows||[];
  var h='<div class="meta">Where the conversation actually lives, and what has gone quiet.</div>';
  h+='<div class="grid g4">';
  h+=dkpi('Channels with traffic',num(p.ch_total),'','blue','msg');
  h+=dkpi('Active (50+ messages)',num(p.ch_active),'','green','check');
  h+=dkpi('Nearly dead (&lt;50)',num(p.ch_quiet),'','amber','alert');
  h+=dkpi('Top 3 hold',(p.ch_top3_share||0)+'%','','violet','people');
  h+='</div>';
  h+='<div class="card" style="margin-top:14px"><h3>Channels by volume</h3>'+
     '<table class="lb"><thead><tr><th>Channel</th><th>Messages</th><th>People</th><th>Share</th></tr></thead><tbody>';
  for(var i=0;i<rows.length;i++)
    h+='<tr><td>#'+esc(rows[i][0])+'</td><td>'+num(rows[i][1])+'</td><td>'+num(rows[i][2])+'</td><td>'+rows[i][3]+'%</td></tr>';
  h+='</tbody></table>';
  if(p.ch_quiet>0)h+='<div class="note">'+num(p.ch_quiet)+' of '+num(p.ch_total)+
    ' channels carry fewer than 50 messages in this window. Consolidating them concentrates the people who are left.</div>';
  return h+'</div>';}


/* Reveal each chart's draw animation when it scrolls into view -- a direct port of
   revealCharts() on the Reddit page. Must run AFTER #view is populated, since the
   observer needs the svg nodes to exist. */
var chartIO=null;
function armCharts(){
  if(!('IntersectionObserver' in window)){
    document.querySelectorAll('#view svg').forEach(function(s){s.classList.add('chart-in');});return;}
  if(chartIO)chartIO.disconnect();
  chartIO=new IntersectionObserver(function(entries){
    entries.forEach(function(e){
      /* reveal on entry, or if it has already been scrolled past on a fast jump */
      var passed=e.rootBounds&&e.boundingClientRect.bottom<=e.rootBounds.top;
      if(e.isIntersecting||passed){e.target.classList.add('chart-in');chartIO.unobserve(e.target);}});
  },{threshold:0.18,rootMargin:'0px 0px -8% 0px'});
  document.querySelectorAll('#view svg').forEach(function(svg){
    if(svg.querySelector('.cdraw'))chartIO.observe(svg);});
}

function curView(){return (location.hash||'').slice(1).split('?')[0]||'dashboard';}
function render(){
  if(!DATA)return;
  var p=scopeOf(periodSel);if(!p)return;
  var cmp=compareSel.kind!=='none',q=scopeOf(compareSel),v=curView();
  var pb=document.querySelector('#periodBtn .rb-l'),ph=document.getElementById('periodHint'),
      cb=document.querySelector('#compareBtn .rb-l'),ch=document.getElementById('compareHint');
  if(pb)pb.textContent=selLabel(periodSel);
  if(ph)ph.textContent=selHint(periodSel);
  if(cb)cb.textContent=cmp?selLabel(compareSel):'Compare';
  if(ch)ch.textContent=cmp?'vs '+selHint(compareSel):'';
  var t=document.getElementById('viewTitle');if(t)t.textContent=TITLES[v]||'Overview';
  var badge={dashboard:num(p.messages),answers:num(p.unanswered),helpers:num(p.helper_count),coverage:'',attention:num(p.neg),safety:num(p.sf_reports),newcomers:num(p.nc_arrived),channels:num(p.ch_total)};
  document.querySelectorAll('#nav a').forEach(function(a){
    var k=a.getAttribute('data-v'),c=a.querySelector('.cnt');
    a.classList.toggle('active',k===v);
    if(c){c.textContent=badge[k]==null?'':badge[k];c.style.display=badge[k]?'':'none';}});
  var h;
  if(v==='answers')h=viewAnswers(p,q,cmp);
  else if(v==='helpers')h=viewHelpers(p,q,cmp);
  else if(v==='coverage')h=viewCoverage(p);
  else if(v==='attention')h=viewAttention(p);
  else if(v==='safety')h=viewSafety(p,q,cmp);
  else if(v==='newcomers')h=viewNewcomers(p,q,cmp);
  else if(v==='channels')h=viewChannels(p);
  else h=viewOverview(p,q,cmp);
  var host=document.getElementById('view');if(host)host.innerHTML=h;
  window.scrollTo(0,0);armCharts();}


/* ---- calendar: pick an arbitrary start/end, same flow as the Reddit picker ---- */
var calTab='start', calStart=null, calEnd=null, calMonth=null, calOpen=false;
var MONTHS=['January','February','March','April','May','June','July','August','September','October','November','December'];
function ymd(y,m,d){return y+'-'+('0'+(m+1)).slice(-2)+'-'+('0'+d).slice(-2);}
function monthGrid(y,m){
  var first=new Date(y,m,1).getDay(), n=new Date(y,m+1,0).getDate(), h='';
  ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'].forEach(function(d){h+='<div class="rpop-dh">'+d+'</div>';});
  for(var i=0;i<first;i++)h+='<div></div>';
  for(var d=1;d<=n;d++){var ds=ymd(y,m,d);
    var dis=ds<DATA.earliest||ds>DATA.latest;
    var sel=(ds===calStart||ds===calEnd);
    var inr=calStart&&calEnd&&ds>calStart&&ds<calEnd;
    h+='<div class="rpop-d'+(dis?' dis':'')+(sel?' sel':'')+(inr?' inr':'')+'" data-d="'+ds+'">'+d+'</div>';}
  return '<div class="rpop-m"><h4>'+MONTHS[m]+' '+y+'</h4><div class="rpop-grid">'+h+'</div></div>';
}
function renderCal(){
  var el=document.getElementById('rpopCal'); if(!el)return;
  if(!calMonth){var L=new Date(DATA.latest+'T12:00:00');calMonth=new Date(L.getFullYear(),L.getMonth()-1,1);}
  var m2=new Date(calMonth.getFullYear(),calMonth.getMonth()+1,1);
  el.querySelector('#rpopMonths').innerHTML=
    monthGrid(calMonth.getFullYear(),calMonth.getMonth())+monthGrid(m2.getFullYear(),m2.getMonth());
  el.querySelectorAll('.rpop-tab').forEach(function(t){t.classList.toggle('active',t.getAttribute('data-tab')===calTab);});
  el.querySelector('#rpopApply').disabled=!(calStart&&calEnd);
}
function pickDate(ds){
  if(calTab==='start'){calStart=ds;if(calEnd&&calEnd<ds)calEnd=null;calTab='end';}
  else{if(calStart&&ds<calStart){calEnd=calStart;calStart=ds;}else calEnd=ds;}
  renderCal();
}

/* ---- picker popover: presets, then every semi-monthly cohort ---- */
var pickRole=null;
function closePop(){var e=document.getElementById('rangePop');if(e)e.style.display='none';pickRole=null;}
function openPicker(role,btn){
  var pop=document.getElementById('rangePop');if(!pop||!DATA)return;
  pickRole=role;calOpen=false;var sel=role==='period'?periodSel:compareSel,h='';
  if(role==='compare')h+='<button data-k="none"'+(compareSel.kind==='none'?' class="sel"':'')+'>No comparison</button><div class="div"></div>';
  DATA.presets.forEach(function(p,i){
    var on=sel&&sel.kind==='preset'&&sel.idx===i;
    h+='<button data-k="preset" data-i="'+i+'"'+(on?' class="sel"':'')+'>'
      +'<span>'+esc(p.label)+'</span><span class="n">'+num(p.messages)+'</span></button>';});
  h+='<div class="div"></div>'
    +'<button data-k="cal"'+(sel&&sel.kind==='custom'?' class="sel"':'')+'>'
    +'<span>Date range</span><span class="n">\u203a</span></button>';
h+='<div class="rpop-cal" id="rpopCal" style="display:'+(calOpen?'block':'none')+'">'+'<div class="rpop-tabs"><button class="rpop-tab" data-tab="start" type="button">Start</button>'+'<button class="rpop-tab" data-tab="end" type="button">End</button></div>'+'<div class="rpop-nav"><button id="rpopPrev" type="button">‹</button>'+'<button id="rpopNext" type="button">›</button></div>'+'<div id="rpopMonths" class="rpop-months"></div>'+'<div class="rpop-actions"><button id="rpopApply" type="button" class="rpop-apply">Apply</button></div></div>';pop.innerHTML=h;pop.style.display='block';if(calOpen)renderCal();
  positionPop(btn);}
function positionPop(btn){var pop=document.getElementById('rangePop');
  btn=btn||document.getElementById(pickRole==='period'?'periodBtn':'compareBtn');
  if(!pop||!btn)return;var r=btn.getBoundingClientRect();
  var cal=document.getElementById('rpopCal');
  var w=(cal&&cal.style.display!=='none')?620:240;   /* size for the state it will be in */
  w=Math.min(w,window.innerWidth-24);
  var left=r.left;
  if(left+w>window.innerWidth-12)left=Math.max(12,window.innerWidth-w-12);
  pop.style.left=left+'px';pop.style.top=(r.bottom+6)+'px';}
document.addEventListener('click',function(e){
  if(!e.target.closest)return;
  var pb=e.target.closest('#periodBtn'),cb=e.target.closest('#compareBtn');
  if(pb){e.stopPropagation();if(pickRole==='period')closePop();else openPicker('period',pb);return;}
  if(cb){e.stopPropagation();if(pickRole==='compare')closePop();else openPicker('compare',cb);return;}
  var day=e.target.closest('#rangePop .rpop-d');
  if(day){e.stopPropagation();if(!day.classList.contains('dis'))pickDate(day.getAttribute('data-d'));return;}
  var tab=e.target.closest('#rangePop .rpop-tab');
  if(tab){e.stopPropagation();calTab=tab.getAttribute('data-tab');renderCal();return;}
  if(e.target.closest('#rpopPrev')){e.stopPropagation();calMonth=new Date(calMonth.getFullYear(),calMonth.getMonth()-1,1);renderCal();return;}
  if(e.target.closest('#rpopNext')){e.stopPropagation();calMonth=new Date(calMonth.getFullYear(),calMonth.getMonth()+1,1);renderCal();return;}
  if(e.target.closest('#rpopApply')){e.stopPropagation();
    if(calStart&&calEnd){var sel={kind:'custom',start:calStart,end:calEnd};
      if(pickRole==='period')periodSel=sel;else compareSel=sel;
      calOpen=false;closePop();render();}return;}
  var opt=e.target.closest('#rangePop button');
  if(opt&&opt.getAttribute('data-k')==='cal'){e.stopPropagation();calOpen=true;
    var c=document.getElementById('rpopCal');if(c){c.style.display='block';renderCal();positionPop();}return;}
  if(opt){var k=opt.getAttribute('data-k'),i=parseInt(opt.getAttribute('data-i'),10);
    var s=k==='none'?{kind:'none'}:{kind:k,idx:i};
    if(pickRole==='period')periodSel=s;else compareSel=s;
    closePop();render();return;}
  if(!e.target.closest('#rangePop'))closePop();});
window.addEventListener('resize',closePop);

/* Hover capsule: one delegated mousemove reads data-tt off whatever is under the
   cursor, so re-rendered charts need no re-binding. */
var tipEl=null;
function tipNode(){if(!tipEl){tipEl=document.createElement('div');tipEl.id='tip';document.body.appendChild(tipEl);}return tipEl;}
document.addEventListener('mousemove',function(e){
  var t=e.target,el=tipNode();
  var txt=t&&t.getAttribute?t.getAttribute('data-tt'):null;
  if(!txt&&t&&t.closest){var w=t.closest('[data-tt]');if(w)txt=w.getAttribute('data-tt');}
  if(!txt){el.style.display='none';return;}
  el.textContent=txt;el.style.display='block';
  var r=el.getBoundingClientRect(),x=e.pageX+12,y=e.pageY+16;
  if(x+r.width>window.scrollX+document.documentElement.clientWidth-8)x=e.pageX-r.width-12;
  el.style.left=x+'px';el.style.top=y+'px';});
document.addEventListener('mouseleave',function(){if(tipEl)tipEl.style.display='none';});

function restoreSidebar(){var p=app();if(!p)return;
  try{if(localStorage.getItem('hintel-sb')==='0')p.classList.remove('sb-collapsed');}catch(_){}
  if(mqSmall.matches)p.classList.remove('sb-collapsed');}

/* Controls live in the top bar on desktop and in the drawer on mobile; moving the
   node keeps one set of listeners rather than duplicating the picker. */
var mqSmall=window.matchMedia('(max-width:900px)');
function placeControls(){var c=document.querySelector('.tbctrls');if(!c)return;
  var host=mqSmall.matches?document.getElementById('sbCtrlMount'):document.querySelector('.topbar');
  if(host&&c.parentElement!==host)host.appendChild(c);}
mqSmall.addEventListener('change',function(){placeControls();closePop();});
/* matchMedia change does not always fire on programmatic resize, and a stuck
   placement leaves the controls unreachable, so resize is a cheap backstop. */
window.addEventListener('resize',placeControls);
function bootData(){
  if(booted)return true;
  var el=document.getElementById('ddata');if(!el)return false;
  try{DATA=JSON.parse(el.textContent);}catch(err){return false;}
  periodSel={kind:'preset',idx:DATA.default_preset||0};booted=true;restoreSidebar();placeControls();render();return true;}
document.addEventListener('DOMContentLoaded',function(){
  placeControls();
  if(!bootData()){var mo=new MutationObserver(function(){if(bootData())mo.disconnect();});
    mo.observe(document.body,{childList:true,subtree:true});}});
})();</script>
"""

DKPI_ICONS = {
 'msg':'<path d="M21 11.5a8.4 8.4 0 0 1-9 8.5 8.4 8.4 0 0 1-3.8-.9L3 21l1.9-5.2A8.4 8.4 0 0 1 4 11.5a8.4 8.4 0 0 1 9-8.5 8.4 8.4 0 0 1 8 8.5z"/>',
 'people':'<path d="M16 19v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 19v-2a4 4 0 0 0-3-3.87"/>',
 'join':'<path d="M16 19v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M19 8v6"/><path d="M22 11h-6"/>',
 'react':'<path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1-1.1a5.5 5.5 0 0 0-7.8 7.8l1.1 1L12 21l7.7-7.6 1.1-1a5.5 5.5 0 0 0 0-7.8z"/>',
 'ask':'<circle cx="12" cy="12" r="10"/><path d="M9.1 9a3 3 0 0 1 5.8 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/>',
 'check':'<path d="M22 11.1V12a10 10 0 1 1-5.9-9.1"/><polyline points="22 4 12 14.01 9 11.01"/>',
 'alert':'<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>',
 'clock':'<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>'}

def dkpi(label, value, d='', tint='blue', icon='msg'):
    """Tinted KPI tile: uppercase key, big value, circular icon badge, delta row."""
    ico = DKPI_ICONS.get(icon, DKPI_ICONS['msg'])
    sub = f'{d}<span>vs previous window</span>' if d else ''
    return (f'<div class="kpi t-{tint}"><div class="kpi-top"><div>'
            f'<div class="l">{label}</div><div class="v">{value}</div></div>'
            f'<span class="kpi-ico"><svg viewBox="0 0 24 24">{ico}</svg></span></div>'
            f'<div class="kpi-d">{sub}</div></div>')

HEADER = """<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ℏIntel — Discord Dashboard</title><link rel="icon" href="public/log.png"><script defer src="/_vercel/insights/script.js"></script><link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
{js}<style>{css}</style></head><body>"""

# Sidebar icons, same Lucide set and stroke treatment as the Reddit dashboard.
NAV_ICONS = {
 'dashboard': '<rect x="3" y="3" width="7" height="9" rx="1"/><rect x="14" y="3" width="7" height="5" rx="1"/>'
             '<rect x="14" y="12" width="7" height="9" rx="1"/><rect x="3" y="16" width="7" height="5" rx="1"/>',
 'answers':  '<circle cx="12" cy="12" r="10"/><path d="M9.1 9a3 3 0 0 1 5.8 1c0 2-3 3-3 3"/>'
             '<line x1="12" y1="17" x2="12.01" y2="17"/>',
 'helpers':  '<path d="M16 19v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/>'
             '<path d="M22 19v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.1a4 4 0 0 1 0 7.8"/>',
 'coverage': '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
 'attention':'<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/>'
             '<line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>',
 'channels': '<line x1="4" y1="9" x2="20" y2="9"/><line x1="4" y1="15" x2="20" y2="15"/>'
             '<line x1="10" y1="3" x2="8" y2="21"/><line x1="16" y1="3" x2="14" y2="21"/>',
 'newcomers':'<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/>'
             '<line x1="19" y1="8" x2="19" y2="14"/><line x1="22" y1="11" x2="16" y2="11"/>',
 'safety':   '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1'
             'c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/>'
             '<path d="M12 8v4"/><path d="M12 16h.01"/>',
}

SB_SVG = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="16" rx="2"/><line x1="9" y1="4" x2="9" y2="20"/><polyline class="arr arr-open" points="13.5 9.5 16 12 13.5 14.5"/><polyline class="arr arr-close" points="16 9.5 13.5 12 16 14.5"/></svg>')

MENU_SVG = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
            'stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="16" rx="2"/>'
            '<line x1="9" y1="4" x2="9" y2="20"/></svg>')


def shell(tabs, views, note):
    """Sidebar + main, mirroring the Reddit dashboard's app shell.

    `tabs` is [(key, label, count, warn)] and `views` maps key -> html. Every view is
    rendered server-side into its own hidden section; the nav just toggles which one
    is visible, so switching tabs costs nothing and the page still works as one file.
    """
    nav = ''
    for i, (key, label, cnt, warn) in enumerate(tabs):
        cls = ' class="active"' if i == 0 else ''
        wcls = ' warn' if warn else ''
        badge = f'<span class="cnt{wcls}">{cnt}</span>' if cnt not in (None, '') else ''
        nav += (f'<a data-v="{key}"{cls}>'
                f'<svg viewBox="0 0 24 24">{NAV_ICONS[key]}</svg>'
                f'<span class="t">{E(label)}</span>{badge}</a>')
    # The server-rendered default view stays in #view as a no-JS fallback: if the
    # client render ever fails, the page still shows real numbers instead of blank.
    body = views[tabs[0][0]]
    first = E(tabs[0][1])
    return (f'<div class="app sb-collapsed"><div id="sbScrim" class="sbscrim"></div>'
            f'<aside class="sidebar"><div class="sbtop">'
            f'<a class="brand" href="index.html" title="ℏIntel hub">'
            f'<img class="logo" src="public/log.png" alt="ℏIntel">'
            f'<span><span class="h">ℏ</span>Intel</span></a>'
            f'<button id="sbToggle" class="sbtoggle" type="button" aria-label="Toggle sidebar" '
            f'data-tip-open="Open sidebar" data-tip-close="Close sidebar">{SB_SVG}</button></div>'
            f'<nav class="nav" id="nav">{nav}</nav>'
            f'<div id="sbCtrlMount" class="sbctrls"></div>'
            f'<div class="sbnote">{note}</div></aside>'
            f'<div class="main"><div class="topbar">'
            f'<button id="mOpen" class="topmenu" type="button" aria-label="Open sidebar">{MENU_SVG}</button>'
            f'<h2 id="viewTitle">{first}</h2>'
            f'<a class="pswap" href="reddit.html" title="Switch to the Reddit dashboard">'
            f'<img src="public/reddit_icon.png" alt="Reddit"></a>'
            f'<div class="tbctrls">'
            f'<span class="sub" id="periodHint"></span>'
            f'<button class="rangebtn" id="periodBtn" type="button">'
            f'<svg class="rb-i" viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="18" rx="2"/>'
            f'<line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/>'
            f'<line x1="3" y1="10" x2="21" y2="10"/></svg><span class="rb-l">Period</span>'
            f'<svg class="rb-c" viewBox="0 0 24 24"><polyline points="6 9 12 15 18 9"/></svg></button>'
            f'<span class="sub" id="compareHint"></span>'
            f'<button class="rangebtn" id="compareBtn" type="button">'
            f'<svg class="rb-i" viewBox="0 0 24 24"><path d="M3 6h18M6 12h12M10 18h4"/></svg>'
            f'<span class="rb-l">Compare</span>'
            f'<svg class="rb-c" viewBox="0 0 24 24"><polyline points="6 9 12 15 18 9"/></svg></button>'
            f'<button class="theme-toggle" id="themeBtn" type="button" title="Toggle theme">'
            f'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
            f'stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg></button>'
            f'</div></div>'
            f'<div id="rangePop" class="rpop" style="display:none"></div>'
            f'<div class="content"><div id="view">{body}</div>{FOOT}</div></div></div>')

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
            '<div style="font:600 18px Plus Jakarta Sans,Inter,system-ui,Segoe UI,Roboto,sans-serif;color:var(--ink);margin-bottom:6px">🔒 Moderators only</div>'
            '<div class="meta" style="margin-bottom:18px">This Discord dashboard contains member names and messages. '
            'Enter the moderator password to view.</div>'
            '<input id="pw" type="password" placeholder="Password" style="width:100%;padding:11px 13px;border:1px solid var(--line);'
            'border-radius:9px;background:var(--card);color:var(--ink);font:15px Plus Jakarta Sans,Inter,system-ui,Segoe UI,Roboto,sans-serif" '
            'onkeydown="if(event.key===\'Enter\')unlock()">'
            '<div id="err" style="color:var(--bad);font-size:13px;margin-top:8px;min-height:18px"></div>'
            '<button onclick="unlock()" style="margin-top:6px;width:100%;padding:11px;border:none;border-radius:9px;'
            'background:var(--accent);color:#fff;font:600 14px Plus Jakarta Sans,Inter,system-ui,Segoe UI,Roboto,sans-serif;cursor:pointer">Unlock</button></div>'
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
    inner = _encrypt_gate(body) if gate else body
    # Icons live in Python so the server- and client-rendered tiles cannot drift apart.
    js = THEME_JS.replace('__ICONS__', json.dumps(DKPI_ICONS))
    with open(OUT, 'w', encoding='utf-8') as f:
        f.write(HEADER.format(css=THEME_CSS, js=js) + inner + '</body></html>')
    print(f'Dashboard written: {OUT}' + (' (password-protected)' if gate else ''))

def setup_page():
    # No shell here -- there is no data to navigate yet, so this stays a single page.
    write("""<div class="content" style="max-width:900px;margin:0 auto">
<h1 style="margin-bottom:6px"><span style="font-weight:400">ℏ</span>Intel — Hedera Discord</h1>
<div class="meta">No Discord data yet — this page activates automatically once the bot feed lands.</div>
<div class="card"><h3>Connect the Hedera Discord (one-time)</h3><ol class="setup">
<li>Create a bot at <b>discord.com/developers/applications</b> → New Application → Bot. Enable <b>Message Content Intent</b>. Copy the token.</li>
<li>Invite it to the server (OAuth2 → URL Generator: scope <b>bot</b>; permissions <b>View Channels</b> + <b>Read Message History</b>). A server admin must accept — same as the Notion connection, ask Abdoul/the Discord admin.</li>
<li>Save <b>discord_config.json</b> next to the scripts: <code>{"token":"BOT_TOKEN","guild_id":"SERVER_ID","channels":[]}</code></li>
<li>Run <code>python -X utf8 fetch_discord.py</code> then <code>python -X utf8 build_discord_dashboard.py</code>.</li>
</ol><div class="meta" style="margin-top:10px">Only the official Bot API is used — no user-token exports (Discord ToS).</div></div></div>""")
    try:
        os.makedirs('data/hub', exist_ok=True)
        json.dump({'platform': 'discord', 'label': 'Hedera Discord', 'href': 'discord.html',
                   'connected': False, 'window': 'Not connected yet', 'stats': []},
                  open('data/hub/discord.json', 'w', encoding='utf-8'))
    except Exception:
        pass

def area_svg(daily, color='#6366f1'):
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

def donut_html(title, segs, center_val, center_sub='total'):
    """Server-side twin of the donut() in the client script — the no-JS fallback has to
    look like the real page, not the old stacked bar."""
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
    leg = ''.join(f'<div class="lg"><span class="dot" style="background:{col}"></span>'
                  f'{E(lab)} <b>{round(v/total*100)}%</b>'
                  f' <span class="lgn">({v:,})</span></div>' for lab, v, col in segs)
    return (f'<div class="card"><h3>{E(title)}</h3><div class="donut">'
            f'<svg viewBox="0 0 120 120" width="106" height="106">'
            f'<circle r="{R}" cx="60" cy="60" fill="none" stroke="var(--tag-bg)" stroke-width="15"/>{rings}'
            f'<text x="60" y="57" text-anchor="middle" style="fill:var(--ink);font-size:21px;font-weight:700">{center_val:,}</text>'
            f'<text x="60" y="73" text-anchor="middle" style="fill:var(--mut);font-size:9px">{E(center_sub)}</text></svg>'
            f'<div class="lcol">{leg}</div></div></div>')


def heatmap(hm, mx):
    days = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun']
    out = '<div class="heat">'
    for di, row in enumerate(hm):
        out += f'<div class="hrow"><span class="hlab">{days[di]}</span>'
        for c in row:
            a = (c / mx) if mx else 0
            bg = f'rgba(99,102,241,{0.15 + a*0.85:.2f})' if a else 'var(--tag-bg)'
            out += f'<span class="hcell" style="background:{bg}"></span>'
        out += '</div>'
    return out + '</div><div class="meta" style="font-size:11px;margin-top:7px">Messages by day-of-week × hour (UTC) · darker = busier</div>'

# ---------------------------------------------------------------- period machinery
# Reporting cadence matches the Reddit dashboard: a first-half cohort (1st-15th)
# and a second-half cohort (16th-end of month), so figures from the two platforms
# line up in the hub and in the staff update.
def semimonthly_cohorts(earliest, latest):
    out, y, m = [], earliest.year, earliest.month
    while datetime(y, m, 1) <= latest:
        first = datetime(y, m, 1)
        mid = datetime(y, m, 15)
        nxt = datetime(y + (m == 12), (m % 12) + 1, 1)
        last = nxt - timedelta(days=1)
        for s_, e_ in ((first, mid), (mid + timedelta(days=1), last)):
            if e_ >= earliest and s_ <= latest:
                out.append((max(s_, earliest), min(e_, latest)))
        y, m = y + (m == 12), (m % 12) + 1
    return out


SCAM_CH = re.compile(r'scam|report', re.I)
SCAM_KW = re.compile(r'\b(scam|phish\w*|hack(ed|er)?|steal|stolen|fake|drain\w*|rug ?pull|'
                     r'seed ?phrase|private ?key|impersonat\w*|giveaway)\b', re.I)


def build_context(df):
    """Author-level facts computed once over full history: when each person first and
    second spoke, and how much they ever said. Retention needs the whole timeline, not
    the selected window -- someone who joined in March and returned in June only counts
    as retained if we can see past the window edge."""
    o = df.sort_values('created_utc')
    g = o.groupby('author_id')['created_utc']
    # nth(1) returns a Series on the ORIGINAL index in this pandas version, which will
    # not align against author_id later. Rank within author and select instead.
    second = o[o.groupby('author_id').cumcount() == 1].set_index('author_id')['created_utc']
    return {'first': g.min(), 'second': second, 'count': o.groupby('author_id').size(),
            'intro': set(o[o['channel'] == 'introductions']['author_id'].dropna()),
            'elsewhere': set(o[o['channel'] != 'introductions']['author_id'].dropna())}


def newcomer_payload(ctx, start, end):
    """The retention funnel: who showed up, and who was still here afterwards."""
    first = ctx['first']
    arrived = first[(first >= start) & (first <= end)]
    ids = arrived.index
    n = len(ids)
    cnt = ctx['count'].reindex(ids).fillna(0)
    retained = int((cnt >= 2).sum())          # said something more than once, ever
    regulars = int((cnt >= 5).sum())
    sec = ctx['second'].reindex(ids).dropna()
    gap = ((sec - first.reindex(sec.index)).dt.total_seconds() / 3600) if len(sec) else None
    intro_in = ctx['intro'] & set(ids)
    intro_conv = len(intro_in & ctx['elsewhere'])
    return {
        'nc_arrived': n,
        'nc_retained': retained,
        'nc_regulars': regulars,
        'nc_oneshot': n - retained,
        'nc_median_return_h': float(gap.median()) if gap is not None and len(gap) else None,
        'nc_intro': len(intro_in),
        'nc_intro_converted': intro_conv,
    }


def safety_payload(df, start, end):
    """Scam/abuse reporting: the dedicated channel plus risk language everywhere else."""
    w = df[(df['created_utc'] >= start) & (df['created_utc'] <= end)]
    rep = w[w['channel'].str.contains(SCAM_CH, na=False)]
    kw = w[w['content'].fillna('').str.contains(SCAM_KW, na=False)]
    rows = [{'author': str(r['author']), 'channel': str(r['channel']),
             'when': r['created_utc'].strftime('%Y-%m-%d %H:%M'),
             'text': str(r['content'])[:220]}
            for _, r in rep.sort_values('created_utc', ascending=False).head(12).iterrows()
            if str(r['content']).strip()]
    top = [[str(a), int(v)] for a, v in
           rep.groupby('author').size().sort_values(ascending=False).head(8).items()]
    by_ch = [[f'#{c}', int(v)] for c, v in
             kw.groupby('channel').size().sort_values(ascending=False).head(8).items()]
    return {'sf_reports': len(rep), 'sf_reporters': int(rep['author_id'].nunique()),
            'sf_mentions': len(kw), 'sf_mention_channels': by_ch,
            'sf_recent': rows, 'sf_top_reporters': top}


def channels_payload(df, start, end):
    """Where activity actually lives, and what has gone quiet."""
    w = df[(df['created_utc'] >= start) & (df['created_utc'] <= end)]
    g = w.groupby('channel').agg(msgs=('id', 'size'), people=('author_id', 'nunique'))
    g = g.sort_values('msgs', ascending=False)
    total = int(g['msgs'].sum()) or 1
    rows = [[str(c), int(r['msgs']), int(r['people']), round(100 * r['msgs'] / total, 1)]
            for c, r in g.head(20).iterrows()]
    active = int((g['msgs'] >= 50).sum())
    quiet = int(((g['msgs'] > 0) & (g['msgs'] < 50)).sum())
    top3 = float(g['msgs'].head(3).sum() / total * 100) if len(g) else 0.0
    return {'ch_rows': rows, 'ch_total': int(len(g)), 'ch_active': active,
            'ch_quiet': quiet, 'ch_top3_share': round(top3, 1)}


def desk_payload(G, start, end, prev_start):
    """Answer-desk figures for one window, JSON-safe, with the previous window's
    counts alongside so the client can draw significance-tested deltas."""
    c = desk_stats(G, start, end)
    p = desk_stats(G, prev_start, start - timedelta(seconds=1))
    q = [{'author': str(r['author']), 'channel': str(r['channel']),
          'when': r['created_utc'].strftime('%Y-%m-%d %H:%M'),
          'text': str(r['content'])[:240]}
         for _, r in c['queue'].head(15).iterrows()]
    hl = [{'name': str(nm), 'answers': int(r['answers']), 'helped': int(r['helped']),
           'median': float(r['median_min'])}
          for nm, r in c['helpers'].head(15).iterrows()]
    cov = c['cover_rows']
    return {
        'questions': c['questions'], 'prev_questions': p['questions'],
        'answered': c['answered'], 'prev_answered': p['answered'],
        'unanswered': c['unanswered'], 'prev_unanswered': p['unanswered'],
        'median_wait': c['median_wait'],
        'answers_given': c['answers_given'], 'prev_answers_given': p['answers_given'],
        'helper_count': c['helper_count'], 'prev_helper_count': p['helper_count'],
        'queue': q, 'queue_total': len(c['queue']), 'helpers': hl, 'cover': cov,
        'cover_gran': c['cover_gran'],
    }



JOIN_RE_TXT = re.compile(r'joined', re.I)
LEAVE_RE_TXT = re.compile(r'(left|leave|kick|ban)\w*', re.I)


def split_joins(joins):
    """(joined, left, split_ok) from the join-log channel.

    The log bot records both events as embeds. Older rows were fetched before
    embeds were captured, so their text is empty and the two are indistinguishable
    -- in that case report the combined count and say so, rather than presenting
    churn as growth.
    """
    txt = joins.get('embed')
    if txt is None:
        return len(joins), 0, False
    txt = txt.fillna('').astype(str)
    if not (txt.str.strip() != '').any():
        return len(joins), 0, False
    j = int(txt.str.contains(JOIN_RE_TXT, na=False).sum())
    l = int(txt.str.contains(LEAVE_RE_TXT, na=False).sum())
    if j + l == 0:
        return len(joins), 0, False
    return j, l, True


def build_atoms(df, joins, G, ctx):
    """Per-day and per-event rows the client sums for an arbitrary date range.

    Precomputed periods cannot answer a custom range: messages and reactions sum, but
    unique members, the median wait, the helper table and the unanswered queue do not.
    So ship the underlying rows once -- questions, cross-author replies, flagged and
    scam messages -- indexed against lookup tables, and let the client filter by date.
    """
    d = df.sort_values('created_utc')
    day = lambda t: t.strftime('%Y-%m-%d')

    authors, chans, texts = {}, {}, {}
    def ai(aid, name):
        if aid not in authors:
            authors[aid] = [len(authors), str(name)]
        return authors[aid][0]
    def ci(c):
        if c not in chans:
            chans[c] = len(chans)
        return chans[c]
    def ti(t):
        t = str(t)[:220]
        if t not in texts:
            texts[t] = len(texts)
        return texts[t]

    # ---- per-day volume: everything that aggregates by simple addition
    daily = {}
    for k, g in d.groupby(d['created_utc'].dt.strftime('%Y-%m-%d')):
        labs = [hs.classify_text(t) if str(t).strip() else ('neutral', 0.0)
                for t in g['content'].fillna('').astype(str)]
        pos = sum(1 for l, _ in labs if l == 'positive')
        neg = sum(1 for l, _ in labs if l == 'negative')
        hrs = [0] * 24
        for t in g['created_utc']:
            hrs[t.hour] += 1
        daily[k] = {
            'm': len(g), 'r': int(g['reactions'].fillna(0).sum()), 'p': pos, 'n': neg,
            'a': sorted({ai(str(r.author_id), r.author) for r in g.itertuples()}),
            'c': {str(ci(c)): int(v) for c, v in g.groupby('channel').size().items()},
            'u': {str(ai(str(a), g[g.author_id == a]['author'].iloc[0])): int(v)
                  for a, v in g.groupby('author_id').size().items()},
            'h': hrs,
        }
    for k, g in joins.groupby(joins['created_utc'].dt.strftime('%Y-%m-%d')):
        daily.setdefault(k, {'m': 0, 'r': 0, 'p': 0, 'n': 0, 'a': [], 'c': {}, 'u': {}, 'h': [0]*24})
        daily[k]['j'] = len(g)

    # ---- questions: [day, hour, author, channel, wait|-1, everAnswered, textIdx]
    q = G['q']
    qrows = [[day(r.created_utc), r.created_utc.hour, ai(str(r.author_id), r.author), ci(r.channel),
              round(r.wait, 1) if r.wait == r.wait and r.wait is not None else -1,
              1 if r.ever else 0, ti(r.content), 1 if r.reply_to == r.reply_to and r.reply_to else 0]
             for r in q.itertuples()]

    # ---- cross-author replies: [day, answerer, asker, latency]
    rep = G['rep']
    # keyed on the QUESTION's date, matching desk_stats(), so the two paths agree
    rrows = [[day(r.t_time), ai(str(r.author_id), r.author),
              str(r.t_author), round(r.lat, 1)] for r in rep.itertuples()]

    # ---- flagged + scam rows, for Needs Attention and Safety over a custom range
    labs = [hs.classify_text(t) if str(t).strip() else ('neutral', 0.0)
            for t in d['content'].fillna('').astype(str)]
    dd = d.assign(_lab=[l for l, _ in labs], _sc=[sc for _, sc in labs])
    # itertuples() renames underscore-prefixed columns to positional _N, so a
    # leading-underscore name cannot be read by attribute. Rename before iterating,
    # or every score silently comes out 0 and "most negative" stops meaning anything.
    negs = dd[dd['_lab'] == 'negative'].rename(columns={'_sc': 'sc'})
    nrows = [[day(r.created_utc), ai(str(r.author_id), r.author), ci(r.channel),
              round(float(r.sc), 3), ti(r.content),
              r.created_utc.strftime('%Y-%m-%d %H:%M')] for r in negs.itertuples()]
    sf = dd[dd['channel'].str.contains(SCAM_CH, na=False)]
    srows = [[day(r.created_utc), ai(str(r.author_id), r.author), ci(r.channel), ti(r.content),
              r.created_utc.strftime('%Y-%m-%d %H:%M')] for r in sf.itertuples()]
    kw = dd[dd['content'].fillna('').str.contains(SCAM_KW, na=False)]
    krows = [[day(r.created_utc), ci(r.channel)] for r in kw.itertuples()]

    # ---- newcomer lookups: first-seen day and lifetime message count per author
    first = {str(ai(a, a)): day(t) for a, t in ctx['first'].items()}
    cnt = {str(ai(a, a)): int(v) for a, v in ctx['count'].items()}
    second = {str(ai(a, a)): day(t) for a, t in ctx['second'].items()}

    names = [None] * len(authors)
    for aid, (i, nm) in authors.items():
        names[i] = nm
    return {'daily': daily, 'authors': names,
            'channels': [c for c, _ in sorted(chans.items(), key=lambda x: x[1])],
            'texts': [t for t, _ in sorted(texts.items(), key=lambda x: x[1])],
            'q': qrows, 'rep': rrows, 'neg': nrows, 'sf': srows, 'kw': krows,
            'first': first, 'count': cnt, 'second': second,
            'intro': sorted({ai(a, a) for a in ctx['intro']}),
            'elsewhere': sorted({ai(a, a) for a in ctx['elsewhere']})}

def dmetrics(df, joins, start, end, G=None, ctx=None):
    """Every per-window figure for [start, end].

    Mirrors metrics() in build_dashboard.py so both platforms feed the same
    period/compare machinery. The equal-length window immediately before is used
    for deltas, which is what makes period-over-period comparison meaningful --
    the single rolling window this replaced had nothing to compare against.
    """
    ndays = (end.date() - start.date()).days + 1
    prev_start = start - timedelta(days=ndays)
    w = df[(df.created_utc >= start) & (df.created_utc <= end)]
    pw = df[(df.created_utc >= prev_start) & (df.created_utc < start)]
    n, pn = len(w), len(pw)

    nj = int(((joins.created_utc >= start) & (joins.created_utc <= end)).sum())
    jw = joins[(joins.created_utc >= start) & (joins.created_utc <= end)]
    n_join, n_left, split_ok = split_joins(jw)
    pnj = int(((joins.created_utc >= prev_start) & (joins.created_utc < start)).sum())

    members = int(w['author_id'].nunique())
    pmembers = int(pw['author_id'].nunique())
    # new vs returning, measured against everyone seen before this window
    prior = set(df[df.created_utc < start]['author_id'].dropna())
    here = set(w['author_id'].dropna())
    new_here = len(here - prior)

    reacts = int(w['reactions'].fillna(0).sum())

    daily = [(d.strftime('%Y-%m-%d'), int(v))
             for d, v in w.set_index('created_utc').resample('D').size().items()]
    chans = [(f'#{c}', int(v)) for c, v in
             w.groupby('channel').size().sort_values(ascending=False).head(10).items()]
    tops = [(a, int(v)) for a, v in
            w.groupby('author').size().sort_values(ascending=False).head(10).items()]

    hm = [[0] * 24 for _ in range(7)]
    for t in w['created_utc']:
        hm[t.weekday()][t.hour] += 1
    hmx = max((max(r) for r in hm), default=0)

    labs = [hs.classify_text(t) if str(t).strip() else ('neutral', 0.0)
            for t in w['content'].fillna('').astype(str)]
    ww = w.assign(_lab=[l for l, _ in labs], _sc=[sc for _, sc in labs])
    pos = int((ww['_lab'] == 'positive').sum())
    neg = int((ww['_lab'] == 'negative').sum())
    negs = ww[ww['_lab'] == 'negative'].sort_values('_sc').head(12)
    neg_rows = [{'author': str(r['author']), 'channel': str(r['channel']),
                 'when': r['created_utc'].strftime('%Y-%m-%d %H:%M'),
                 'text': str(r['content'])[:220]} for _, r in negs.iterrows()]

    out = {
        'start': start.strftime('%Y-%m-%d'), 'end': end.strftime('%Y-%m-%d'), 'days': ndays,
        'messages': n, 'prev_messages': pn, 'per_day': round(n / max(ndays, 1), 1),
        'members': members, 'prev_members': pmembers, 'new_members': nj,
        'prev_new_members': pnj, 'new_to_server': new_here, 'reactions': reacts,
        'joined': n_join, 'left': n_left, 'split_ok': split_ok,
        'prev_reactions': int(pw['reactions'].fillna(0).sum()),
        'pos': pos, 'neg': neg, 'neu': n - pos - neg,
        'daily': daily, 'channels': chans, 'contributors': tops,
        'heat': hm, 'heat_max': hmx, 'negatives': neg_rows,
    }
    if G is not None:
        out.update(desk_payload(G, start, end, prev_start))
    if ctx is not None:
        out.update(newcomer_payload(ctx, start, end))
        out.update(safety_payload(df, start, end))
        out.update(channels_payload(df, start, end))
    return out


# --------------------------------------------------------- comparison, with a floor
# Counts fluctuate on their own. #community-general averages ~85 questions per
# semi-monthly cohort; at that size random variation alone moves the number ~15%, and
# the unanswered count (~20) needs a 32% swing before it means anything. Printing an
# untested "+25%" chip on those invents trends that are not in the data. So every
# delta is significance-tested against its own sample size, and only shown if it
# clears the floor -- otherwise it reads "within noise", which is the honest answer.
Z95 = 1.96

def sig_delta(cur, prev, good_up=True):
    """Delta for a count, shown only if it beats the noise floor.

    Comparing two equal-length windows, the null is that each event was equally
    likely to fall in either, so cur ~ Binomial(cur+prev, 0.5) and
    z = (cur - prev) / sqrt(cur + prev).
    """
    if cur is None or prev is None:
        return ''
    if cur + prev == 0:
        return ''
    z = (cur - prev) / math.sqrt(cur + prev)
    if abs(z) < Z95:
        return ('<span class="delta flat" title="Change is within the noise floor for '
                'this sample size — not a real move">≈ flat</span>')
    if not prev:
        return '<span class="delta up" title="No activity in the previous window">new</span>'
    pct = (cur - prev) / prev * 100
    rising = pct >= 0
    cls = ('up' if rising else 'down') if good_up else ('down' if rising else 'up')
    return (f'<span class="delta {cls}" title="z={z:.1f} — clears the noise floor">'
            f'{"▲" if rising else "▼"} {abs(pct):.0f}%</span>')


def sig_delta_rate(x1, n1, x2, n2, good_up=True):
    """Delta for a proportion (e.g. % answered), via a two-proportion z-test."""
    if not n1 or not n2:
        return ''
    p1, p2 = x1 / n1, x2 / n2
    p = (x1 + x2) / (n1 + n2)
    se = math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2))
    if se == 0:
        return ''
    z = (p1 - p2) / se
    if abs(z) < Z95:
        return ('<span class="delta flat" title="Change is within the noise floor for '
                'this sample size — not a real move">≈ flat</span>')
    pts = (p1 - p2) * 100
    rising = pts >= 0
    cls = ('up' if rising else 'down') if good_up else ('down' if rising else 'up')
    return (f'<span class="delta {cls}" title="z={z:.1f} — clears the noise floor">'
            f'{"▲" if rising else "▼"} {abs(pts):.0f} pts</span>')


# ------------------------------------------------------------------ answer graph
QWORD = re.compile(r'^\s*(how|what|why|where|when|which|who|can|could|does|do|is|are|'
                   r'any(?:one|body)?|has|have|should|would|will)\b', re.I)
MENTION = re.compile(r'<@!?(\d+)>')
PROX_MIN = 30            # "answered promptly" -- the responsiveness metric
STALE_MIN = 60 * 24      # "never answered" -- what actually belongs in the queue

# Helpers offering help ("anyone need help?", "feel free to ask") match the question
# pattern but are not asks. Left in, they dominate the queue with the top helpers' own
# messages -- the opposite of what the queue is for.
OFFER = re.compile(r'(need (any\s*)?help|feel free to ask|how can i help|any (questions|issues)|'
                   r'dm me|happy to help|let me know if|anyone need)', re.I)


def is_question(t):
    t = (t or '').strip()
    if not t or t.startswith('http'):
        return False
    if OFFER.search(t):
        return False
    return t.endswith('?') or bool(QWORD.match(t))


def answer_graph(df):
    """Who asks, who answers, and what got dropped.

    Built once over the full community history, then sliced per window by
    desk_stats() -- so a question asked just before a window still resolves against
    a later answer, and the previous window costs nothing extra to compute.

    What counts as an answer matters more than it looks. Someone merely speaking
    after a question is not one: in #community-general 58% of *any* message draws a
    cross-author message within 30 minutes, so bare proximity measures channel
    traffic, not answering. We require the follow-up to address the asker -- a
    threaded reply, or an @-mention. That is deliberately a lower bound: an inline
    answer with neither will not be counted, so the queue over-reports rather than
    hiding real drops.
    """
    d = df.sort_values('created_utc')
    txt = d['content'].fillna('').astype(str)
    d = d.assign(_q=txt.map(is_question), _ment=txt.map(lambda t: set(MENTION.findall(t))))

    author_of = dict(zip(d['id'], d['author']))
    time_of = dict(zip(d['id'], d['created_utc']))

    rep = d[d['reply_to'].notna()].copy()
    rep['t_author'] = rep['reply_to'].map(author_of)
    rep['t_time'] = rep['reply_to'].map(time_of)
    rep = rep[rep['t_author'].notna() & (rep['t_author'] != rep['author'])]
    rep['lat'] = (rep['created_utc'] - rep['t_time']).dt.total_seconds() / 60
    rep = rep[rep['lat'] >= 0]

    prox = {}
    for _, g in d.groupby('channel', sort=False):
        ts = g['created_utc'].tolist(); au = g['author'].tolist()
        qq = g['_q'].tolist(); ids = g['id'].tolist()
        aid = g['author_id'].tolist(); ment = g['_ment'].tolist()
        for i, isq in enumerate(qq):
            if not isq:
                continue
            for j in range(i + 1, len(ts)):
                gap = (ts[j] - ts[i]).total_seconds() / 60
                if gap > STALE_MIN or j - i > 400:
                    break
                if au[j] != au[i] and aid[i] in ment[j]:
                    prox[ids[i]] = gap
                    break

    # Time to first answer = whichever landed first, the threaded reply or the
    # @-mention. Proximity alone would cap every wait at PROX_MIN and flatter it.
    thread_lat = rep.groupby('reply_to')['lat'].min().to_dict()

    def first_answer(i):
        c = [v for v in (prox.get(i), thread_lat.get(i)) if v is not None]
        return min(c) if c else None

    q = d[d['_q']].copy()
    q['wait'] = q['id'].map(first_answer)
    q['prompt'] = q['wait'].le(PROX_MIN)
    q['ever'] = q['wait'].le(STALE_MIN)
    return {'q': q, 'rep': rep}


def coverage_rows(aq, min_n=5):
    """Coverage at the finest granularity the sample actually supports.

    24 hourly medians need a lot of questions: a 15-day window has ~40, so almost no
    hour clears min_n and the panel used to read "not enough data" for anything short
    of a quarter. Fall back to 4-hour blocks (4x the sample per bar) before giving up,
    and tell the caller which granularity it got so the axis can be labelled honestly.
    """
    if not len(aq):
        return [], 'none'
    hourly = aq.groupby(aq['created_utc'].dt.hour)['wait'].agg(['median', 'size'])
    keep = hourly[hourly['size'] >= min_n]
    if len(keep) >= 4:
        return [[int(i), float(r['median']), int(r['size'])] for i, r in keep.iterrows()], 'hour'
    blocks = aq.groupby(aq['created_utc'].dt.hour // 4)['wait'].agg(['median', 'size'])
    keep = blocks[blocks['size'] >= min_n]
    if len(keep) >= 2:
        return [[int(i) * 4, float(r['median']), int(r['size'])] for i, r in keep.iterrows()], 'block'
    return [], 'none'


def desk_stats(G, start, end):
    """Slice the pre-built answer graph to one window. Cheap, so the previous window
    can be computed the same way for comparison."""
    q = G['q']
    q = q[(q['created_utc'] >= start) & (q['created_utc'] <= end)]
    # A question that is itself a threaded reply is mid-conversation, not an open ask.
    unans = q[~q['ever'] & q['reply_to'].isna()].sort_values('created_utc', ascending=False)

    rep = G['rep']
    rw = rep[(rep['t_time'] >= start) & (rep['t_time'] <= end)]
    helpers = (rw.groupby('author')
                 .agg(answers=('id', 'size'), helped=('t_author', 'nunique'),
                      median_min=('lat', 'median'))
                 .sort_values('answers', ascending=False))

    aq = q[q['wait'].notna()]
    cover = (aq.assign(hr=aq['created_utc'].dt.hour)
               .groupby('hr')['wait'].agg(['median', 'size'])) if len(aq) else None
    cover_rows, cover_gran = coverage_rows(aq)

    waits = q.loc[q['ever'], 'wait']
    return {'questions': len(q), 'answered': int(q['prompt'].sum()),
            'unanswered': len(unans), 'median_wait': float(waits.median()) if len(waits) else None,
            'answers_given': len(rw), 'helper_count': len(helpers),
            'queue': unans, 'helpers': helpers, 'cover': cover,
            'cover_rows': cover_rows, 'cover_gran': cover_gran, 'now': end}


def fmt_age(td):
    h = td.total_seconds() / 3600
    if h < 1:
        return f'{int(td.total_seconds() // 60)}m ago'
    if h < 48:
        return f'{int(h)}h ago'
    return f'{int(h // 24)}d ago'


def render_answer_desk(a, p=None):
    pct = 100 * a['answered'] / a['questions'] if a['questions'] else 0
    mw = f"{a['median_wait']:.0f} min" if a['median_wait'] is not None else '—'
    b = ('<div class="meta">Questions the community asked, and whether anyone actually '
         'answered them.</div>')
    b += '<div class="grid g4">'
    if p:
        d_q = sig_delta(a['questions'], p['questions'])
        d_pct = sig_delta_rate(a['answered'], a['questions'], p['answered'], p['questions'])
        d_un = sig_delta(a['unanswered'], p['unanswered'], good_up=False)
    else:
        d_q = d_pct = d_un = ''
    b += dkpi('Questions asked', f'{a["questions"]:,}', d_q, 'blue', 'ask')
    b += dkpi(f'Answered in {PROX_MIN} min', f'{pct:.0f}%', d_pct, 'green', 'check')
    b += dkpi('Never answered', f'{a["unanswered"]:,}', d_un, 'amber', 'alert')
    # No delta on the median: a shift in a median is not a count, so the count-based
    # test does not apply and a percentage here would be an unearned claim.
    b += dkpi('Median first reply', mw, '', 'violet', 'clock')
    b += '</div>'

    b += '<div class="card" style="margin-top:14px"><h3>Never answered — no reply in 24 hours</h3>'
    if len(a['queue']):
        for _, m in a['queue'].head(15).iterrows():
            b += (f'<div class="msg"><div class="mh"><b>{E(m["author"])}</b> in #{E(m["channel"])}'
                  f'<span class="chip">{fmt_age(a["now"] - m["created_utc"])}</span></div>'
                  f'{E(str(m["content"])[:240])}</div>')
        if len(a['queue']) > 15:
            b += f'<div class="meta" style="margin-top:10px">+ {len(a["queue"])-15:,} more unanswered.</div>'
    else:
        b += '<div class="meta">Every question in this window got a response.</div>'
    b += ('<div class="note">An answer means a threaded reply or an @-mention of the asker. '
          'A plain inline reply with neither is not detectable, so treat this as a review '
          'list rather than a verdict.</div></div>')
    return b


def render_coverage(a):
    b = ('<div class="meta">How long a question waits before anyone answers, by the hour it '
         'was asked. This is a staffing picture: the slow hours are the gaps in cover.</div>')
    c = a['cover'][a['cover']['size'] >= 5] if a['cover'] is not None else None
    if c is None or not len(c):
        return b + '<div class="card"><div class="meta">Not enough answered questions in this window.</div></div>'
    mx = c['median'].max() or 1
    worst = c['median'].idxmax()
    best = c['median'].idxmin()
    b += '<div class="grid g4">'
    b += dkpi('Slowest hour', f'{int(worst):02d}:00', '', 'amber', 'alert')
    b += dkpi('Wait then', f'{c["median"].max():.0f} min', '', 'blue', 'clock')
    b += dkpi('Fastest hour', f'{int(best):02d}:00', '', 'green', 'check')
    b += dkpi('Wait then', f'{c["median"].min():.0f} min', '', 'violet', 'clock')
    b += '</div>'
    b += '<div class="card" style="margin-top:14px"><h3>Median wait by hour asked (UTC)</h3>'
    for hr, row in c.iterrows():
        col = 'var(--bad)' if row['median'] >= 60 else 'var(--accent)'
        b += (f'<div class="hbar"><span class="nm">{int(hr):02d}:00</span>'
              f'<span class="bar"><span style="width:{row["median"]/mx*100:.1f}%;'
              f'background:{col}"></span></span>'
              f'<span class="n">{row["median"]:.0f}m</span></div>')
    b += ('<div class="meta" style="font-size:11px;margin-top:7px">Hours with fewer than 5 '
          'answered questions are omitted · red = an hour or worse</div></div>')
    return b


def render_helpers(a, window_label, p=None):
    h = a['helpers']
    b = ('<div class="meta">Who carries the answering load — read straight off the reply '
         'graph, no roles data needed.</div>')
    if not len(h):
        return b + '<div class="card"><div class="meta">No replies in this window.</div></div>'
    total = int(h['answers'].sum())
    share = 100 * h['answers'].iloc[0] / total if total else 0
    d_ans = sig_delta(total, p['answers_given']) if p else ''
    d_ppl = sig_delta(len(h), p['helper_count']) if p else ''
    b += '<div class="grid g4">'
    b += dkpi('Answers given', f'{total:,}', d_ans, 'blue', 'msg')
    b += dkpi('People answering', f'{len(h):,}', d_ppl, 'violet', 'people')
    b += dkpi(f'Carried by {E(str(h.index[0]))[:18]}', f'{share:.0f}%', '', 'amber', 'alert')
    b += dkpi('Regulars (10+ answers)', f'{int((h["answers"]>=10).sum()):,}', '', 'green', 'check')
    b += '</div>'
    b += (f'<div class="card" style="margin-top:14px"><h3>Who answers — {E(window_label)}</h3>'
          '<table class="lb"><thead><tr><th>Member</th><th>Answers</th><th>People helped</th>'
          '<th>Median reply</th></tr></thead><tbody>')
    for name, r in h.head(15).iterrows():
        b += (f'<tr><td>{E(name)}</td><td>{int(r["answers"]):,}</td><td>{int(r["helped"]):,}</td>'
              f'<td>{r["median_min"]:.0f} min</td></tr>')
    b += '</tbody></table>'
    if share >= 25:
        b += (f'<div class="note">⚠ {E(str(h.index[0]))} answers {share:.0f}% of everything — '
              f'a single point of failure worth spreading.</div>')
    b += '</div>'
    return b


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--days', type=int, default=14)
    args = ap.parse_args()

    if not os.path.exists(CSV_PATH):
        setup_page(); return
    # Snowflake IDs are 19 digits. Left to pandas, `reply_to` becomes float64 (NaNs
    # force it) and float64 holds only ~16 — every reply ID would be silently mangled,
    # breaking the answer graph. Read the ID columns as strings.
    raw = pd.read_csv(CSV_PATH, low_memory=False,
                      dtype={'id': str, 'reply_to': str, 'author_id': str, 'channel_id': str,
                             'embed': str})
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

    # ---- full-history periods (every cohort since the archive starts) -----------
    EARLIEST, LATEST = df['created_utc'].min(), df['created_utc'].max()
    G = answer_graph(df)
    CTX = build_context(df)
    COHORTS = semimonthly_cohorts(EARLIEST, LATEST)
    PERIODS = [dmetrics(df, joins, s_, e_.replace(hour=23, minute=59, second=59), G, CTX)
               for s_, e_ in COHORTS]

    def preset(label, ndays):
        s_ = (LATEST - timedelta(days=ndays - 1)).replace(hour=0, minute=0, second=0)
        d = dmetrics(df, joins, max(s_, EARLIEST), LATEST, G, CTX)
        d['label'] = label
        d['ndays'] = ndays
        return d
    PRESETS = [preset(l, n_) for l, n_ in
               (('Last 7 days', 7), ('Last 15 days', 15), ('Last month', 30),
                ('Last 12 weeks', 84), ('Last 6 months', 182), ('Last 365 days', 365))]

    ATOMS = build_atoms(df, joins, G, CTX)
    DATA = {'generated': datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC'),
            'presets': PRESETS, 'default_preset': 1,
            'earliest': EARLIEST.strftime('%Y-%m-%d'), 'latest': LATEST.strftime('%Y-%m-%d'),
            'atoms': ATOMS}
    print(f'Periods: {len(PERIODS)} cohorts {PERIODS[0]["start"]} -> {PERIODS[-1]["end"]}'
          f'  ({sum(p["messages"] for p in PERIODS):,} messages covered)')
    w = df[df['created_utc'] >= start]
    pw = df[(df['created_utc'] >= prev_start) & (df['created_utc'] < start)]

    n, pn = len(w), len(pw)
    members, pmembers = w['author_id'].nunique(), pw['author_id'].nunique()
    reacts = int(w['reactions'].fillna(0).sum())
    prev_reacts = int(pw['reactions'].fillna(0).sum())
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
         f'community channels, humans only (bot-logs &amp; mod-internal channels excluded)</div>')
    b += '<div class="grid g4">'
    b += dkpi(f'Messages · {per_day:.0f}/day', f'{n:,}', sig_delta(n, pn), 'blue', 'msg')
    b += dkpi('Active members', f'{members:,}', sig_delta(members, pmembers), 'violet', 'people')
    b += dkpi('Join/leave events', f'{new_members:,}', sig_delta(new_members, prev_members_j), 'green', 'join')
    b += dkpi('Reactions given', f'{reacts:,}', sig_delta(reacts, prev_reacts), 'amber', 'react')
    b += '</div>'
    b += f'<div class="card" style="margin-top:14px"><h3>Daily activity</h3>{area_svg(daily)}</div>'
    b += '<div class="grid g2" style="margin-top:14px">'
    b += f'<div class="card"><h3>Busiest channels</h3>{hbars(chan_pairs, n)}</div>'
    b += f'<div class="card"><h3>Top contributors</h3>{hbars(top_pairs, n)}</div>'
    b += '</div>'
    b += '<div class="grid g2" style="margin-top:14px">'
    b += f'<div class="card"><h3>Activity heatmap</h3>{heatmap(hm, hmx)}</div>'
    pp_ = (pos / max(n,1)) * 100; np_ = (neg / max(n,1)) * 100; up = 100 - pp_ - np_
    b += donut_html('Sentiment', [('Positive', pos, '#10b981'), ('Neutral', neu, '#cbd5e1'),
                                  ('Negative', neg, '#f43f5e')], n, 'messages')
    b += '</div>'

    # ---- attention view: the negative-sentiment queue ----
    att = ('<div class="meta">Messages the sentiment classifier scored most negative — '
           'the flags worth a human read.</div>'
           '<div class="card"><h3>Most negative messages</h3>')
    if len(negs):
        for _, m in negs.iterrows():
            att += (f'<div class="msg"><div class="mh"><b>{E(m["author"])}</b> in #{E(m["channel"])}'
                    f'<span class="chip">{m["created_utc"]:%d %b %H:%M}</span></div>'
                    f'{E(str(m["content"])[:220])}</div>')
    else:
        att += '<div class="meta">No strongly negative messages in this window.</div>'
    att += '</div>'

    ag = desk_stats(G, start, latest)
    sf_d = safety_payload(df, start, latest)
    nc_d = newcomer_payload(CTX, start, latest)
    ch_d = channels_payload(df, start, latest)
    # Same-length window immediately before, so the comparison is like-for-like.
    prev = desk_stats(G, prev_start, start - timedelta(seconds=1))
    views = {
        'dashboard': b,
        'answers': render_answer_desk(ag, prev),
        'helpers': render_helpers(ag, f'{start:%d %b} → {latest:%d %b %Y}', prev),
        'coverage': render_coverage(ag),
        'attention': att,
        'safety': '', 'newcomers': '', 'channels': '',
    }
    tabs = [
        ('dashboard', 'Dashboard',    f'{n:,}',              False),
        ('answers',   'Answer Desk',  f'{ag["unanswered"]:,}', ag['unanswered'] > 0),
        ('helpers',   'Helpers',      f'{len(ag["helpers"]):,}', False),
        ('coverage',  'Coverage',     '',                    False),
        ('attention', 'Needs Attention', f'{len(negs):,}',   len(negs) > 0),
        ('safety',    'Safety',        f"{sf_d['sf_reports']:,}",  sf_d['sf_reports'] > 0),
        ('newcomers', 'Newcomers',     f"{nc_d['nc_arrived']:,}",  False),
        ('channels',  'Channels',      f"{ch_d['ch_total']:,}",    False),
    ]
    note = (f'ℏIntel · Hedera Discord<br>{start:%d %b %Y} → {latest:%d %b %Y}<br>'
            f'Generated {datetime.utcnow():%Y-%m-%d %H:%M} UTC')

    # DATA rides *inside* the encrypted region. It carries member names, queue text and
    # flagged messages, so shipping it in <head> the way the Reddit page does would hand
    # all of that to anyone who opens the file and defeat the password gate. A
    # type="application/json" block is inert when the gate injects it via innerHTML --
    # the head script reads its textContent once the content lands.
    payload = ('<script type="application/json" id="ddata">'
               + json.dumps(DATA, separators=(',', ':')).replace('</', '<\\/')
               + '</script>')
    b = payload + shell(tabs, views, note)

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
