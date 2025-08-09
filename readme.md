
# Market Sync

A compact pipeline for ingesting **open** prediction markets (starting with Polymarket), normalizing them to a common schema, embedding and caching their text, and proposing cross‑source links by cosine similarity. An optional two‑pane UI lets you explore Polymarket markets on top and rank other sources below by semantic similarity.

---

## Highlights

- **Source adapters**: Resilient Polymarket client with retries, cursor pagination, and server‑side filtering to **open** markets.
- **Data model**: `Bet` dataclass with a stable `text_hash`. SQLite schema for `bets`, `embeddings`, `events`, `event_aliases`, and a `event_candidates` review queue.
- **Embeddings**: Voyage AI embeddings with an on‑disk cache keyed by SHA‑256; resume‑safe **backfill** so Ctrl‑C during embedding does not strand items.
- **Matching**: Cosine‑similarity matcher with high/low thresholds for auto‑linking vs. queuing.
- **Sync UX**: Optional `tqdm` progress shows per‑bet status: insert / update / skip, and embedding phase updates.
- **Two‑pane UI**: Launch with `--ui`. Click a Polymarket card (top) and the bottom pane ranks other sources by embedding similarity, with filters and refresh.

---

## Architecture (at a glance)

```mermaid
flowchart LR
  subgraph Sources
    PM[Polymarket\n(open markets)]
    S2[Other markets\n(Manifold/Kalshi/...)]
  end

  PM --> SYNC
  S2 --> SYNC

  subgraph Core
    SYNC[Sync Layer\n(fetch + normalize)]
    DB[(SQLite Repo\nbets/events/aliases)]
    CACHE[(Embedding Cache\nhash -> vector)]
    MATCH[Matcher\n(cosine; auto-link/queue)]
  end

  SYNC --> DB
  DB --> CACHE
  CACHE -->|miss| EMB[Embedding Provider\n(Voyage 3.5 / 3.5-lite)]
  EMB --> CACHE
  DB --> MATCH
  MATCH --> UI[Two-Pane UI (--ui)]
  UI --> DB
```

**Rendered diagrams** (PNG):

- System architecture: https://github.com/dberweger2017/polymarket-trades/blob/main/img/market_sync_architecture.png?raw=true
- Embedding cost comparison: https://github.com/dberweger2017/polymarket-trades/blob/main/img/embedding_prices.png?raw=true

---

## Quick start

```bash
# 1) Install
pip install -r requirements.txt
# or minimally:
pip install requests python-dotenv voyageai tqdm streamlit

# 2) Configure environment
export VOYAGE_API_KEY=your_key_here
# optional:
export DB_PATH=embeddings_cache.sqlite
export LOG_LEVEL=INFO
export VOYAGE_MODEL=voyage-3.5

# 3) Run a one-off sync (with progress)
python main.py --progress

# 4) Launch the UI
python main.py --ui
```

**Notes**

- The Polymarket client requests **open** markets on the server using the Gamma API parameters (`active=true`, `closed=false`, `archived=false`).
- If a previous run was interrupted during embedding, the next run will **backfill missing embeddings** automatically (no need to delete SQLite).

---

## Repository layout

```
market_sync/
  clients/
    polymarket.py      # Gamma API client (open markets)
  embeddings.py        # Voyage client + on-disk cache
  db.py                # SQLite schema + connection
  models.py            # Bet dataclass
  repo.py              # CRUD + linking + queueing
  sync.py              # Upsert + embed pipeline (tqdm-aware, resume-safe)
  match.py             # Cosine matcher & event linking
  util.py              # Timestamps + ISO parsing
  config.py            # Env-configured constants
run_once.py            # Scriptable one-shot sync
main.py                # CLI entry; --ui and --progress support
ui_streamlit.py        # Optional two-pane UI (Streamlit)
```

---

## Configuration

Environment variables (see `market_sync/config.py`):

