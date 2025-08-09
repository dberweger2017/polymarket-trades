import requests, pandas as pd
from sentence_transformers import SentenceTransformer
import faiss, numpy as np

# 1) Ingest
pm = requests.get("https://gamma-api.polymarket.com/markets?limit=1000").json()  # Gamma REST; paginate if needed
def flatten_polymarket(m):
    outs=[]
    for o in m.get("outcomes", []):
        outs.append({
            "source":"polymarket",
            "market_id": m["id"],
            "question": m.get("question") or m.get("title"),
            "notes": m.get("description") or "",
            "close_time": m.get("closeTime"),
            "outcome": o.get("name","YES"),
            "price": o.get("price"),    # probability in [0,1] typically
            "url": f'https://polymarket.com/market/{m.get("slug","")}'
        })
    return outs

pm_rows = sum([flatten_polymarket(m) for m in pm.get("data", pm)], [])