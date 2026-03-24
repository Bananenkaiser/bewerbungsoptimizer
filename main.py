"""Indeed Job Tracker – Einstiegspunkt"""

import argparse
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()

from src.storage.database import init_db


def load_config(config_path: str = "config/settings.yaml") -> dict:
    with open(config_path) as f:
        return yaml.safe_load(f)


def _setup_logging(config: dict) -> None:
    log_cfg = config.get("logging", {})
    level = getattr(logging, log_cfg.get("level", "INFO").upper(), logging.INFO)
    log_file = log_cfg.get("file", "data/jobtracker.log")
    Path(log_file).parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-8s %(name)s – %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
    )


def cmd_run(config: dict) -> None:
    """Einmaliger Crawl aller Suchprofile."""
    from pymongo.errors import DuplicateKeyError

    from src.fetcher.rss_fetcher import fetch_all_profiles
    from src.storage.database import JOBS_COLLECTION, SEARCH_RUNS_COLLECTION, get_session
    from src.storage.models import Job, SearchRun

    profiles_path = "config/search_profiles.yaml"
    with open(profiles_path) as f:
        profiles_cfg = yaml.safe_load(f)
    profiles: list[dict] = profiles_cfg.get("profiles", [])

    if not profiles:
        print("Keine Suchprofile in config/search_profiles.yaml konfiguriert.")
        return

    rate_cfg = config.get("rate_limiting", {})
    min_delay = float(rate_cfg.get("min_delay_seconds", 5))
    max_delay = float(rate_cfg.get("max_delay_seconds", 15))

    print(f"Starte Crawl für {len(profiles)} Suchprofil(e) ...")
    raw_jobs = fetch_all_profiles(profiles, min_delay=min_delay, max_delay=max_delay)

    total_new = 0
    now = datetime.now(timezone.utc)

    with get_session() as db:
        jobs_col = db[JOBS_COLLECTION]
        runs_col = db[SEARCH_RUNS_COLLECTION]

        # Einen SearchRun pro Profil anlegen
        profile_names = [p.get("name", "unknown") for p in profiles]
        run_id_map: dict[str, object] = {}
        run_counts: dict[str, dict] = {}
        for name in profile_names:
            run = SearchRun(started_at=now, search_profile=name)
            result = runs_col.insert_one(run.to_document())
            run_id_map[name] = result.inserted_id
            run_counts[name] = {"jobs_found": 0, "jobs_new": 0}

        for raw in raw_jobs:
            job = Job(
                guid=raw.guid,
                content_hash=raw.content_hash,
                title=raw.title,
                company=raw.company,
                location=raw.location,
                url=raw.url,
                description=raw.description,
                published_at=raw.published_at,
                fetched_at=datetime.now(timezone.utc),
                search_profile=raw.search_profile,
            )
            try:
                jobs_col.insert_one(job.to_document())
                total_new += 1
                if raw.search_profile in run_counts:
                    run_counts[raw.search_profile]["jobs_new"] += 1
            except DuplicateKeyError:
                pass  # GUID-Duplikat – überspringen

            if raw.search_profile in run_counts:
                run_counts[raw.search_profile]["jobs_found"] += 1

        # SearchRun-Dokumente mit finalen Zählern aktualisieren
        finished = datetime.now(timezone.utc)
        for name, oid in run_id_map.items():
            runs_col.update_one(
                {"_id": oid},
                {"$set": {
                    "finished_at": finished,
                    "jobs_found": run_counts[name]["jobs_found"],
                    "jobs_new": run_counts[name]["jobs_new"],
                }},
            )

    print(f"Fertig: {len(raw_jobs)} gefunden, {total_new} neu gespeichert.")


def cmd_dashboard(config: dict) -> None:
    """CLI-Dashboard anzeigen."""
    print("Dashboard noch nicht implementiert (Phase 7).")


def cmd_scheduler(config: dict) -> None:
    """Dauerhaft mit Scheduler laufen."""
    print("Scheduler noch nicht implementiert (Phase 6).")


