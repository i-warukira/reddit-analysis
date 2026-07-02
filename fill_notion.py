"""
Push the ℏIntel Action Tracker rows into a Notion table.

Works with BOTH kinds of Notion tables:
  * a real database (inline or full-page)          -> creates pages
  * a simple table block (like the Sentiment log)  -> appends table rows,
    mapping columns by the table's own header row (Date, Source / Channel,
    Audience, Sentiment, Copy, Post Link, Raised by, Action needed, Status)

Rows come straight out of the built index.html, so Notion receives EXACTLY
what the dashboard's Tracker tab shows (same hybrid sentiment, same flags).
Existing Post Links are skipped — safe to re-run after every rebuild.

Setup (once):
  1. A MEMBER of the workspace that owns the page creates a connection at
     https://app.notion.com/developers (Access token) and connects it to the
     page (page ••• -> Connections). Guests cannot do this step.
  2. Save credentials in notion_config.json next to this script (git-ignored):
       { "token": "ntn_xxx", "database_id": "<paste the page or table link>" }

Run:  python -X utf8 fill_notion.py --dry-run      # preview + column mapping
      python -X utf8 fill_notion.py --raised-by henry
"""
import argparse, json, re, sys, time
import requests

API = 'https://api.notion.com/v1'
NV  = '2022-06-28'

FIELD_ALIASES = {
    'date':      ['date'],
    'source':    ['source', 'channel'],
    'audience':  ['audience'],
    'author':    ['author', 'user', 'account'],
    'sentiment': ['sentiment'],
    'copy':      ['copy', 'quote', 'text', 'message'],
    'link':      ['post link', 'link', 'url'],
    'raised_by': ['raised by', 'raised'],
    'action':    ['action needed', 'action'],
    'status':    ['status'],
    'why':       ['why', 'reason', 'flag'],
}

# ---------------------------------------------------------------- plumbing
def load_config(args):
    tok, db = args.token, args.db
    if not (tok and db):
        try:
            cfg = json.load(open('notion_config.json', encoding='utf-8'))
            tok = tok or cfg.get('token')
            db  = db  or cfg.get('database_id')
        except FileNotFoundError:
            pass
    if not tok or not db:
        sys.exit('Missing credentials. Create notion_config.json (see docstring) '
                 'or pass --token and --db.')
    ids = re.findall(r'[0-9a-fA-F]{32}', db.replace('-', ''))
    if not ids:
        sys.exit(f'Could not find a 32-char Notion id in: {db!r}')
    return tok, ids[-1]

def notion(tok, method, path, payload=None, ok404=False):
    r = requests.request(method, API + path, timeout=30,
                         headers={'Authorization': f'Bearer {tok}',
                                  'Notion-Version': NV, 'Content-Type': 'application/json'},
                         json=payload)
    if r.status_code == 429:
        time.sleep(float(r.headers.get('Retry-After', 2)))
        return notion(tok, method, path, payload, ok404)
    if r.status_code == 404 and ok404:
        return None
    if not r.ok:
        sys.exit(f'Notion API {r.status_code} on {path}: {r.text[:300]}')
    return r.json()

def block_children(tok, block_id):
    out, cursor = [], None
    while True:
        path = f'/blocks/{block_id}/children?page_size=100' + (f'&start_cursor={cursor}' if cursor else '')
        res = notion(tok, 'GET', path)
        out += res['results']
        if not res.get('has_more'): break
        cursor = res['next_cursor']
    return out

def tracker_rows():
    html = open('index.html', encoding='utf-8').read()
    data = json.loads(re.search(r'const DATA = (\{.*?\});\nconst \$', html, re.S).group(1))
    p = data['periods'][-1]
    rows = p.get('tracker', [])
    print(f"Tracker rows in latest period ({p['start']} -> {p['end']}): {len(rows)}")
    return rows

