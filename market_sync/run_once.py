import os
import json
import logging
from dotenv import load_dotenv
from .config import DB_PATH, VOYAGE_MODEL
from .db import open_db
from .embeddings import EmbeddingCache, Embedder
from .repo import Repo
from .clients.polymarket import PolymarketClient
from .sync import sync_source
from .match import propose_and_link

def run_once(limit_per_source: int = 500):
    # Basic logging config; respect LOG_LEVEL env var
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    logger = logging.getLogger(__name__)

    load_dotenv()
    logger.info("run_once start limit_per_source=%d", limit_per_source)
    conn = open_db(DB_PATH)
    cache = EmbeddingCache(conn)
    repo = Repo(conn)
    embedder = Embedder(model=VOYAGE_MODEL, cache=cache, api_key=os.getenv("VOYAGE_API_KEY"))
    sources = {}
    pm = PolymarketClient()
    sources["polymarket"] = pm.fetch_bets(limit_per_source)
    for src, bets in sources.items():
        logger.info("Syncing source %s with %d bets", src, len(bets))
        sync_source(bets, repo, embedder)
    auto_links, queued = propose_and_link(repo, embedder, list(sources.keys()))
    result = {"linked": auto_links, "queued": queued}
    logger.info("run_once result: %s", result)
    print(json.dumps(result))

if __name__ == "__main__":
    run_once(500)

