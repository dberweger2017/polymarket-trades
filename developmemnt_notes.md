## Development notes

### Provider choices (LLM and embeddings)
- **Context**: Single-provider (OpenAI) is simplest; DeepSeek does not expose an embeddings API yet.
- **Decision (current)**: Use VoyageAI for embeddings; leave the LLM provider pluggable (likely OpenAI later when needed).
- **Why**:
  - **Cost/quality**: `voyage-3.5` offers strong semantic performance at a good price.
  - **Separation of concerns**: Embeddings and LLM can evolve independently; switching the LLM later does not affect stored vectors.
  - **Caching**: With a local cache, embedding costs are paid once per unique text.

### Data model and storage
- **SQLite with WAL** in `market_sync/db.py` (`PRAGMA journal_mode=WAL`, `synchronous=NORMAL`).
  - **Why**: Simple, zero-deps, good concurrent read performance; durable enough for this workload.

- **Tables**:
  - `embeddings(hash, model, embedding, created_at)`
    - **Why**: Key by stable SHA-256 of text plus `model` so different models can coexist. Store embedding as JSON for simplicity.
  - `bets(source, market_id, slug, title, description, url, close_time, text_hash, is_active, first_seen_at, last_seen_at, inactive_at)`
    - **Why**: `text_hash` detects content changes quickly; `is_active` + timestamps let us track lifecycle as markets open/close without deleting rows.
  - `events(id, title, created_at, updated_at)` and `event_aliases(event_id, source, market_id, text_hash, similarity, llm_confidence, method, …)`
    - **Why**: Normalize cross-source "same event" grouping. `event_aliases` stores provenance (`similarity`, `llm_confidence`, `method`) for auditability and re-scoring.
  - `event_candidates(pair_key, a_source, a_market_id, b_source, b_market_id, similarity, reason, status, created_at)`
    - **Why**: Queue borderline matches for review. `pair_key` prevents duplicate work.
  - **Indexes**: on `bets(text_hash)`, `bets(is_active)`, and `event_aliases(event_id)` for fast lookups.

### Text preparation and hashing
- **Bet text**: `title` + two newlines + `description` (if present). Set in `market_sync/models.py`.
  - **Why**: Keeps title salient while preserving description context; the delimiter helps the embedder capture structure.
- **Hashing**: SHA-256 of the final text; stored as `text_hash` on `bets` and used as the key in `embeddings`.
  - **Why**: Stable, content-addressed caching independent of `market_id` or source.

### Embeddings pipeline (`market_sync/embeddings.py`)
- **Cache-first** flow: check `EmbeddingCache` by `(hash, model)`; only call API for misses.
  - **Why**: Avoids duplicate API spend; makes re-syncs cheap.
- **VoyageAI client**: `input_type="document"`, retries with exponential backoff.
  - **Why**: "document" suits retrieval-style representations; backoff handles rate limits/transient errors.

### Sync pipeline (`market_sync/sync.py`)
- Upsert all fetched bets, collect `active_ids`, then `mark_inactive_except` for the source.
  - **Why**: One pass marks removed/closed markets inactive without needing delete semantics.
- Embed only texts that are new or changed and not already cached.
  - **Why**: Minimizes API calls and latency.

### Matching and linking (`market_sync/match.py`)
- **Similarity**: Cosine on embeddings.
- **Thresholds**: `high=0.90` auto-link; `low=0.83` queue for review.
  - **Why**: Conservative auto-linking to minimize false positives; still capture promising pairs for human/LLM review.
- **Bounding work**: `max_pairs_per_new` caps cross-source comparisons per new item.
  - **Why**: Prevents worst-case quadratic blow-ups on large syncs.
- **Event creation/linking**: If neither bet has an event, create one and link both; otherwise attach to existing.
  - **Why**: Ensures a single canonical event aggregates aliases as evidence accrues.

### Source client: Polymarket (`market_sync/clients/polymarket.py`)
- **Robust HTTP**: Session with retries/backoff for `GET` and a custom `User-Agent`.
  - **Why**: Resilient to 429/5xx and polite to the upstream.
- **Pagination**: Cursor-based; flexible extraction of `data` arrays and `nextCursor` variants.
  - **Why**: Handles API shape drift without frequent code changes.
- **Normalization**: Map market objects to `Bet`; parse `close_time` via `iso_parse` supporting ms/seconds/ISO and normalizing to UTC.
  - **Why**: Keep downstream code format-agnostic and consistent.

### Utilities and configuration
- **Config** (`market_sync/config.py`): `GAMMA_BASE`, `VOYAGE_MODEL`, `DB_PATH`, `USER_AGENT` via env with sane defaults.
  - **Why**: Make behavior configurable without code edits; safe defaults aid local dev.
- **Time/parse utils** (`market_sync/util.py`): `now_ts()` and `iso_parse()` with robust handling and UTC normalization.
  - **Why**: Consistency across storage and logs; resilience to upstream date formats.

### Entry points
- `main.py`: Minimal script for quick manual runs (fetch + sync Polymarket).
- `market_sync/run_once.py`: Full run with logging, all sources, sync, then matching. Prints a compact JSON summary (linked/queued).
  - **Why**: One-shot operation suitable for cron/k8s job runners and easy observability.

### Near-term plan
- Add LLM-assisted re-scoring/explanations for `event_candidates` (uses `llm_confidence` and `method` fields already in schema).
- Add more sources and unify their clients behind a common interface.
- Build a simple reviewer UI for triaging queued pairs.

### Environment keys
- `VOYAGE_API_KEY` (required)
- Optional: `GAMMA_BASE`, `VOYAGE_MODEL` (default `voyage-3.5`), `DB_PATH`, `USER_AGENT`, `LOG_LEVEL`.