def cmd_status(config: dict, job_id: str, new_status: str) -> None:
    """Bewerbungsstatus eines Jobs setzen."""
    from bson import ObjectId
    from bson.errors import InvalidId

    from src.storage.database import JOBS_COLLECTION, get_session
    from src.storage.models import JobStatus

    valid = [s.value for s in JobStatus]
    if new_status not in valid:
        print(f"Ungültiger Status '{new_status}'. Erlaubt: {', '.join(valid)}")
        sys.exit(1)

    try:
        oid = ObjectId(job_id)
    except InvalidId:
        print(f"Ungültige Job-ID '{job_id}'. Bitte MongoDB ObjectId verwenden (24 hex Zeichen).")
        sys.exit(1)

    with get_session() as db:
        job_doc = db[JOBS_COLLECTION].find_one({"_id": oid})
        if job_doc is None:
            print(f"Job mit ID {job_id} nicht gefunden.")
            sys.exit(1)
        db[JOBS_COLLECTION].update_one({"_id": oid}, {"$set": {"status": new_status}})
        print(f"Job {job_id} ({job_doc['title']}) → Status: {new_status}")


def cmd_analyze(config: dict, job_source: str, cv_path_str: str | None) -> None:
    """Analysiert Passung zwischen einer Stelle und dem eigenen Lebenslauf."""
    from src.analyzer.job_matcher import analyze_job

    # CV-Pfad bestimmen
    cv_str = cv_path_str or config.get("cv", {}).get("path", "")
    if not cv_str:
        print(
            "Kein Lebenslauf angegeben. Bitte --cv <pfad> angeben oder "
            "'cv.path' in config/settings.yaml setzen."
        )
        sys.exit(1)
    cv_path = Path(cv_str)
    if not cv_path.exists():
        print(f"Lebenslauf nicht gefunden: {cv_path}")
        sys.exit(1)

    # me.md laden (optional)
    me_str = config.get("cv", {}).get("me_path", "")
    me_path = Path(me_str) if me_str else None

    # Stelleninhalt laden
    job_title = ""
    company = ""

    import re as _re
    _OID_RE = _re.compile(r'^[0-9a-f]{24}$', _re.I)

    if _OID_RE.match(job_source):
        # MongoDB ObjectId aus Datenbank
        from bson import ObjectId

        from src.storage.database import JOBS_COLLECTION, get_session

        oid = ObjectId(job_source)
        with get_session() as db:
            job_doc = db[JOBS_COLLECTION].find_one({"_id": oid})
            if job_doc is None:
                print(f"Job mit ID {job_source} nicht gefunden.")
                sys.exit(1)
            job_description = (
                f"Titel: {job_doc['title']}\nUnternehmen: {job_doc['company']}\n\n"
                f"{job_doc.get('description', '')}"
            )
            job_title = job_doc["title"]
            company = job_doc["company"]
        print(f"Analysiere: {job_title} @ {company} (ID {job_source})")
    else:
        p = Path(job_source)
        if p.exists():
            job_description = p.read_text(encoding="utf-8", errors="replace")
            print(f"Analysiere Stellenausschreibung aus: {p}")
        elif job_source == "-":
            print("Stellenausschreibung von stdin lesen (Eingabe mit Strg+D beenden):")
            job_description = sys.stdin.read()
        else:
            print(f"Datei nicht gefunden: {job_source}")
            sys.exit(1)

    print(f"Lebenslauf: {cv_path}")
    if me_path and me_path.exists():
        print(f"Persönliche Infos: {me_path}")
    print("─" * 60)

    result = analyze_job(
        job_description=job_description,
        cv_path=cv_path,
        me_path=me_path,
        job_title=job_title,
        company=company,
        stream_output=True,
        config=config,
    )

    print("─" * 60)
    if result.fit_score >= 0:
        bar = "█" * (result.fit_score // 5) + "░" * (20 - result.fit_score // 5)
        print(f"\nPassungsgrad: {result.fit_score}%  [{bar}]")
    total_tokens = result.input_tokens + result.output_tokens
    print(
        f"Tokens: {total_tokens:,} gesamt  "
        f"(Input: {result.input_tokens:,} | Output: {result.output_tokens:,})"
    )
    if result.model_used:
        print(f"Modell:  {result.model_used}")

    # Markdown-Auswertung speichern
    output_dir = Path("data/jobs/auswertung")
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    if job_title and company:
        slug = f"{job_title}_{company}".lower()
    elif _OID_RE.match(job_source):
        slug = f"job_{job_source}"
    else:
        slug = Path(job_source).stem
    # Dateiname bereinigen
    import re
    slug = re.sub(r"[^\w\-]", "_", slug)[:60]
    md_path = output_dir / f"{timestamp}_{slug}.md"

    score_line = f"**Passungsgrad: {result.fit_score}%**" if result.fit_score >= 0 else ""
    header = f"# Auswertung: {job_title or job_source}"
    if company:
        header += f" @ {company}"
    md_content = (
        f"{header}\n\n"
        f"*Analysiert am {datetime.now().strftime('%d.%m.%Y %H:%M')}*"
        f"  |  Lebenslauf: `{cv_path.name}`\n\n"
        f"{score_line}\n\n"
        "---\n\n"
        f"{result.full_analysis}\n"
    )
    md_path.write_text(md_content, encoding="utf-8")
    print(f"\nAuswertung gespeichert: {md_path}")


def cmd_scrape(config: dict, url: str, profile_name: str) -> None:
    """Scrapt eine Indeed-Suchergebnis-URL mit Playwright und speichert die Stellen."""
    from pymongo.errors import DuplicateKeyError

    from src.fetcher.scraper import scrape_search_url
    from src.storage.database import JOBS_COLLECTION, get_session
    from src.storage.models import Job

    print(f"Starte Scraping: {url}")
    raw_jobs = scrape_search_url(url, profile_name=profile_name)

    if not raw_jobs:
        print("Keine Stellen gefunden.")
        return

    total_new = 0
    with get_session() as db:
        jobs_col = db[JOBS_COLLECTION]
        for raw in raw_jobs:
            job = Job(
                guid=raw.guid,
                content_hash=raw.content_hash,
                title=raw.title,
                company=raw.company,
                location=raw.location,
                url=raw.url,
                description=raw.description,
                published_at=raw.published_at,
                fetched_at=datetime.now(timezone.utc),
                search_profile=raw.search_profile,
            )
            try:
                jobs_col.insert_one(job.to_document())
                total_new += 1
            except DuplicateKeyError:
                pass

    print(f"Fertig: {len(raw_jobs)} gefunden, {total_new} neu gespeichert.")


def cmd_export(config: dict, fmt: str) -> None:
    """Jobs exportieren."""
    if fmt != "csv":
        print(f"Format '{fmt}' nicht unterstützt. Nur 'csv' verfügbar.")
        sys.exit(1)
    print("Export noch nicht implementiert (Phase 7).")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="jobtracker",
        description="Indeed Job Tracker – Stellenangebote automatisch verfolgen",
    )
    parser.add_argument("--config", default="config/settings.yaml", help="Pfad zur Konfiguration")

    sub = parser.add_subparsers(dest="command")
    sub.add_parser("run", help="Einmaliger Crawl aller Suchprofile")
    sub.add_parser("dashboard", help="CLI-Dashboard anzeigen")
    sub.add_parser("scheduler", help="Dauerhaft mit Scheduler starten")

    status_p = sub.add_parser("status", help="Bewerbungsstatus eines Jobs setzen")
    status_p.add_argument("job_id", type=str, help="Job-ID (MongoDB ObjectId, 24 hex Zeichen)")
    status_p.add_argument("new_status", help="Neuer Status")

    export_p = sub.add_parser("export", help="Jobs exportieren")
    export_p.add_argument("format", choices=["csv"], help="Exportformat")

    scrape_p = sub.add_parser("scrape", help="Indeed-Suchergebnisseite mit Browser scrapen")
    scrape_p.add_argument("url", help="Indeed Suchergebnis-URL")
    scrape_p.add_argument(
        "--name",
        default="scraper",
        help="Profilname für die gespeicherten Stellen (Standard: scraper)",
    )

    analyze_p = sub.add_parser(
        "analyze",
        help="Stelle mit Lebenslauf abgleichen (KI-Analyse)",
    )
    analyze_p.add_argument(
        "job",
        help="Job-ID aus DB, Pfad zu einer Textdatei mit der Ausschreibung, oder '-' für stdin",
    )
    analyze_p.add_argument(
        "--cv",
        default=None,
        help="Pfad zum Lebenslauf (PDF oder Textdatei). Überschreibt cv.path aus settings.yaml",
    )

    args = parser.parse_args()

    config = load_config(args.config)
    _setup_logging(config)
    db_cfg = config.get("database", {})
    init_db(
        uri=os.environ.get("MONGODB_URI") or db_cfg.get("uri"),
        db_name=os.environ.get("MONGODB_DB") or db_cfg.get("name"),
    )

    if args.command == "run":
        cmd_run(config)
    elif args.command == "dashboard":
        cmd_dashboard(config)
    elif args.command == "scheduler":
        cmd_scheduler(config)
    elif args.command == "status":
        cmd_status(config, args.job_id, args.new_status)
    elif args.command == "scrape":
        cmd_scrape(config, args.url, args.name)
    elif args.command == "export":
        cmd_export(config, args.format)
    elif args.command == "analyze":
        cmd_analyze(config, args.job, args.cv)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
