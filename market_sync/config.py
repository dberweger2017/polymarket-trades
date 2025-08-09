import os
GAMMA_BASE = os.getenv("GAMMA_BASE", "https://gamma-api.polymarket.com")
VOYAGE_MODEL = os.getenv("VOYAGE_MODEL", "voyage-3.5")
DB_PATH = os.getenv("DB_PATH", "embeddings_cache.sqlite")
USER_AGENT = os.getenv("USER_AGENT", "market-sync/1.0")

