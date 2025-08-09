from typing import List, Tuple
import logging
from .models import Bet
from .repo import Repo
from .embeddings import Embedder

logger = logging.getLogger(__name__)

def sync_source(bets: List[Bet], repo: Repo, embedder: Embedder) -> Tuple[list, list, int]:
    logger.info("sync_source start: source=%s count=%d", bets[0].source if bets else "", len(bets))
    new_or_changed = []
    active_ids = []
    for b in bets:
        is_new, is_changed = repo.upsert_bet(b)
        if is_new or is_changed:
            new_or_changed.append(b)
        active_ids.append(b.market_id)
    inactivated = repo.mark_inactive_except(bets[0].source if bets else "", set(active_ids))
    logger.info("sync_source: new_or_changed=%d inactivated=%d", len(new_or_changed), inactivated)
    need_embed = []
    for b in new_or_changed:
        h = embedder.text_hash(b.text_for_embedding)
        if embedder.cache.get(h, embedder.model) is None:
            need_embed.append(b.text_for_embedding)
    if need_embed:
        logger.info("sync_source: embedding %d texts", len(need_embed))
        embedder.embed_texts(need_embed)
    logger.info("sync_source done: source=%s", bets[0].source if bets else "")
    return new_or_changed, bets, inactivated

