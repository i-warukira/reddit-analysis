"""
ℏIntel shared sentiment classifier (hybrid VADER).

Same rules the Reddit dashboard uses, packaged for reuse by other sources
(Discord, X, ...): VADER + crypto/community domain lexicon + negation-aware
phrase rules + question softener + finance-idiom neutralization.

classify(title, body)  -> (label, score)   # Reddit-style: headline + body
classify_text(text)    -> (label, score)   # single-text sources (chat messages)
"""
import re

try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    _va = SentimentIntensityAnalyzer()
    AVAILABLE = True
except Exception:                                      # pragma: no cover
    _va = None
    AVAILABLE = False

DOMAIN = {'cooked': -2.2, 'rug': -2.5, 'rugpull': -3.0, 'rekt': -2.5, 'dump': -1.6,
          'dumping': -1.9, 'dumped': -1.6, 'bagholder': -2.0, 'sinking': -1.8, 'sink': -1.4,
          'tanked': -2.0, 'tanking': -2.0, 'bleeding': -1.8, 'crashing': -2.0, 'drained': -2.4,
          'divest': -1.8, 'divests': -1.8, 'divesting': -1.8, 'delist': -2.0, 'delisting': -2.0,
          'stuck': -1.3, 'stagnant': -1.5, 'vaporware': -2.4, 'abandoned': -1.9,
          'shitcoin': -2.6, 'ponzi': -2.8, 'irrelevant': -1.6}
if AVAILABLE:
    _va.lexicon.update(DOMAIN)

# headline-level claims — apply to titles only (body mentions are often transient/quoted)
NEG_TITLE = re.compile(
    r'divests? from|continues? to fail|keeps? failing|'
    r'anything left to look forward|stuck token|token .{0,14}stuck|sad truth', re.I)
# anywhere rules, negation-aware
NEG_ANY = re.compile(
    r'lost project|sadly .{0,32}(sink|drop|dump|fall)|got (scammed|drained)|'
    r'(?<!nor )(?<!not )is (this|it) a scam\?|(?<!not a )scam post', re.I)
QSTART = re.compile(r'^(how|what|which|where|when|who)\b', re.I)
IDIOMS = [(re.compile(r'war\s+chest', re.I), 'cash reserve')]


def _clean(s):
    s = str(s or '')
    for pat, repl in IDIOMS:
        s = pat.sub(repl, s)
    return s


def classify(title, body):
    """Reddit-style: title-weighted blend; negative = min(title, body) <= -0.5."""
    t, b = _clean(title), _clean(body if isinstance(body, str) else '')
    txt = (t + ' ' + b)[:900]
    if NEG_TITLE.search(t) or NEG_ANY.search(txt):
        return 'negative', -0.99
    if not AVAILABLE:
        return 'neutral', 0.0
    ct = _va.polarity_scores(t[:500])['compound']
    cb = _va.polarity_scores(b[:600])['compound'] if b.strip() else ct
    mn, blend = min(ct, cb), (2 * ct + cb) / 3
    if QSTART.match(t.strip()) and not any(w in txt.lower() for w in DOMAIN):
        mn = max(mn, -0.4)
    if mn <= -0.5:   return 'negative', round(mn, 3)
    if blend >= 0.5: return 'positive', round(blend, 3)
    return 'neutral', round(blend, 3)


def classify_text(text):
    """Single-text sources (chat messages): one compound, phrase rules on the whole text."""
    t = _clean(text)[:900]
    if NEG_TITLE.search(t) or NEG_ANY.search(t):
        return 'negative', -0.99
    if not AVAILABLE:
        return 'neutral', 0.0
    c = _va.polarity_scores(t[:600])['compound']
    if QSTART.match(t.strip()) and not any(w in t.lower() for w in DOMAIN):
        c = max(c, -0.4)
    if c <= -0.5:   return 'negative', round(c, 3)
    if c >= 0.5:    return 'positive', round(c, 3)
    return 'neutral', round(c, 3)