def row_values(r, args):
    return {'date': r.get('date', '')[:10], 'source': r.get('source', 'Reddit'),
            'audience': r.get('audience', ''), 'author': r.get('author', ''),
            'sentiment': r.get('sentiment', ''), 'copy': r.get('copy', ''),
            'link': ('https://www.reddit.com' + r['link']) if r.get('link') else '',
            'raised_by': args.raised_by, 'action': '', 'status': args.status,
            'why': r.get('why', '')}

# ---------------------------------------------------------------- target resolution
def resolve_target(tok, some_id):
    """Return ('database', id, schema) or ('table', id, block). Accepts a database id,
    a simple-table block id, or a page id (walks the page to find tables/databases)."""
    db = notion(tok, 'GET', f'/databases/{some_id}', ok404=True)
    if db: return 'database', some_id, db
    blk = notion(tok, 'GET', f'/blocks/{some_id}', ok404=True)
    if blk and blk['type'] == 'table':
        return 'table', some_id, blk
    if not blk:
        sys.exit(f'Notion: {some_id} not accessible. Is the connection added to the page?')
    # treat as page: collect inline databases and simple tables
    found = []
    for b in block_children(tok, some_id):
        if b['type'] == 'child_database':
            found.append(('database', b['id'], b['child_database'].get('title', '(untitled db)')))
        elif b['type'] == 'table':
            found.append(('table', b['id'], f"simple table ({b['table']['table_width']} cols)"))
    if not found:
        sys.exit('No table or database found on that page.')
    if len(found) > 1:
        print('Multiple tables found on the page:')
        for i, (k, fid, t) in enumerate(found): print(f'  [{i}] {k}: {t}  ({fid})')
        sys.exit('Re-run with --db <one of the ids above>.')
    kind, fid, title = found[0]
    print(f'Resolved {kind}: {title}')
    if kind == 'database':
        fid = fid.replace('-', '')
        return 'database', fid, notion(tok, 'GET', f'/databases/{fid}')
    return 'table', fid, notion(tok, 'GET', f'/blocks/{fid}')

# ---------------------------------------------------------------- database mode
def db_map_columns(schema):
    props = schema['properties']
    mapping = {}
    for field, aliases in FIELD_ALIASES.items():
        for name, meta in props.items():
            if any(a in name.lower() for a in aliases):
                mapping[field] = (name, meta['type']); break
    title_prop = next(n for n, m in props.items() if m['type'] == 'title')
    return mapping, title_prop

def db_existing_links(tok, db, link_prop):
    links, cursor = set(), None
    while True:
        payload = {'page_size': 100}
        if cursor: payload['start_cursor'] = cursor
        res = notion(tok, 'POST', f'/databases/{db}/query', payload)
        for page in res['results']:
            prop = page['properties'].get(link_prop, {})
            v = (prop.get('url') or
                 ''.join(t.get('plain_text', '') for t in prop.get('rich_text', [])))
            if v: links.add(v.strip())
        if not res.get('has_more'): break
        cursor = res['next_cursor']
    return links

def db_prop_value(ptype, text):
    text = str(text or '')
    if ptype == 'title':        return {'title': [{'text': {'content': text[:1800]}}]}
    if ptype == 'rich_text':    return {'rich_text': [{'text': {'content': text[:1800]}}]}
    if ptype == 'url':          return {'url': text or None}
    if ptype == 'select':       return {'select': {'name': text[:90]} if text else None}
    if ptype == 'status':       return {'status': {'name': text[:90]} if text else None}
    if ptype == 'multi_select': return {'multi_select': [{'name': text[:90]}] if text else []}
    if ptype == 'date':
        m = re.match(r'(\d{4}-\d{2}-\d{2})', text)
        return {'date': {'start': m.group(1)} if m else None}
    return None

