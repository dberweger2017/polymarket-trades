# main.py
import os
import argparse
from dotenv import load_dotenv
from market_sync.config import DB_PATH, VOYAGE_MODEL
from market_sync.db import open_db
from market_sync.embeddings import EmbeddingCache, Embedder
from market_sync.repo import Repo
from market_sync.clients.polymarket import PolymarketClient
from market_sync.sync import sync_source
# from market_sync.match import propose_and_link  # optional

def main():
    load_dotenv()

    parser = argparse.ArgumentParser()
    parser.add_argument("--ui", action="store_true", help="Launch the live UI")
    parser.add_argument("--progress", action="store_true", help="Show tqdm progress during sync")
    parser.add_argument("--no-backfill", action="store_true", help="Do not resume missing embeddings")
    args = parser.parse_args()

    if args.ui:
        # Run Streamlit UI
        import subprocess, sys, pathlib
        ui_path = pathlib.Path(__file__).with_name("ui_streamlit.py")
        if not ui_path.exists():
            # fallback: assume ui_streamlit.py is in repo root (next to main.py)
            ui_path = pathlib.Path("ui_streamlit.py")
        subprocess.run([sys.executable, "-m", "streamlit", "run", str(ui_path)], check=False)
        return

    conn = open_db(DB_PATH)
    cache = EmbeddingCache(conn)
    repo = Repo(conn)
    embedder = Embedder(model=VOYAGE_MODEL, cache=cache, api_key=os.getenv("VOYAGE_API_KEY"))
    bets = PolymarketClient().fetch_bets(10000)
    print(f"Fetched {len(bets)} bets from Polymarket")
    sync_source(bets, repo, embedder, show_progress=args.progress, backfill_missing=not args.no_backfill)
    # auto_links, queued = propose_and_link(repo, embedder, ["polymarket"])
    # print({"linked": auto_links, "queued": queued})

if __name__ == "__main__":
    main()
