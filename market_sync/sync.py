# market_sync/sync.py
from typing import List, Tuple
import logging
from .models import Bet
from .repo import Repo
from .embeddings import Embedder

logger = logging.getLogger(__name__)

def sync_source(bets: List[Bet], repo: Repo, embedder: Embedder, show_progress: bool = False) -> Tuple[list, list, int]:
    logger.info("sync_source start: source=%s count=%d", bets[0].source if bets else "", len(bets))
    new_or_changed = []
    active_ids = []

    # --- progress bar (pass 1: upsert) ---
    iterator = bets
    pbar = None
    if show_progress and bets:
        try:
            from tqdm.auto import tqdm
            pbar = tqdm(bets, desc=f"sync[{bets[0].source}]", unit="bet")
            iterator = pbar
        except Exception:
            logger.debug("tqdm not available; continuing without progress")

    for b in iterator:
        is_new, is_changed = repo.upsert_bet(b)
        status = "insert" if is_new else ("update" if is_changed else "skip")
        if pbar:
            pbar.set_postfix_str(f"{status} id={b.market_id}")
        if is_new or is_changed:
            new_or_changed.append(b)
        active_ids.append(b.market_id)

    if pbar:
        pbar.close()

    inactivated = repo.mark_inactive_except(bets[0].source if bets else "", set(active_ids))
    logger.info("sync_source: new_or_changed=%d inactivated=%d", len(new_or_changed), inactivated)

    # Decide which texts still need embeddings
    need_embed_texts = []
    need_embed_bets = []
    for b in new_or_changed:
        h = embedder.text_hash(b.text_for_embedding)
        if embedder.cache.get(h, embedder.model) is None:
            need_embed_texts.append(b.text_for_embedding)
            need_embed_bets.append(b)

    # --- progress bar (pass 2: embedding) ---
    if need_embed_texts:
        if show_progress:
            try:
                from tqdm.auto import tqdm
                p2 = tqdm(need_embed_bets, desc="embedding", unit="bet")
                for b in p2:
                    # ensure still missing (race-safe) then embed one-by-one for rich progress
                    h = embedder.text_hash(b.text_for_embedding)
                    if embedder.cache.get(h, embedder.model) is None:
                        embedder.embed_text(b.text_for_embedding)
                    p2.set_postfix_str(f"embedded id={b.market_id}")
                p2.close()
            except Exception:
                logger.debug("tqdm not available during embedding; falling back to batch")
                embedder.embed_texts(need_embed_texts)
        else:
            # fast batched path (default)
            embedder.embed_texts(need_embed_texts)

    logger.info("sync_source done: source=%s", bets[0].source if bets else "")
    return new_or_changed, bets, inactivated