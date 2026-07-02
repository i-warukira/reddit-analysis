"""
Push the ℏIntel Action Tracker rows into a Notion database.

Reads the tracker rows straight out of the built index.html (so Notion gets
EXACTLY what the dashboard shows — same hybrid sentiment, same flags), then
creates one Notion page per row, skipping any post link already present in the
database (safe to re-run; never double-inserts).

Setup (once, ~2 minutes):
  1. https://www.notion.so/my-integrations  ->  New integration  ->  copy the
     "Internal Integration Secret" (starts with `ntn_` or `secret_`).
  2. Open your Notion database page -> ••• menu -> Connections ->
     "Connect to" -> pick your integration.
  3. Copy the database ID from the page URL:
     notion.so/<workspace>/<DATABASE_ID>?v=...   (32 hex chars, dashes optional)
  4. Save both in notion_config.json next to this script:
       { "token": "ntn_xxx", "database_id": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" }
     (git-ignored — never commit it)

Run:  python -X utf8 fill_notion.py                # latest reporting period
      python -X utf8 fill_notion.py --dry-run      # show what would be sent
      python -X utf8 fill_notion.py --raised-by henry
"""
import argparse, json, re, sys, time
import requests

API = 'https://api.notion.com/v1'
NV  = '2022-06-28'          # Notion-Version

# how our tracker fields map onto likely Notion column names (case-insensitive substring)
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
    return tok, re.sub(r'[^0-9a-fA-F]', '', db)[:32]

def tracker_rows():
    html = open('index.html', encoding='utf-8').read()
    data = json.loads(re.search(r'const DATA = (\{.*?\});\nconst \$', html, re.S).group(1))
    p = data['periods'][-1]
    rows = p.get('tracker', [])
    print(f"Tracker rows in latest period ({p['start']} -> {p['end']}): {len(rows)}")
    return rows

def notion(tok, method, path, payload=None):
    r = requests.request(method, API + path, timeout=30,
                         headers={'Authorization': f'Bearer {tok}',
                                  'Notion-Version': NV, 'Content-Type': 'application/json'},
                         json=payload)
    if r.status_code == 429:                      # rate-limited: wait and retry once
        time.sleep(float(r.headers.get('Retry-After', 2)))
        return notion(tok, method, path, payload)
    if not r.ok:
        sys.exit(f'Notion API {r.status_code}: {r.text[:300]}')
    return r.json()

def map_columns(schema):
    """Match our fields to the database's real property names + types."""
    props = schema['properties']
    mapping = {}
    for field, aliases in FIELD_ALIASES.items():
        for name, meta in props.items():
            if any(a in name.lower() for a in aliases):
                mapping[field] = (name, meta['type'])
                break
    title_prop = next(n for n, m in props.items() if m['type'] == 'title')
    return mapping, title_prop

def existing_links(tok, db, link_prop):
    """All Post Link values already in the DB (for dedupe)."""
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

def prop_value(ptype, field, text):
    """Build a Notion property payload for the column's actual type."""
    text = str(text or '')
    if ptype == 'title':      return {'title': [{'text': {'content': text[:1800]}}]}
    if ptype == 'rich_text':  return {'rich_text': [{'text': {'content': text[:1800]}}]}
    if ptype == 'url':        return {'url': text or None}
    if ptype == 'select':     return {'select': {'name': text[:90]} if text else None}
    if ptype == 'status':     return {'status': {'name': text[:90]} if text else None}
    if ptype == 'multi_select': return {'multi_select': [{'name': text[:90]}] if text else []}
    if ptype == 'date':
        m = re.match(r'(\d{4}-\d{2}-\d{2})', text)
        return {'date': {'start': m.group(1)} if m else None}
    return None                                    # people/relation/etc: skip

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--token'); ap.add_argument('--db')
    ap.add_argument('--raised-by', default='')
    ap.add_argument('--status', default='New')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()
    tok, db = load_config(args)

    schema = notion(tok, 'GET', f'/databases/{db}')
    mapping, title_prop = map_columns(schema)
    print('Column mapping:', {k: v[0] for k, v in mapping.items()} or 'NONE')
    if 'link' not in mapping:
        sys.exit('No link/URL column found in the database — add one (e.g. "Post Link").')

    rows = tracker_rows()
    have = existing_links(tok, db, mapping['link'][0])
    print(f'Already in Notion: {len(have)} links')

    created = skipped = 0
    for r in rows:
        url = ('https://www.reddit.com' + r['link']) if r.get('link') else ''
        if url and url in have:
            skipped += 1; continue
        props = {}
        values = {'date': r.get('date', '')[:10], 'source': r.get('source', 'Reddit'),
                  'audience': r.get('audience', ''), 'author': r.get('author', ''),
                  'sentiment': r.get('sentiment', ''), 'copy': r.get('copy', ''),
                  'link': url, 'raised_by': args.raised_by, 'action': '',
                  'status': args.status, 'why': r.get('why', '')}
        for field, (name, ptype) in mapping.items():
            if ptype == 'title': continue          # title handled below
            v = prop_value(ptype, field, values[field])
            if v is not None: props[name] = v
        # title column gets the copy (or author) so rows are readable in Notion
        props[title_prop] = prop_value('title', 'copy', values['copy'] or values['author'])
        if args.dry_run:
            print(f"  would create: {values['date']} | {values['sentiment']:8} | {values['copy'][:60]}")
        else:
            notion(tok, 'POST', '/pages', {'parent': {'database_id': db}, 'properties': props})
            time.sleep(0.35)                       # stay under Notion's 3 req/s
        created += 1
    print(f'{"Would create" if args.dry_run else "Created"}: {created} · skipped (already present): {skipped}')

if __name__ == '__main__':
    main()
