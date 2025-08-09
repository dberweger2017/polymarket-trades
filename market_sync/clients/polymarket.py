from typing import List, Optional
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from ..config import GAMMA_BASE, USER_AGENT
from ..models import Bet
from ..util import iso_parse

class PolymarketClient:
    def __init__(self, base: str = GAMMA_BASE, session: Optional[requests.Session] = None, verify: bool | str = True):
        self.base = base.rstrip("/")
        self.sess = session or self._build_session()
        self.verify = verify

    def _build_session(self) -> requests.Session:
        s = requests.Session()
        retry = Retry(total=5, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504], allowed_methods=frozenset(["GET"]))
        adapter = HTTPAdapter(max_retries=retry)
        s.mount("https://", adapter)
        s.mount("http://", adapter)
        s.headers.update({"User-Agent": USER_AGENT})
        return s

    def _extract_items_and_cursor(self, payload):
        items = []
        next_cursor = None
        if isinstance(payload, list):
            items = payload
        elif isinstance(payload, dict):
            data = payload.get("data")
            if isinstance(data, list):
                items = data
            elif isinstance(data, dict) and isinstance(data.get("data"), list):
                items = data["data"]
            elif isinstance(payload.get("markets"), list):
                items = payload["markets"]
            meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
            for key in ("nextCursor", "next_cursor", "next", "cursor"):
                if payload.get(key):
                    next_cursor = payload[key]
                    break
                if meta.get(key):
                    next_cursor = meta[key]
                    break
        return items, next_cursor

    def fetch_open_markets(self, limit: int = 1000) -> List[dict]:
        results: List[dict] = []
        cursor = None
        while len(results) < limit:
            params = {"limit": min(1000, max(1, limit - len(results))), "state": "open"}
            if cursor:
                params["cursor"] = cursor
            r = self.sess.get(f"{self.base}/markets", params=params, timeout=30, verify=self.verify)
            r.raise_for_status()
            payload = r.json()
            items, next_cursor = self._extract_items_and_cursor(payload)
            if not items:
                break
            results.extend(items)
            if not next_cursor:
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