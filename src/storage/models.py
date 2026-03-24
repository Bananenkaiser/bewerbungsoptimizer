"""MongoDB document helpers for Indeed Job Tracker.

Ersetzt SQLAlchemy ORM-Modelle. Dokumente werden in MongoDB als Dicts
gespeichert; diese Helfer bieten:
  - Dataclass-Definitionen für Typsicherheit in Python
  - to_document(): Serialisierung zum MongoDB-Dict
  - from_document(): Deserialisierung aus MongoDB-Dict
"""

import enum
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from bson import ObjectId


class JobStatus(str, enum.Enum):
    new = "new"
    saved = "saved"
    applied = "applied"
    interview = "interview"
    offer = "offer"
    rejected = "rejected"
    withdrawn = "withdrawn"


@dataclass
class Job:
    guid: str
    content_hash: str
    title: str
    company: str
    url: str
    location: str | None = None
    description: str | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    experience_level: str | None = None
    job_type: str | None = None
    keywords_matched: list[str] = field(default_factory=list)
    score: float | None = None
    published_at: datetime | None = None
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    status: JobStatus = JobStatus.new
    notified: bool = False
    search_profile: str | None = None
    _id: ObjectId | None = None

    def to_document(self) -> dict[str, Any]:
        doc: dict[str, Any] = {
            "guid": self.guid,
            "content_hash": self.content_hash,
            "title": self.title,
            "company": self.company,
            "url": self.url,
            "location": self.location,
            "description": self.description,
            "salary_min": self.salary_min,
            "salary_max": self.salary_max,
            "experience_level": self.experience_level,
            "job_type": self.job_type,
            "keywords_matched": self.keywords_matched,
            "score": self.score,
            "published_at": self.published_at,
            "fetched_at": self.fetched_at,
            "status": self.status.value,
            "notified": self.notified,
            "search_profile": self.search_profile,
        }
        if self._id is not None:
            doc["_id"] = self._id
        return doc

    @classmethod
    def from_document(cls, doc: dict[str, Any]) -> "Job":
        return cls(
            _id=doc.get("_id"),
            guid=doc["guid"],
            content_hash=doc["content_hash"],
            title=doc["title"],
            company=doc["company"],
            url=doc["url"],
            location=doc.get("location"),
            description=doc.get("description"),
            salary_min=doc.get("salary_min"),
            salary_max=doc.get("salary_max"),
            experience_level=doc.get("experience_level"),
            job_type=doc.get("job_type"),
            keywords_matched=doc.get("keywords_matched", []),
            score=doc.get("score"),
            published_at=doc.get("published_at"),
            fetched_at=doc.get("fetched_at", datetime.now(timezone.utc)),
            status=JobStatus(doc.get("status", "new")),
            notified=doc.get("notified", False),
            search_profile=doc.get("search_profile"),
        )

    def __repr__(self) -> str:
        return f"<Job guid={self.guid!r} title={self.title!r} status={self.status}>"


@dataclass
class SearchRun:
    search_profile: str
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None
    jobs_found: int = 0
    jobs_new: int = 0
    error: str | None = None
    _id: ObjectId | None = None

    def to_document(self) -> dict[str, Any]:
        doc: dict[str, Any] = {
            "search_profile": self.search_profile,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "jobs_found": self.jobs_found,
            "jobs_new": self.jobs_new,
            "error": self.error,
        }
        if self._id is not None:
            doc["_id"] = self._id
        return doc

    @classmethod
    def from_document(cls, doc: dict[str, Any]) -> "SearchRun":
        return cls(
            _id=doc.get("_id"),
            search_profile=doc["search_profile"],
            started_at=doc.get("started_at", datetime.now(timezone.utc)),
            finished_at=doc.get("finished_at"),
            jobs_found=doc.get("jobs_found", 0),
            jobs_new=doc.get("jobs_new", 0),
            error=doc.get("error"),
        )

    def __repr__(self) -> str:
        return (
            f"<SearchRun profile={self.search_profile!r} "
            f"found={self.jobs_found} new={self.jobs_new}>"
        )