def fill_database(tok, db, schema, rows, args):
    mapping, title_prop = db_map_columns(schema)
    print('Column mapping:', {k: v[0] for k, v in mapping.items()} or 'NONE')
    if 'link' not in mapping:
        sys.exit('No link/URL column found — add one (e.g. "Post Link").')
    have = db_existing_links(tok, db, mapping['link'][0])
    print(f'Already in Notion: {len(have)} links')
    created = skipped = 0
    for r in rows:
        vals = row_values(r, args)
        if vals['link'] and vals['link'] in have:
            skipped += 1; continue
        props = {}
        for field, (name, ptype) in mapping.items():
            if ptype == 'title': continue
            v = db_prop_value(ptype, vals[field])
            if v is not None: props[name] = v
        props[title_prop] = db_prop_value('title', vals['copy'] or vals['author'])
        if args.dry_run:
            print(f"  would create: {vals['date']} | {vals['sentiment']:8} | {vals['copy'][:60]}")
        else:
            notion(tok, 'POST', '/pages', {'parent': {'database_id': db}, 'properties': props})
            time.sleep(0.35)
        created += 1
    print(f'{"Would create" if args.dry_run else "Created"}: {created} · skipped: {skipped}')

# ---------------------------------------------------------------- simple-table mode
def cell_text(cell):
    return ''.join(t.get('plain_text', '') for t in cell).strip()

def fill_table(tok, table_id, block, rows, args):
    width = block['table']['table_width']
    trows = block_children(tok, table_id)
    if not trows:
        sys.exit('Table has no rows — add a header row first.')
    header = [cell_text(c) for c in trows[0]['table_row']['cells']]
    print('Table header:', header)
    # map our fields onto header column indexes
    colmap = {}
    for field, aliases in FIELD_ALIASES.items():
        for i, name in enumerate(header):
            if any(a in name.lower() for a in aliases):
                colmap[field] = i; break
    print('Column mapping:', {k: header[v] for k, v in colmap.items()} or 'NONE')
    if 'link' not in colmap:
        sys.exit('No "Post Link"-like column in the table header.')
    # existing links (text or hyperlink href) for dedupe
    have = set()
    for tr in trows[1:]:
        cells = tr['table_row']['cells']
        if colmap['link'] < len(cells):
            for t in cells[colmap['link']]:
                href = (t.get('text') or {}).get('link') or {}
                if href.get('url'): have.add(href['url'].strip())
            txt = cell_text(cells[colmap['link']])
            if txt.startswith('http'): have.add(txt)
    print(f'Already in table: {len(have)} links')
    def rt(text, url=None):
        if not text: return []
        seg = {'type': 'text', 'text': {'content': str(text)[:1800]}}
        if url: seg['text']['link'] = {'url': url}
        return [seg]
    created = skipped = 0
    batch = []
    for r in rows:
        vals = row_values(r, args)
        if vals['link'] and vals['link'] in have:
            skipped += 1; continue
        cells = [[] for _ in range(width)]
        for field, idx in colmap.items():
            if idx >= width: continue
            if field == 'link':
                cells[idx] = rt(vals['link'] or '', vals['link'] or None)
            else:
                cells[idx] = rt(vals[field])
        if args.dry_run:
            print(f"  would append: {vals['date']} | {vals['sentiment']:8} | {vals['copy'][:60]}")
        else:
            batch.append({'type': 'table_row', 'table_row': {'cells': cells}})
        created += 1
    if batch:
        for i in range(0, len(batch), 40):          # append in chunks
            notion(tok, 'PATCH', f'/blocks/{table_id}/children', {'children': batch[i:i+40]})
            time.sleep(0.4)
    print(f'{"Would append" if args.dry_run else "Appended"}: {created} · skipped: {skipped}')

# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--token'); ap.add_argument('--db')
    ap.add_argument('--raised-by', default='')
    ap.add_argument('--status', default='New')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()
    tok, some_id = load_config(args)
    kind, target_id, meta = resolve_target(tok, some_id)
    rows = tracker_rows()
    if kind == 'database':
        fill_database(tok, target_id, meta, rows, args)
    else:
        fill_table(tok, target_id, meta, rows, args)

if __name__ == '__main__':
    main()
