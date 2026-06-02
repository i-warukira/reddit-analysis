# Cowork Prompt — Hedera Reddit Community Intelligence Report

Copy everything inside the code block below and give it to Cowork.
Change only the two values in **CONFIG** (subreddit and date range) if you want a
different community or period. Everything else must stay as-is to reproduce the
report byte-for-byte in the same format as
`REPORT_2026-05-12_to_2026-06-01_FINAL.txt`.

---

```
You are producing a "Community Intelligence Tracker" report for a Reddit
subreddit, in the EXACT format of the existing file
C:\Users\Administrator\Music\reddit-universal-scraper\REPORT_2026-05-12_to_2026-06-01_FINAL.txt

Work in the repo: C:\Users\Administrator\Music\reddit-universal-scraper
Two authoritative scripts already exist there — use them as the source of truth:
  - scrape_may12_jun1.py   (fetches posts+comments, appends to the CSVs)
  - report_may12_jun1.py   (reads the CSVs, prints the formatted report)
Do NOT redesign the report. Reproduce it from the first character to the last,
including the 7-section overview, the 5 design principles, Sections 1–12, TOP
PERFORMING POSTS, AREAS FOR IMPROVEMENT, SUMMARY SCORECARD, and the EVIDENCE
APPENDIX. Match the labels, spacing, and "======" separators exactly.

==================== CONFIG (the only things you may change) ====================
SUBREDDIT  = Hedera
PERIOD     = 2026-05-12 to 2026-06-01   (inclusive; UTC)
================================================================================

FOLLOW THESE STEPS PRECISELY. ACCURACY IS CRITICAL — never invent numbers; every
figure must come from the fetched data.

STEP 1 — DATA SOURCE (important)
- Live Reddit JSON (old.reddit.com / www.reddit.com) is IP-BLOCKED on this host
  (returns HTTP 403 HTML). Do NOT rely on it.
- Use the Arctic-Shift archive instead (full Reddit objects, reliable):
    Base: https://arctic-shift.photon-reddit.com
    Posts:    GET /api/posts/search?subreddit=<SUB>&after=<ISO>&before=<ISO>&limit=100&sort=asc
    Comments: GET /api/comments/search?subreddit=<SUB>&after=<ISO>&before=<ISO>&limit=100&sort=asc
  Use User-Agent: "reddit-research/1.0". Paginate by advancing `after` to
  (last item's created_utc + 1 second) until a page returns < 100 rows.
  `before` is exclusive — to cover through the last day, set it to the day AFTER
  PERIOD end at 00:00:00 (e.g. for a period ending 2026-06-01, use 2026-06-02T00:00:00).

STEP 2 — BUILD THE CSV ROWS (match the existing schema EXACTLY)
posts.csv columns:
  id,title,author,created_utc,permalink,url,score,upvote_ratio,num_comments,
  num_crossposts,selftext,post_type,is_nsfw,is_spoiler,flair,total_awards,
  has_media,media_downloaded,source,keywords,sentiment_score,sentiment_label
comments.csv columns:
  post_permalink,comment_id,parent_id,author,body,score,created_utc,depth,
  is_submitter,post_id,post_title,post_selftext,post_author

- post_type: 'video' if is_video; else 'gallery' if is_gallery; else 'image' if
  the url ends in .jpg/.jpeg/.png/.gif/.webp or contains 'i.redd.it'; else 'text'
  if is_self; else 'link'.
- sentiment_score / sentiment_label: use the repo's analytics.sentiment.analyze_sentiment
  on (title + ' ' + selftext) for posts, and on body for comments.
- keywords: top-5 from analytics.sentiment.extract_keywords(title+selftext).
- source: 'Arctic-Shift'.
- comment depth: 0 if parent_id starts with 't3_'; else 1 + depth(parent comment).
- comment post_id: the link_id with the 't3_' prefix stripped.

STEP 3 — CRITICAL DATE-FORMAT BUG (do not skip)
The existing CSVs store created_utc with a SPACE separator ("2026-05-12 01:12:51").
If you write new rows with a 'T' separator, pandas' mixed-format parser silently
turns them into NaT and they vanish from the report (you'll get "Posts analyzed: 0").
=> Write created_utc as "YYYY-MM-DD HH:MM:SS" (space, no 'T') for BOTH posts and
   comments, OR normalize the whole column after appending. Verify after writing
   that the number of posts in the period is > 0.

STEP 4 — APPEND TO THE EXISTING CSVs (keep full history)
Append the new rows to data/r_Hedera/posts.csv and data/r_Hedera/comments.csv,
de-duplicating by post id / comment_id. The full history MUST stay in the file —
the report's "new contributor" and growth math compares the period against all
prior data in the same CSVs.

STEP 5 — GENERATE THE REPORT
Run report_may12_jun1.py (set its period_start, period_end, period_label,
num_days, and OUTPUT_FILE to match CONFIG). num_days = inclusive day count of the
period (e.g. May 12–Jun 1 = 21). Output filename convention:
REPORT_<start>_to_<end>_FINAL.txt in the repo root.
Run with UTF-8: `python -X utf8 report_may12_jun1.py` (the report contains em-dashes
and arrows that crash the default Windows cp1252 console).

STEP 6 — HONEST METRICS (already built into report_may12_jun1.py — keep them)
- Growth is an EQUAL-LENGTH window comparison (prior N-day window vs the period),
  labeled "Growth vs prior <N>d window %". Not a sloppy 30-vs-21-day "MoM".
- "First-time" contributors are labeled "New to tracker (since <earliest data date>)"
  because they're only new relative to the data we hold, not the whole subreddit.
- Soft/keyword metrics (scam, FUD, impersonation, misinformation, compliance,
  feature-request, bug-report, AI Studio, hackathon, support-resolved) are PROXIES,
  not verified mod actions. Each is computed by a tightened, word-bounded regex and
  recorded in the EVIDENCE APPENDIX with date, user, post/comment, reddit link, and
  the matched text snippet so every count is auditable. Keep the appendix.
- Regexes must be word-bounded to avoid false positives (e.g. impersonation must
  NOT match "pretending"; compliance must NOT match the bare substrings "sec"/"ban").

STEP 7 — VERIFY BEFORE DECLARING DONE
- "Posts analyzed" and "Comments analyzed" at the top are both > 0 and match the
  fetched counts.
- Spot-check 3 figures against the raw data (e.g. top post upvotes, a keyword-hit
  count vs its appendix rows).
- Confirm the output file opens with the "===" header and ends with "END OF REPORT",
  and that the EVIDENCE APPENDIX lists source rows for each soft metric.
- Report the data-source caveat to the user: scores/ratios are the Arctic-Shift
  archive snapshot (essentially final for posts >1 day old), and the mod-dashboard
  fields remain "(manual input)".

Deliver: the path to the finished REPORT_<start>_to_<end>_FINAL.txt plus a short
summary of headline numbers (posts, comments, posts/day, upvote ratio, unique
contributors, top post, risk level, support resolution).
```
