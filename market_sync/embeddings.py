import os
import json
import time
import hashlib
from typing import List, Optional
import voyageai as voyageai
from .util import now_ts

class EmbeddingCache:
    def __init__(self, conn):
        self.conn = conn

    def get(self, hash_: str, model: str) -> Optional[List[float]]:
        cur = self.conn.cursor()
        cur.execute("SELECT embedding FROM embeddings WHERE hash = ? AND model = ?", (hash_, model))
        row = cur.fetchone()
        if row:
            return json.loads(row[0])
        return None

    def set(self, hash_: str, model: str, embedding: List[float]):
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT INTO embeddings (hash, model, embedding, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(hash, model) DO UPDATE SET
              embedding=excluded.embedding,
              created_at=excluded.created_at
            """,
            (hash_, model, json.dumps(embedding), now_ts()),
        )
        self.conn.commit()

class Embedder:
    def __init__(self, model: str, cache: EmbeddingCache, api_key: Optional[str] = None, max_retries: int = 5, backoff_base: float = 0.5):
        key = api_key or os.getenv("VOYAGE_API_KEY")
        if not key:
            raise RuntimeError("VOYAGE_API_KEY not set in environment")
        self.client = voyageai.Client(api_key=key)
        self.model = model
        self.cache = cache
        self.max_retries = max_retries
        self.backoff_base = backoff_base

    @staticmethod
    def text_hash(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _embed_batch_api(self, texts: List[str]) -> List[List[float]]:
        delay = self.backoff_base
        for attempt in range(self.max_retries):
            try:
                resp = self.client.embed(texts, model=self.model, input_type="document")
                return resp.embeddings
            except Exception:
                if attempt == self.max_retries - 1:
                    raise
                time.sleep(delay)
                delay *= 2
        raise RuntimeError("Embedding batch failed")

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        hashes = [self.text_hash(t) for t in texts]
        cached_vectors = {}
        missing_idx = []
        missing_texts = []
        for i, (h, t) in enumerate(zip(hashes, texts)):
            v = self.cache.get(h, self.model)
            if v is None:
                missing_idx.append(i)
                missing_texts.append(t)
            else:
                cached_vectors[i] = v
        if missing_texts:
            new_vecs = self._embed_batch_api(missing_texts)
            for i, vec in zip(missing_idx, new_vecs):
                self.cache.set(hashes[i], self.model, vec)
                cached_vectors[i] = vec
        return [cached_vectors[i] for i in range(len(texts))]

    def embed_text(self, text: str) -> List[float]:
        return self.embed_texts([text])[0]