# Reddit Analytics Suite

A full-featured Reddit scraping toolkit with:

- CLI scraping workflows for subreddits and users
- Media and comment collection
- Streamlit dashboard
- FastAPI REST API
- Plugin-based post-processing
- Search, analytics, scheduling, and export utilities

The project is designed to run without Reddit API keys for core scraping workflows.

## Features

- Scrape posts from subreddits or users
- Optional comment scraping and media download
- Multiple scrape modes: `full`, `history`, `monitor`
- Dry-run mode for safe validation
- Plugin system for post/comment enrichment
- Dashboard for exploration and analysis
- REST API for BI and external integrations
- SQLite-backed storage with maintenance commands
- Parquet export for analytics pipelines

## Project Structure

```text
reddit-universal-scraper/
├── main.py
├── config.py
├── requirements.txt
├── analytics/
├── alerts/
├── api/
├── dashboard/
├── export/
├── plugins/
├── scheduler/
├── scraper/
├── search/
└── data/
```

## Requirements

- Python 3.8+
- `ffmpeg` (optional but recommended for best Reddit video handling)

Install dependencies:

```bash
pip install -r requirements.txt
```

Install `ffmpeg` (optional):

```bash
# Windows (Chocolatey)
choco install ffmpeg

# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt install ffmpeg
```

## Quick Start

Run a basic scrape:

```bash
python main.py python --mode full --limit 100
```

Launch the dashboard:

```bash
python main.py --dashboard
# http://localhost:8501
```

Launch the API:

```bash
python main.py --api
# docs: http://localhost:8000/docs
```

## CLI Usage

General form:

```bash
python main.py [target] [options]
```

### Scraping

```bash
# Full scrape (posts + media + comments)
python main.py delhi --mode full --limit 100

# History mode (fast, no media/comments)
python main.py delhi --mode history --limit 500

# Continuous monitor mode
python main.py delhi --mode monitor

# Scrape user posts
python main.py spez --user --mode full --limit 50

# Skip media or comments
python main.py delhi --no-media --limit 200
python main.py delhi --no-comments --limit 200
```

### Dry Run

```bash
python main.py python --mode full --limit 50 --dry-run
```

### Plugins

```bash
# Show available plugins
python main.py --list-plugins

# Run scrape with plugins enabled
python main.py python --mode full --plugins
```

Built-in plugins include:

- `sentiment_tagger`
- `deduplicator`
- `keyword_extractor`
- `ai_reply_drafter`

### Search

```bash
python main.py --search "credit card"
python main.py --search "credit card" --min-score 100
python main.py --search "credit card" --author some_user
```

### Analytics

```bash
python main.py --analyze delhi --sentiment
python main.py --analyze delhi --keywords
```

### Scheduling

```bash
python main.py --schedule delhi --every 60
python main.py --schedule delhi --every 30 --mode full --limit 50
```

### Maintenance and Export

```bash
python main.py --job-history
python main.py --backup
python main.py --vacuum
python main.py --export-parquet python
```

### AI Reply Backfill

```bash
python main.py --backfill-replies python
```

## Dashboard

Run:

```bash
python main.py --dashboard
```

The dashboard supports subreddit/user selection and includes tabs such as:

- Overview
- Analytics
- Search
- Comments
- Scraper
- Job History
- Integrations

## REST API

Run:

```bash
python main.py --api
```

Base URL: `http://localhost:8000`

Useful endpoints:

- `GET /`
- `GET /health`
- `GET /info`
- `GET /posts`
- `GET /posts/{post_id}`
- `GET /comments`
- `GET /subreddits`
- `GET /subreddits/{subreddit}/stats`
- `GET /jobs`
- `GET /jobs/stats`
- `GET /query?sql=SELECT...`
- `GET /grafana/search`
- `POST /grafana/query`

Interactive docs:

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Data Output

Scraped data is stored under `data/` by target:

- `data/r_<subreddit>/posts.csv`
- `data/r_<subreddit>/comments.csv`
- `data/r_<subreddit>/media/images/`
- `data/r_<subreddit>/media/videos/`
- `data/u_<username>/...`

SQLite database path:

- `data/reddit_scraper.db`

## Docker

Build image:

```bash
docker build -t reddit-scraper .
```

Run a scrape:

```bash
docker run -v ./data:/app/data reddit-scraper python --limit 100
```

Run API + dashboard with Compose:

```bash
docker-compose up -d
```

Default service ports:

- Dashboard: `8501`
- API: `8000`

## Environment Variables

Optional notification and AI variables:

```bash
DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."
TELEGRAM_BOT_TOKEN="..."
TELEGRAM_CHAT_ID="..."
GEMINI_API_KEY="..."
GEMINI_MODEL="gemini-1.5-flash"
AI_REPLY_MAX_COMMENTS="25"
```

## Notes

- Use `--list-plugins` to verify plugin availability.
- For best video results, install `ffmpeg`.
- Existing `docs/` files provide additional integration examples.

## License

MIT
