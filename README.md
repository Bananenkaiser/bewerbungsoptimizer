# Bewerbungsoptimizer

> A personal job application assistant that crawls job postings, analyzes CV fit using LLMs, and tracks the entire application process — all through a self-hosted web dashboard.

---

## What it does

Job hunting generates a lot of noise. This tool cuts through it:

1. **Crawls** Indeed job postings via RSS feeds and a Playwright scraper
2. **Analyzes** each posting against your CV using an LLM — producing a fit score (0–100 %), level assessment, strengths/gaps, and concrete CV improvement suggestions
3. **Tracks** the full application lifecycle: applied, response received, interview, rejection
4. **Maintains a candidate profile** — one-time CV analysis produces a compact profile (~300 tokens) that replaces the raw PDF in every subsequent analysis (~75 % token reduction)
5. **Integrates GitHub** — scans all public repositories, extracts tools and skills from READMEs, and merges them into the candidate profile

---

## Tech stack

| Layer | Technology |
|---|---|
| Backend / CLI | Python 3.12, `asyncio` |
| Web UI | Streamlit |
| Database | MongoDB (`pymongo`) |
| LLM integration | Anthropic Claude API (`claude-opus-4-6`) · OpenAI-compatible (LM Studio) |
| Web scraping | Playwright (Chromium), `feedparser`, `httpx` |
| PDF parsing | `pypdf` |
| Containerization | Docker, Docker Compose |
| Scheduling | APScheduler |
| Notifications | `plyer` (desktop), SMTP (email digest) |

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                  Streamlit Dashboard                 │
│  Overview · Job List · Analysis · Profile Manager   │
└────────────────────┬────────────────────────────────┘
                     │
        ┌────────────▼────────────┐
        │        MongoDB          │
        │  jobs · search_runs     │
        └──────┬──────────────────┘
               │
    ┌──────────┴──────────┐
    │                     │
┌───▼────────┐    ┌───────▼──────────────────┐
│  Fetcher   │    │      LLM Analyzer         │
│  RSS Feed  │    │  Anthropic Claude API     │
│  Playwright│    │  or local LM Studio       │
└────────────┘    │  (OpenAI-compatible)      │
                  └───────────────────────────┘
```

**Key design decisions:**
- **Dual LLM backend** — switches between cloud (Anthropic) and local (LM Studio) via a single config flag; falls back automatically if the local model is unreachable
- **Candidate profile pattern** — CV is analyzed once; the resulting Markdown profile replaces the raw PDF in all subsequent LLM calls, drastically reducing latency and cost
- **Schema-less extra fields** — core job data uses a typed dataclass; analysis results (full text, model name, token counts, levels) are stored as extra MongoDB fields without schema migration
- **Stateless dashboard** — all state lives in MongoDB and `st.session_state`; the Streamlit process can be restarted at any time without data loss

---

## Features

**Analysis**
- Fit score with reasoning (0–100 %)
- Candidate level vs. required level assessment (Junior / Mid / Senior / Lead)
- Strengths, gaps, and concrete CV improvement suggestions per job posting
- Extracts job title and company automatically from the posting text

**Candidate profile**
- One-time LLM analysis of CV + personal notes (`me.md`)
- Granular skill extraction: programming languages, ML/AI frameworks, databases, tools
- GitHub integration: fetches READMEs from all public repos, extracts technologies via LLM
- Editable in the dashboard; profile is used automatically in all analyses

**Application tracking**
- Status pipeline: `new → applied → interview → offer / rejected / withdrawn`
- Tracks application date, response date, interview invitations, rejection notes
- Statistics overview: scores, response rates, status distribution

**Infrastructure**
- Fully containerized with Docker Compose (app + MongoDB)
- Configurable crawl schedule (time window, weekdays only, interval)
- Rate limiting on scraper requests (randomized delays)

---

## Getting started

**Requirements:** Docker, or Python 3.12 + MongoDB

```bash
# Clone and configure
cp .env.example .env
# Edit .env: set ANTHROPIC_API_KEY or point LM_STUDIO_URL to your local instance

cp config/settings.yaml.example config/settings.yaml
# Edit config/settings.yaml: set lmstudio_url and cv.path

# Start everything
docker compose up -d

# Dashboard
open http://localhost:8501
```

**Local development:**

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium

MONGODB_URI=mongodb://localhost:27017/jobtracker \
  python -m streamlit run dashboard.py
```

---

## Configuration

`config/settings.yaml`:

```yaml
analyzer:
  backend: "lmstudio"          # "anthropic" or "lmstudio"
  lmstudio_url: "http://192.168.1.x:1234/v1"

cv:
  path: "data/cv.pdf"
  profile_path: "data/kandidatenprofil.md"   # auto-generated

scheduler:
  crawl_interval_hours: 2
  crawl_window_start: 8
  crawl_window_end: 18
  crawl_weekdays_only: true
```

---

## Project structure

```
├── src/
│   ├── analyzer/job_matcher.py    # LLM analysis, profile creation, CV improvement
│   ├── dashboard/streamlit_app.py # Full Streamlit UI
│   ├── fetcher/                   # RSS + Playwright scrapers
│   ├── storage/                   # MongoDB models and connection
│   ├── notifier/                  # Desktop + email notifications
│   └── scheduler/                 # APScheduler jobs
├── config/
│   ├── settings.yaml
│   └── search_profiles.yaml
├── main.py                        # CLI entrypoint
├── dashboard.py                   # Streamlit entrypoint
├── Dockerfile
└── docker-compose.yml
```
