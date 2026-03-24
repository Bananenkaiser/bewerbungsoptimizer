"""Playwright-basierter Scraper für Indeed Stellenangebote.

Wird verwendet wenn der RSS-Feed blockiert wird oder keine Ergebnisse liefert.
Nimmt eine Indeed-Suchergebnis-URL entgegen und extrahiert alle Stellenangebote.
"""

import hashlib
import logging
import random
import re
import time
from datetime import datetime, timezone
from urllib.parse import urlparse, parse_qs

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

from src.fetcher.rss_fetcher import RawJob

logger = logging.getLogger(__name__)

INDEED_BASE = "https://de.indeed.com"

# Realistischer User-Agent (Chrome auf Linux)
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def _extract_job_key(url: str) -> str:
    """Extrahiert den Indeed Job-Key (jk=...) aus einer URL."""
    params = parse_qs(urlparse(url).query)
    keys = params.get("jk") or params.get("vjk")
    return keys[0] if keys else ""


def _compute_hash(title: str, company: str) -> str:
    raw = f"{title.lower().strip()}|{company.lower().strip()}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _random_delay(min_s: float = 2.0, max_s: float = 5.0) -> None:
    time.sleep(random.uniform(min_s, max_s))


def scrape_search_url(
    search_url: str,
    profile_name: str = "scraper",
    max_jobs: int = 50,
) -> list[RawJob]:
    """Scrapt eine Indeed-Suchergebnis-URL und gibt Rohdaten zurück.

    Args:
        search_url: Indeed-Suchergebnis-URL (z.B. https://de.indeed.com/Jobs?q=Data+Scientist&l=Kleve...)
        profile_name: Name des Suchprofils (für Logging und Speicherung)
        max_jobs: Maximale Anzahl zu scrapender Stellen
    """
    jobs: list[RawJob] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1280, "height": 900},
            locale="de-DE",
        )
        page = context.new_page()

        # Cookie-Banner und Popups ignorieren
        page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """)

        logger.info("[%s] Öffne Suchergebnisseite: %s", profile_name, search_url)
        try:
            page.goto(search_url, wait_until="domcontentloaded", timeout=30_000)
        except PlaywrightTimeout:
            logger.error("[%s] Timeout beim Laden der Suchergebnisseite.", profile_name)
            browser.close()
            return []

        # Cookie-Banner wegklicken falls vorhanden
        try:
            page.click('[id*="onetrust-accept"]', timeout=3_000)
        except PlaywrightTimeout:
            pass

        # Job-Cards finden — Indeed nutzt data-jk Attribut
        job_links = page.query_selector_all("a[data-jk]")
        if not job_links:
            # Fallback: Links mit /rc/clk oder /pagead/clk
            job_links = page.query_selector_all("h2.jobTitle a, a.jcs-JobTitle")

        logger.info("[%s] %d Job-Cards gefunden.", profile_name, len(job_links))

        # Job-Keys und URLs sammeln
        job_entries: list[dict] = []
        seen_keys: set[str] = set()
        for link in job_links[:max_jobs]:
            href = link.get_attribute("href") or ""
            jk = link.get_attribute("data-jk") or _extract_job_key(href)
            if not jk or jk in seen_keys:
                continue
            seen_keys.add(jk)
            full_url = f"{INDEED_BASE}/viewjob?jk={jk}"
            job_entries.append({"jk": jk, "url": full_url})

        logger.info("[%s] %d eindeutige Stellen zum Scrapen.", profile_name, len(job_entries))

        # Jede Stelle einzeln öffnen
        for i, entry in enumerate(job_entries):
            _random_delay(2.0, 5.0)
            job_url = entry["url"]
            logger.debug("[%s] Scrape %d/%d: %s", profile_name, i + 1, len(job_entries), job_url)

            try:
                page.goto(job_url, wait_until="domcontentloaded", timeout=20_000)
            except PlaywrightTimeout:
                logger.warning("[%s] Timeout bei %s – übersprungen.", profile_name, job_url)
                continue

            # Titel
            title = ""
            for sel in ["h1.jobsearch-JobInfoHeader-title", "h1[data-testid='jobsearch-JobInfoHeader-title']", "h1"]:
                el = page.query_selector(sel)
                if el:
                    title = el.inner_text().strip()
                    break

            # Unternehmen
            company = ""
            for sel in [
                "[data-testid='inlineHeader-companyName']",
                "[data-testid='companyInfo-name']",
                ".jobsearch-InlineCompanyRating-companyName",
                "[data-company-name]",
            ]:
                el = page.query_selector(sel)
                if el:
                    company = el.inner_text().strip()
                    break

            # Ort
            location = ""
            for sel in [
                "[data-testid='inlineHeader-companyLocation']",
                "[data-testid='jobsearch-JobInfoHeader-companyLocation']",
                ".jobsearch-JobInfoHeader-subtitle .jobsearch-JobInfoHeader-locationField",
            ]:
                el = page.query_selector(sel)
                if el:
                    location = el.inner_text().strip()
                    break

            # Beschreibung
            description = ""
            for sel in [
                "#jobDescriptionText",
                "[data-testid='jobsearch-JobComponent-description']",
                ".jobsearch-jobDescriptionText",
            ]:
                el = page.query_selector(sel)
                if el:
                    description = el.inner_text().strip()
                    break

            if not title and not description:
                logger.warning("[%s] Keine Inhalte bei %s – übersprungen.", profile_name, job_url)
                continue

            guid = f"jk:{entry['jk']}"
            content_hash = _compute_hash(title, company)

            jobs.append(RawJob(
                guid=guid,
                content_hash=content_hash,
                title=title,
                company=company,
                location=location,
                url=job_url,
                description=description,
                published_at=None,
                search_profile=profile_name,
            ))
            logger.info("[%s] ✓ %s @ %s", profile_name, title, company)

        browser.close()

    logger.info("[%s] Scraping abgeschlossen: %d Stellen.", profile_name, len(jobs))
    return jobs
