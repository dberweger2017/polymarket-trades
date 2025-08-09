from typing import List, Optional
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from ..config import GAMMA_BASE, USER_AGENT
from ..models import Bet
from ..util import iso_parse

class PolymarketClient:
    def __init__(self, base: str = GAMMA_BASE, session: Optional[requests.Session] = None):
        self.base = base.rstrip("/")
        self.sess = session or self._build_session()

    def _build_session(self) -> requests.Session:
        s = requests.Session()
        retry = Retry(total=5, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504], allowed_methods=frozenset(["GET"]))
        adapter = HTTPAdapter(max_retries=retry)
        s.mount("https://", adapter)
        s.mount("http://", adapter)
        s.headers.update({"User-Agent": USER_AGENT})
        return s

    def fetch_open_markets(self, limit: int = 1000) -> List[dict]:
        results: List[dict] = []
        cursor = None
        while len(results) < limit:
            params = {"limit": min(1000, max(1, limit - len(results))), "state": "open"}
            if cursor:
                params["cursor"] = cursor
            r = self.sess.get(f"{self.base}/markets", params=params, timeout=30)
            r.raise_for_status()
            payload = r.json()
            items = payload.get("data", payload)
            if isinstance(items, dict) and "data" in items:
                items = items["data"]
            if not isinstance(items, list):
                break
            results.extend(items)
            next_cursor = None
            for k in ("nextCursor", "next_cursor", "next", "cursor"):
                if k in payload and payload[k]:
                    next_cursor = payload[k]
                    break
            if not next_cursor or len(items) == 0:
                break
            cursor = next_cursor
        return results[:limit]

    @staticmethod
    def to_bet(obj: dict) -> Bet:
        title = obj.get("question") or obj.get("title") or ""
        desc = obj.get("description") or obj.get("criteria") or obj.get("rules") or ""
        slug = obj.get("slug")
        url = f"https://polymarket.com/market/{slug}" if slug else None
        ct_raw = obj.get("closeTime") or obj.get("endDate") or obj.get("end_time")
        close_time = iso_parse(ct_raw)
        return Bet(
            source="polymarket",
            market_id=str(obj.get("id")),
            slug=slug,
            title=title,
            description=desc,
            url=url,
            close_time=close_time,
            raw=obj,
        )

    def fetch_bets(self, limit: int) -> List[Bet]:
        rows = self.fetch_open_markets(limit=limit)
        return [self.to_bet(r) for r in rows]

