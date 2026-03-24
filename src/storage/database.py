"""MongoDB-Verbindungsverwaltung für Indeed Job Tracker."""

import os
from contextlib import contextmanager
from typing import Generator

from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

_client: MongoClient | None = None
_db: Database | None = None

JOBS_COLLECTION = "jobs"
SEARCH_RUNS_COLLECTION = "search_runs"


def init_db(uri: str | None = None, db_name: str | None = None) -> Database:
    """Initialisiert die MongoDB-Verbindung und erstellt Indizes.

    Liest MONGODB_URI und MONGODB_DB aus Umgebungsvariablen, falls keine
    Argumente übergeben werden.
    """
    global _client, _db

    resolved_uri = uri or os.environ.get("MONGODB_URI", "mongodb://localhost:27017/jobtracker")
    resolved_db = db_name or os.environ.get("MONGODB_DB", "jobtracker")

    _client = MongoClient(resolved_uri, serverSelectionTimeoutMS=10_000)
    _db = _client[resolved_db]

    # Indizes anlegen (idempotent – sicher bei jedem Start)
    _db[JOBS_COLLECTION].create_index("guid", unique=True)
    _db[JOBS_COLLECTION].create_index("content_hash")
    _db[JOBS_COLLECTION].create_index("published_at")
    _db[JOBS_COLLECTION].create_index("search_profile")
    _db[SEARCH_RUNS_COLLECTION].create_index("started_at")

    return _db


def get_db() -> Database:
    """Gibt das aktive MongoDB-Datenbank-Handle zurück."""
    if _db is None:
        raise RuntimeError("Datenbank nicht initialisiert. Zuerst init_db() aufrufen.")
    return _db


def get_collection(name: str) -> Collection:
    """Gibt eine benannte Collection aus der aktiven Datenbank zurück."""
    return get_db()[name]


@contextmanager
def get_session() -> Generator[Database, None, None]:
    """Context Manager, der das Datenbank-Handle liefert.

    Behält den Namen 'get_session' für Kompatibilität mit den Aufrufstellen
    in main.py. MongoDB benötigt hier keine explizite Transaktionssession.
    """
    db = get_db()
    yield db
