# market_sync/db.py
import sqlite3
import logging
from .util import now_ts

logger = logging.getLogger(__name__)

def open_db(path: str):
    logger.info("Opening SQLite DB at %s", path)
    conn = sqlite3.connect(path, check_same_thread=False)
    cur = conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL;")
    cur.execute("PRAGMA synchronous=NORMAL;")
    logger.debug("Ensuring tables exist")
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS embeddings (
            hash TEXT NOT NULL,
            model TEXT NOT NULL,
            embedding TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            PRIMARY KEY (hash, model)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS bets (
            source TEXT NOT NULL,
            market_id TEXT NOT NULL,
            slug TEXT,
            title TEXT NOT NULL,
            description TEXT,
            url TEXT,
            close_time TEXT,
            text_hash TEXT NOT NULL,
            is_active INTEGER NOT NULL,
            first_seen_at INTEGER NOT NULL,
            last_seen_at INTEGER NOT NULL,
            inactive_at INTEGER,
            PRIMARY KEY (source, market_id)
        )
        """
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_bets_text_hash ON bets(text_hash)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_bets_active ON bets(is_active)")
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
            id TEXT PRIMARY KEY,
            title TEXT,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS event_aliases (
            event_id TEXT NOT NULL,
            source TEXT NOT NULL,
            market_id TEXT NOT NULL,
            text_hash TEXT NOT NULL,
            similarity REAL,
            llm_confidence REAL,
            method TEXT,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            PRIMARY KEY (source, market_id),
            FOREIGN KEY (event_id) REFERENCES events(id)
        )
        """
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_event_aliases_event ON event_aliases(event_id)")
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS event_candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pair_key TEXT UNIQUE,
            a_source TEXT NOT NULL,
            a_market_id TEXT NOT NULL,
            b_source TEXT NOT NULL,
            b_market_id TEXT NOT NULL,
            similarity REAL NOT NULL,
            reason TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at INTEGER NOT NULL
        )
        """
    )
    conn.commit()
    logger.info("DB ready")
    return conn

