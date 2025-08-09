# market_sync/match.py
import hashlib
import math
import logging
from typing import List, Dict, Tuple
from .embeddings import EmbeddingCache, Embedder
from .repo import Repo

logger = logging.getLogger(__name__)

def cosine(a: List[float], b: List[float]) -> float:
    da = 0.0
    db = 0.0
    dot = 0.0
    for x, y in zip(a, b):
        dot += x * y
        da += x * x
        db += y * y
    if da == 0.0 or db == 0.0:
        return 0.0
    return dot / math.sqrt(da * db)

def propose_and_link(repo: Repo, embedder: Embedder, sources: List[str], high: float = 0.9, low: float = 0.83, max_pairs_per_new: int = 2000) -> Tuple[int, int]:
    auto_links = 0
    queued = 0
    source_rows: Dict[str, List[tuple]] = {}
    for s in sources:
        logger.info("Gathering active bets for source=%s", s)
        source_rows[s] = repo.fetch_active_bets_by_source(s)
    for s in sources:
        others = [x for x in sources if x != s]
        logger.info("Matching for source=%s vs %s", s, ",".join(others))
        for mid, title, description, url, thash in source_rows[s]:
            if repo.get_event_for_bet(s, mid):
                logger.debug("Skipping already-linked bet %s:%s", s, mid)
                continue
            a_text = "\n\n".join([title or "", description or ""]).strip()
            if not a_text:
                logger.debug("Skipping empty text for %s:%s", s, mid)
                continue
            a_hash = hashlib.sha256(a_text.encode("utf-8")).hexdigest()
            a_vec = embedder.cache.get(a_hash, embedder.model)
            if a_vec is None:
                logger.debug("Embedding A %s:%s", s, mid)
                a_vec = embedder.embed_text(a_text)
            for osrc in others:
                checked = 0
                for omid, ot, od, ou, oth in source_rows[osrc]:
                    if repo.get_event_for_bet(osrc, omid):
                        logger.debug("Skipping already-linked candidate %s:%s", osrc, omid)
                        continue
                    b_text = "\n\n".join([ot or "", od or ""]).strip()
                    if not b_text:
                        logger.debug("Skipping empty candidate text %s:%s", osrc, omid)
                        continue
                    b_hash = hashlib.sha256(b_text.encode("utf-8")).hexdigest()
                    b_vec = embedder.cache.get(b_hash, embedder.model)
                    if b_vec is None:
                        logger.debug("Embedding B %s:%s", osrc, omid)
                        b_vec = embedder.embed_text(b_text)
                    sim = cosine(a_vec, b_vec)
                    logger.debug("sim(%s:%s, %s:%s)=%.4f", s, mid, osrc, omid, sim)
                    if sim >= high:
                        eida = repo.get_event_for_bet(s, mid)
                        eidb = repo.get_event_for_bet(osrc, omid)
                        if eida and eidb and eida == eidb:
                            logger.debug("Already in same event: %s", eida)
                        elif eida and not eidb:
                            repo.link_bet_to_event(eida, osrc, omid, oth, sim, None, "auto-sim")
                            auto_links += 1
                        elif eidb and not eida:
                            repo.link_bet_to_event(eidb, s, mid, thash, sim, None, "auto-sim")
                            auto_links += 1
                        else:
                            eid = repo.create_event(title=title or ot)
                            repo.link_bet_to_event(eid, s, mid, thash, sim, None, "auto-sim")
                            repo.link_bet_to_event(eid, osrc, omid, oth, sim, None, "auto-sim")
                            auto_links += 1
                    elif sim >= low:
                        repo.queue_pair(s, mid, osrc, omid, sim, "sim-threshold")
                        queued += 1
                    checked += 1
                    if checked >= max_pairs_per_new:
                        logger.info("Max pairs per new reached for %s:%s (limit=%d)", s, mid, max_pairs_per_new)
                        break
    logger.info("propose_and_link done: auto_links=%d queued=%d", auto_links, queued)
    return auto_links, queued

