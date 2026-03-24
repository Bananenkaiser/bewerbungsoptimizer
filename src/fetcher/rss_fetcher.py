"""RSS Feed Fetcher für Indeed Stellenangebote."""

import hashlib
import logging
import random
import re
import time
import urllib.parse
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime

import feedparser
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

INDEED_RSS_BASE = "https://de.indeed.com/rss"


@dataclass
class RawJob:
    """Rohdaten eines Indeed RSS-Eintrags."""

    guid: str
    content_hash: str
    title: str
    company: str
    location: str
    url: str
    description: str
    published_at: datetime | None
    search_profile: str


def _build_rss_url(profile: dict) -> str:
    params: dict[str, str] = {
        "q": profile.get("keywords", ""),
        "l": profile.get("location", ""),
        "sort": "date",
        "fromage": str(profile.get("max_age_days", 7)),
    }
    if profile.get("radius_km"):
        params["radius"] = str(profile["radius_km"])
    if profile.get("job_type"):
        params["jt"] = profile["job_type"]
    return f"{INDEED_RSS_BASE}?{urllib.parse.urlencode(params)}"


def _strip_html(html: str) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    return soup.get_text(separator=" ", strip=True)


def _parse_title_company(raw_title: str) -> tuple[str, str]:
    """Indeed RSS-Titel hat oft das Format 'Job Title - Company Name'."""
    parts = re.split(r"\s+-\s+", raw_title, maxsplit=1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return raw_title.strip(), ""


def _parse_published(entry: object) -> datetime | None:
    if hasattr(entry, "published") and entry.published:
        try:
            return parsedate_to_datetime(entry.published)
        except Exception:
            pass
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        try:
            return datetime(*entry.published_parsed[:6])
        except Exception:
            pass
    return None


def _clean_url(url: str) -> str:
    """Tracking-Parameter aus Indeed-URL entfernen, Job-Key behalten."""
    parsed = urllib.parse.urlparse(url)
    params = urllib.parse.parse_qs(parsed.query)
    keep = {"jk"}
    filtered = {k: v for k, v in params.items() if k in keep}
    clean_query = urllib.parse.urlencode(filtered, doseq=True)
    return urllib.parse.urlunparse(parsed._replace(query=clean_query))


def _compute_hash(title: str, company: str) -> str:
    raw = f"{title.lower().strip()}|{company.lower().strip()}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _sanitize_xml(data: bytes) -> bytes:
    """Ersetzt unescaped & in XML (häufigste Indeed-Ursache für 'not well-formed')."""
    text = data.decode("utf-8", errors="replace")
    text = re.sub(r"&(?!(?:[a-zA-Z]+|#[0-9]+|#x[0-9a-fA-F]+);)", "&amp;", text)
    return text.encode("utf-8")


def fetch_profile(profile: dict) -> list[RawJob]:
    """Fetcht den Indeed RSS Feed für ein Suchprofil und gibt Rohdaten zurück."""
    from feedparser import http as fp_http

    url = _build_rss_url(profile)
    profile_name = profile.get("name", "unknown")
    logger.info("[%s] Fetche RSS: %s", profile_name, url)

    # feedparser intern fetchen (umgeht 403-Exceptions), XML bereinigen
    result: dict = {}
    try:
        raw_data: bytes = fp_http.get(url, result=result) or b""
    except Exception as exc:
        logger.error("[%s] Fetch-Fehler: %s", profile_name, exc)
        return []

    if not raw_data:
        logger.warning("[%s] Leere Antwort vom Feed.", profile_name)
        return []

    sanitized = _sanitize_xml(raw_data)
    feed = feedparser.parse(sanitized)

    if feed.bozo and feed.bozo_exception:
        logger.warning("[%s] Feed-Parsing-Warnung: %s", profile_name, feed.bozo_exception)

    if not feed.entries:
        logger.info("[%s] Keine Einträge im Feed.", profile_name)
        return []

    jobs: list[RawJob] = []
    for entry in feed.entries:
        guid: str = entry.get("id") or entry.get("link") or ""
        if not guid:
            continue

        raw_title: str = entry.get("title", "")
        title, company = _parse_title_company(raw_title)

        description_html: str = entry.get("summary") or entry.get("description") or ""
        description = _strip_html(description_html)

        # Fallback: Company aus description extrahieren (Indeed-Format)
        if not company:
            m = re.search(r"Company:\s*([^\n<]+)", description_html)
            if m:
                company = m.group(1).strip()

        location: str = entry.get("location", "") or profile.get("location", "")

        raw_url: str = entry.get("link") or ""
        url_clean = _clean_url(raw_url) if raw_url else raw_url

        published_at = _parse_published(entry)
        content_hash = _compute_hash(title, company)

        jobs.append(
            RawJob(
                guid=guid,
                content_hash=content_hash,
                title=title,
                company=company,
                location=location,
                url=url_clean,
                description=description,
                published_at=published_at,
                search_profile=profile_name,
            )
        )

    logger.info("[%s] %d Stellen im Feed.", profile_name, len(jobs))
    return jobs


def fetch_all_profiles(
    profiles: list[dict],
    min_delay: float = 5.0,
    max_delay: float = 15.0,
) -> list[RawJob]:
    """Fetcht alle Suchprofile nacheinander mit Rate-Limiting."""
    all_jobs: list[RawJob] = []
    for i, profile in enumerate(profiles):
        if i > 0:
            delay = random.uniform(min_delay, max_delay)
            logger.debug("Rate-Limiting: %.1fs warten ...", delay)
            time.sleep(delay)
        jobs = fetch_profile(profile)
        all_jobs.extend(jobs)
    return all_jobs
