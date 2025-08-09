import hashlib
import math
from typing import List, Dict, Tuple
from .embeddings import EmbeddingCache, Embedder
from .repo import Repo

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
        source_rows[s] = repo.fetch_active_bets_by_source(s)
    for s in sources:
        others = [x for x in sources if x != s]
        for mid, title, description, url, thash in source_rows[s]:
            if repo.get_event_for_bet(s, mid):
                continue
            a_text = "\n\n".join([title or "", description or ""]).strip()
            if not a_text:
                continue
            a_hash = hashlib.sha256(a_text.encode("utf-8")).hexdigest()
            a_vec = embedder.cache.get(a_hash, embedder.model)
            if a_vec is None:
                a_vec = embedder.embed_text(a_text)
            for osrc in others:
                checked = 0
                for omid, ot, od, ou, oth in source_rows[osrc]:
                    if repo.get_event_for_bet(osrc, omid):
                        continue
                    b_text = "\n\n".join([ot or "", od or ""]).strip()
                    if not b_text:
                        continue
                    b_hash = hashlib.sha256(b_text.encode("utf-8")).hexdigest()
                    b_vec = embedder.cache.get(b_hash, embedder.model)
                    if b_vec is None:
                        b_vec = embedder.embed_text(b_text)
                    sim = cosine(a_vec, b_vec)
                    if sim >= high:
                        eida = repo.get_event_for_bet(s, mid)
                        eidb = repo.get_event_for_bet(osrc, omid)
                        if eida and eidb and eida == eidb:
                            pass
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
                        break
    return auto_links, queued

