# Bewerbungsoptimizer

Ein automatisierter Job-Tracker, der Stellenangebote von Indeed crawlt, in einer MongoDB speichert und mithilfe von KI (Claude API oder lokalem LM Studio) den Fit zwischen Stelle und Lebenslauf analysiert.

## Features

- **Crawling** – RSS-Feed-Fetcher und Playwright-Scraper für Indeed-Suchergebnisse
- **Speicherung** – MongoDB mit Duplikaterkennung via GUID/Content-Hash
- **KI-Analyse** – Abgleich von Stellenausschreibung und Lebenslauf (Claude API oder LM Studio)
- **Status-Tracking** – Bewerbungsstatus pro Stelle pflegen
- **Scheduler** – Zeitgesteuerter Crawl (konfigurierbar)
- **Benachrichtigungen** – Desktop-Notifications und optionale E-Mail-Digests

## Voraussetzungen

- Python 3.11+
- MongoDB (lokal oder via Docker)
- [LM Studio](https://lmstudio.ai/) (optional, für lokale KI-Analyse)
- Anthropic API Key (optional, für Claude-Analyse)

## Installation

```bash
pip install -r requirements.txt
playwright install chromium
```

## Konfiguration

Einstellungen in `config/settings.yaml` anpassen:

```yaml
database:
  uri: "mongodb://localhost:27017/jobtracker"

analyzer:
  backend: "lmstudio"       # oder "anthropic"
  lmstudio_url: "http://localhost:1234/v1"

cv:
  path: "data/persönliche_informationen/MeinCV.pdf"
```

Umgebungsvariablen (`.env`-Datei):

```env
MONGODB_URI=mongodb://localhost:27017/jobtracker
MONGODB_DB=jobtracker
ANTHROPIC_API_KEY=sk-...       # nur bei backend: anthropic
EMAIL_PASSWORD=...              # nur bei E-Mail-Benachrichtigungen
```

## Docker

```bash
docker-compose up -d
```

## Verwendung

```bash
# Einmaliger Crawl aller konfigurierten Suchprofile
python main.py run

# Stelle mit Playwright scrapen
python main.py scrape "https://de.indeed.com/jobs?q=..." --name "mein-profil"

# KI-Analyse einer Stelle (Job-ID aus DB, Textdatei oder stdin)
python main.py analyze <job-id-oder-datei> --cv data/persönliche_informationen/CV.pdf

# Bewerbungsstatus setzen
python main.py status <job-id> <status>

# Scheduler dauerhaft starten
python main.py scheduler
```

Suchprofile werden in `config/search_profiles.yaml` konfiguriert.
