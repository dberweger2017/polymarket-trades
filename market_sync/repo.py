import hashlib
from typing import Optional, Tuple, Iterable, List
import uuid
import logging
from .util import now_ts

logger = logging.getLogger(__name__)
class Repo:
    def __init__(self, conn):
        self.conn = conn

    def get_existing_bet(self, source: str, market_id: str) -> Optional[Tuple]:
        logger.debug("Fetching existing bet: %s:%s", source, market_id)
        row = self.conn.execute(
            "SELECT source, market_id, text_hash, is_active FROM bets WHERE source=? AND market_id=?",
            (source, market_id),
        ).fetchone()
        return row

    def upsert_bet(self, b) -> Tuple[bool, bool]:
        existing = self.get_existing_bet(b.source, b.market_id)
        now = now_ts()
        if not existing:
            logger.info("Inserting new bet: %s:%s title=%r", b.source, b.market_id, b.title)
            self.conn.execute(
                """
                INSERT INTO bets(source, market_id, slug, title, description, url, close_time, text_hash, is_active, first_seen_at, last_seen_at, inactive_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (b.source, b.market_id, b.slug, b.title, b.description, b.url, b.close_time, b.text_hash, 1, now, now, None),
            )
            self.conn.commit()
            return True, True
        changed = existing[2] != b.text_hash
        logger.info("Updating bet: %s:%s changed=%s", b.source, b.market_id, changed)
        self.conn.execute(
            """
            UPDATE bets SET slug=?, title=?, description=?, url=?, close_time=?, text_hash=?, is_active=1, last_seen_at=?, inactive_at=NULL
            WHERE source=? AND market_id=?
            """,
            (b.slug, b.title, b.description, b.url, b.close_time, b.text_hash, now, b.source, b.market_id),
        )
        self.conn.commit()
        return False, changed

    def mark_inactive_except(self, source: str, active_ids: Iterable[str]) -> int:
        now = now_ts()
        ids = list(active_ids)
        if not ids:
            logger.info("Marking all bets inactive for source=%s", source)
            cur = self.conn.execute(
                "UPDATE bets SET is_active=0, inactive_at=? WHERE source=? AND is_active=1",
                (now, source),
            )
        else:
            logger.info("Marking bets inactive for source=%s excluding %d ids", source, len(ids))
            q = "UPDATE bets SET is_active=0, inactive_at=? WHERE source=? AND is_active=1 AND market_id NOT IN ({})".format(",".join("?" * len(ids)))
            args = [now, source] + ids
            cur = self.conn.execute(q, args)
        self.conn.commit()
        return cur.rowcount

    def get_event_for_bet(self, source: str, market_id: str) -> Optional[str]:
        row = self.conn.execute(
            "SELECT event_id FROM event_aliases WHERE source=? AND market_id=?",
            (source, market_id),
        ).fetchone()
        return row[0] if row else None

    def create_event(self, title: Optional[str] = None) -> str:
        eid = str(uuid.uuid4())
        now = now_ts()
        logger.info("Creating event: id=%s title=%r", eid, title)
        self.conn.execute(
            "INSERT INTO events(id, title, created_at, updated_at) VALUES(?,?,?,?)",
            (eid, title, now, now),
        )
        self.conn.commit()
        return eid

    def link_bet_to_event(self, event_id: str, source: str, market_id: str, text_hash: str, similarity: Optional[float], llm_confidence: Optional[float], method: str):
        now = now_ts()
        logger.info("Linking bet to event: event=%s %s:%s method=%s sim=%s", event_id, source, market_id, method, similarity)
        self.conn.execute(
            """
            INSERT INTO event_aliases(event_id, source, market_id, text_hash, similarity, llm_confidence, method, created_at, updated_at)
            VALUES(?,?,?,?,?,?,?, ?, ?)
            ON CONFLICT(source, market_id) DO UPDATE SET
              event_id=excluded.event_id, text_hash=excluded.text_hash, similarity=excluded.similarity,
              llm_confidence=excluded.llm_confidence, method=excluded.method, updated_at=excluded.updated_at
            """,
            (event_id, source, market_id, text_hash, similarity, llm_confidence, method, now, now),
        )
        self.conn.commit()

    def queue_pair(self, a_source: str, a_market_id: str, b_source: str, b_market_id: str, similarity: float, reason: str):
        pair = sorted([(a_source, a_market_id), (b_source, b_market_id)])
        key = hashlib.sha256((":".join(pair[0]) + "|" + ":".join(pair[1])).encode("utf-8")).hexdigest()
        logger.info("Queue pair: %s:%s <-> %s:%s sim=%.4f reason=%s", a_source, a_market_id, b_source, b_market_id, similarity, reason)
        self.conn.execute(
            """
            INSERT OR IGNORE INTO event_candidates(pair_key, a_source, a_market_id, b_source, b_market_id, similarity, reason, status, created_at)
            VALUES(?,?,?,?,?,?,?,?,?)
            """,
            (key, a_source, a_market_id, b_source, b_market_id, float(similarity), reason, "pending", now_ts()),
        )
        self.conn.commit()

    def fetch_active_bets_by_source(self, source: str) -> List[tuple]:
        rows = self.conn.execute(
            "SELECT market_id, title, description, url, text_hash FROM bets WHERE source=? AND is_active=1",
            (source,),
        ).fetchall()
        logger.debug("Fetched %d active bets for source=%s", len(rows), source)
        return rows

