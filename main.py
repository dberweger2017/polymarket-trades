# main.py
import os
from dotenv import load_dotenv
from market_sync.config import DB_PATH, VOYAGE_MODEL
from market_sync.db import open_db
from market_sync.embeddings import EmbeddingCache, Embedder
from market_sync.repo import Repo
from market_sync.clients.polymarket import PolymarketClient
from market_sync.sync import sync_source
from market_sync.match import propose_and_link

def main():
    load_dotenv()
    conn = open_db(DB_PATH)
    cache = EmbeddingCache(conn)
    repo = Repo(conn)
    embedder = Embedder(model=VOYAGE_MODEL, cache=cache, api_key=os.getenv("VOYAGE_API_KEY"))
    bets = PolymarketClient().fetch_bets(500)
    print(bets)
    sync_source(bets, repo, embedder)
    #auto_links, queued = propose_and_link(repo, embedder, ["polymarket"])
    #print({"linked": auto_links, "queued": queued})

if __name__ == "__main__":
    main()