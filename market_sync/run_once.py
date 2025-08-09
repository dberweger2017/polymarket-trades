import os
import json
from dotenv import load_dotenv
from .config import DB_PATH, VOYAGE_MODEL
from .db import open_db
from .embeddings import EmbeddingCache, Embedder
from .repo import Repo
from .clients.polymarket import PolymarketClient
from .sync import sync_source
from .match import propose_and_link

def run_once(limit_per_source: int = 500):
    load_dotenv()
    conn = open_db(DB_PATH)
    cache = EmbeddingCache(conn)
    repo = Repo(conn)
    embedder = Embedder(model=VOYAGE_MODEL, cache=cache, api_key=os.getenv("VOYAGE_API_KEY"))
    sources = {}
    pm = PolymarketClient()
    sources["polymarket"] = pm.fetch_bets(limit_per_source)
    for src, bets in sources.items():
        sync_source(bets, repo, embedder)
    auto_links, queued = propose_and_link(repo, embedder, list(sources.keys()))
    print(json.dumps({"linked": auto_links, "queued": queued}))

if __name__ == "__main__":
    run_once(500)

