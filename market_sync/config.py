# market_sync/config.py
import os
import logging

logger = logging.getLogger(__name__)
GAMMA_BASE = os.getenv("GAMMA_BASE", "https://gamma-api.polymarket.com")
VOYAGE_MODEL = os.getenv("VOYAGE_MODEL", "voyage-3.5")
DB_PATH = os.getenv("DB_PATH", "embeddings_cache.sqlite")
USER_AGENT = os.getenv("USER_AGENT", "market-sync/1.0")

# Log resolved configuration (avoid secrets)
logger.debug("Config resolved: GAMMA_BASE=%s, VOYAGE_MODEL=%s, DB_PATH=%s, USER_AGENT=%s", GAMMA_BASE, VOYAGE_MODEL, DB_PATH, USER_AGENT)