| Variable         | Default                            | Purpose                        |
|------------------|------------------------------------|--------------------------------|
| `VOYAGE_API_KEY` | —                                  | Required for Voyage embeddings |
| `VOYAGE_MODEL`   | `voyage-3.5`                       | Embedding model                |
| `DB_PATH`        | `embeddings_cache.sqlite`          | SQLite path                    |
| `GAMMA_BASE`     | `https://gamma-api.polymarket.com` | Polymarket API base            |
| `USER_AGENT`     | `market-sync/1.0`                  | Requests UA                    |
| `LOG_LEVEL`      | `INFO`                             | Python logging level           |

Runtime toggles:

- `--progress` or `PROGRESS=1` to enable `tqdm` bars during sync.
- Backfill is enabled by default; pass `--no-backfill` to embed only new/changed items.

---

## How syncing works

1. **Fetch** markets from each source adapter. The Polymarket adapter requests **open** markets using `active=true`, `closed=false`, `archived=false` and paginates with cursors.
2. **Normalize** into `Bet`, compute `text_hash` of `title + description`.
3. **Upsert** into SQLite (`insert` / `update` / `skip`).
4. **Embed** any texts whose hash is missing from the cache. If a previous run was interrupted, backfill scans current active bets and finishes pending vectors.
5. **Match** across sources by cosine similarity:
   - `>= high` (e.g., 0.90): auto-link into events
   - `>= low` and `< high` (e.g., 0.83): queue for human review

With `--progress`, the primary bar shows inserts/updates/skips; the second bar shows per‑bet embedding progress.

---

## UI

Launch with:

```bash
python main.py --ui
```

Top pane lists Polymarket markets (filterable). Selecting a card computes or loads its embedding. The bottom pane ranks markets from other sources by **embedding similarity** to the selected item. A sidebar control lets you refresh to pull and sync again.

---

## Model providers and pricing

The project is provider‑agnostic and currently uses **Voyage AI** by default. Alternatives such as **OpenAI** or **Jina AI** can be integrated by swapping the embedding client.

| Provider | Representative models | Indicative price (USD / 1M tokens) | Notes |
|---------|------------------------|-------------------------------------|-------|
| Voyage  | `voyage-3.5-lite`      | 0.02                                | Fast and cost‑efficient for large backfills |
| Voyage  | `voyage-3.5`           | 0.06                                | Higher quality general embedding |
| OpenAI  | `text-embedding-3-small` | 0.02                              | Widely adopted, easy migration path |
| OpenAI  | `text-embedding-3-large` | 0.13                              | Higher‑dimensional embedding |
| Jina AI | Various                 | Varies                              | Offers hosted and on‑prem options |

**Important**: Prices above are indicative. Always verify on the providers’ official pricing pages before production use.

See also: /mnt/data/embedding_prices.png

---

## Roadmap

1. Second source adapter (e.g., Manifold/Kalshi) so the bottom pane showcases real cross‑venue matches.
2. Human‑in‑the‑loop actions in the UI: “Link these two” → `Repo.link_bet_to_event`; “Queue for review” → `Repo.queue_pair`.
3. Reranking for the top‑N candidates using a rerank API to boost precision before auto‑linking.
4. Scalability: add ANN (FAISS/ScaNN) for candidate recall; keep SQLite as the source of truth.
5. Observability: counters for new/changed, auto‑links, queued pairs, embed misses, and similarity distributions.

---

## Polymarket specifics

Use the Gamma API `GET /markets` with `active=true`, `closed=false`, and optionally `archived=false` to fetch **open** markets. This works well with cursor‑based pagination.

---

## Troubleshooting

- Interrupted mid‑embed: re‑run the sync. The backfill step detects missing vectors and completes them; no need to delete the SQLite file.
- No candidates in the UI: add another source adapter and run refresh.
- Foreign keys: SQLite enforces FKs only with `PRAGMA foreign_keys=ON`. If you rely on enforcement, enable the pragma at connection time.

---

## Security and privacy

Only market metadata and embedding vectors are stored in SQLite. Embedding providers receive the text you choose to embed. Review provider policies and add a redaction layer if required.

---

## License

Choose a license that matches your intended distribution and contribution model (e.g., MIT or Apache‑2.0).