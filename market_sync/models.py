from dataclasses import dataclass, field
from typing import Optional, List
import hashlib

@dataclass(slots=True)
class Bet:
    source: str
    market_id: str
    slug: Optional[str]
    title: str
    description: Optional[str]
    url: Optional[str]
    close_time: Optional[str]
    raw: dict = field(default_factory=dict)
    text_for_embedding: str = field(init=False)
    text_hash: str = field(init=False)
    embedding: Optional[List[float]] = None

    def __post_init__(self):
        desc = (self.description or "").strip()
        pieces = [self.title.strip()]
        if desc:
            pieces.append(desc)
        self.text_for_embedding = "\n\n".join(pieces)
        self.text_hash = hashlib.sha256(self.text_for_embedding.encode("utf-8")).hexdigest()

