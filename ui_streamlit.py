# ui_streamlit.py
import os
import time
from typing import Dict, List, Tuple, Optional
import streamlit as st

from dotenv import load_dotenv
from market_sync.config import DB_PATH, VOYAGE_MODEL
from market_sync.db import open_db
from market_sync.embeddings import EmbeddingCache, Embedder
from market_sync.repo import Repo
from market_sync.clients.polymarket import PolymarketClient
from market_sync.sync import sync_source
from market_sync.match import cosine

# ---------- Page setup ----------
st.set_page_config(
    page_title="Market Sync — Live",
    page_icon="🧭",
    layout="wide",
)

# Small CSS polish for cardy look + split panes
st.markdown("""
<style>
/* --- Design tokens ------------------------------------------------------- */
:root{
  --card-bg:#ffffff;
  --card-border:#E5E7EB;            /* slate-200 */
  --text-primary:#0F172A;           /* slate-900 */
  --text-secondary:#334155;         /* slate-700 */
  --pill-bg:#F8FAFC;                /* slate-50 */
  --pill-border:#E2E8F0;            /* slate-200 */
  --shadow:0 2px 12px rgba(15,23,42,.06);
  --hover-border:#94A3B8;           /* slate-400 */
}

@media (prefers-color-scheme: dark){
  :root{
    --card-bg:#1f2430;              /* softer than #0f1116 */
    --card-border:#3B4151;          /* slate-ish */
    --text-primary:#F8FAFC;         /* near-white */
    --text-secondary:#CBD5E1;       /* slate-300 */
    --pill-bg:#131722;              /* very dark */
    --pill-border:#3B4151;
    --shadow:0 2px 16px rgba(0,0,0,.45);
    --hover-border:#64748B;         /* slate-500 */
  }
}

/* --- Layout polish ------------------------------------------------------- */
.main .block-container { padding-top: 1.2rem; padding-bottom: 2rem; max-width: 1400px; }
.grid { display:grid; gap:12px; grid-template-columns: repeat(4, minmax(0, 1fr)); }
@media (max-width: 1300px) { .grid { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
@media (max-width: 1000px) { .grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }

/* --- Cards --------------------------------------------------------------- */
.card {
  border-radius:16px; padding:14px 16px; height:100%;
  background:var(--card-bg);
  border:1px solid var(--card-border);
  box-shadow: var(--shadow);
  transition: transform .08s ease, box-shadow .08s ease, border-color .2s ease;
  color:var(--text-primary);
}
.card:hover { transform: translateY(-1px); box-shadow: 0 6px 22px rgba(0,0,0,.08); border-color: var(--hover-border); }

.card .title { font-weight:600; line-height:1.2; font-size:0.98rem; color:var(--text-primary); }
.card .desc  { color:var(--text-secondary); font-size:.88rem; margin-top:.45rem; max-height:5.2em; overflow:hidden; }
.card .meta  { display:flex; gap:.5rem; align-items:center; margin-top:.65rem; color:var(--text-secondary); font-size:.8rem; }
.card .pill  {
  padding:.18rem .55rem; border-radius:999px;
  border:1px solid var(--pill-border); background:var(--pill-bg); color:var(--text-secondary);
}

/* --- Section headers ----------------------------------------------------- */
.badge {
  display:inline-flex; align-items:center; gap:.5rem;
  padding:.35rem .6rem; border-radius:999px; font-weight:600;
  background:linear-gradient(135deg, rgba(59,130,246,.10), rgba(99,102,241,.10));
  border:1px solid rgba(99,102,241,.25); color:var(--text-primary);
}
.section-title{ display:flex; align-items:center; justify-content:space-between; gap:1rem; margin:.25rem 0 0; padding-bottom:.25rem; }
</style>
""", unsafe_allow_html=True)

# ---------- Lazy singletons in session_state ----------
def get_ctx():
    if "ctx" not in st.session_state:
        load_dotenv()
        conn = open_db(DB_PATH)
        cache = EmbeddingCache(conn)
        repo = Repo(conn)
        embedder = Embedder(model=VOYAGE_MODEL, cache=cache, api_key=os.getenv("VOYAGE_API_KEY"))
        st.session_state.ctx = {
            "conn": conn,
            "repo": repo,
            "embedder": embedder,
            "last_sync": None,
        }
    return st.session_state.ctx

CTX = get_ctx()
REPO: Repo = CTX["repo"]
EMB: Embedder = CTX["embedder"]

# ---------- Data helpers ----------
def list_sources() -> List[str]:
    rows = CTX["conn"].execute("SELECT DISTINCT source FROM bets WHERE is_active=1 ORDER BY source").fetchall()
    return [r[0] for r in rows]

def fetch_active_bets(source: str, limit: int = 500, search: str = "") -> List[Dict]:
    q = """
    SELECT source, market_id, slug, title, COALESCE(description, ''), url, COALESCE(close_time, '')
    FROM bets
    WHERE is_active=1 AND source=?
    """
    args: List = [source]
    if search:
        q += " AND (title LIKE ? OR description LIKE ?)"
        like = f"%{search}%"
        args += [like, like]
    q += " ORDER BY last_seen_at DESC LIMIT ?"
    args += [limit]
    rows = CTX["conn"].execute(q, args).fetchall()
    out = []
    for s, mid, slug, title, desc, url, close_time in rows:
        text = title.strip() + ("\n\n" + desc.strip() if desc and desc.strip() else "")
        out.append({
            "source": s, "market_id": mid, "slug": slug, "title": title, "description": desc,
            "url": url or (f"https://polymarket.com/market/{slug}" if s=="polymarket" and slug else None),
            "close_time": close_time or None, "text": text
        })
    return out

def ensure_embedding(text: str) -> List[float]:
    h = EMB.text_hash(text)
    vec = EMB.cache.get(h, EMB.model)
    if vec is None:
        vec = EMB.embed_text(text)
    return vec

def rank_similar(target_vec: List[float], candidates: List[Dict]) -> List[Tuple[Dict, float]]:
    ranked = []
    for c in candidates:
        if not c["text"]:
            continue
        vec = ensure_embedding(c["text"])
        ranked.append((c, float(cosine(target_vec, vec))))
    ranked.sort(key=lambda x: x[1], reverse=True)
    return ranked

# ---------- Actions ----------
def refresh_sources():
    pm = PolymarketClient()
    bets = pm.fetch_bets(limit=st.session_state.get("pm_limit", 500))
    new_or_changed, _, inactivated = sync_source(bets, REPO, EMB)
    CTX["last_sync"] = time.time()
    return {"new_or_changed": len(new_or_changed), "inactivated": inactivated, "count": len(bets)}

# ---------- Header ----------
st.markdown('<span class="badge">Market Sync Live UI</span>', unsafe_allow_html=True)
st.title("Two-Pane Market Explorer")

with st.sidebar:
    st.subheader("Controls")
    st.session_state.pm_limit = st.number_input("Fetch limit (Polymarket)", min_value=50, max_value=2000, value=500, step=50)
    if st.button("🔄 Refresh from sources", use_container_width=True):
        with st.spinner("Syncing Polymarket…"):
            r = refresh_sources()
        st.success(f"Refreshed • {r['count']} markets • {r['new_or_changed']} new/changed, {r['inactivated']} inactivated")
    st.write("---")
    st.caption("VOYAGE model")
    st.code(VOYAGE_MODEL)
    if CTX["last_sync"]:
        st.caption(f"Last sync: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(CTX['last_sync']))}")

# ---------- Top / bottom layout ----------
st.markdown("### Top: Polymarket")
top_search = st.text_input("Filter Polymarket by text", placeholder="Type to filter title/description…")
top_limit  = st.slider("Show up to", 20, 800, 120, step=20)
pm_bets = fetch_active_bets("polymarket", limit=top_limit, search=top_search)

# Selected state
if "selected_pm" not in st.session_state and pm_bets:
    st.session_state.selected_pm = pm_bets[0]["market_id"]

# Cards grid
st.markdown('<div class="grid">', unsafe_allow_html=True)
for bet in pm_bets:
    selected = (bet["market_id"] == st.session_state.get("selected_pm"))
    border = " style='border-color:rgba(99,102,241,.55)'" if selected else ""
    link = f"<a href='{bet['url']}' target='_blank' style='text-decoration:none;color:inherit'>🔗</a>" if bet["url"] else ""
    st.markdown(
        f"""
        <div class="card" {border}>
            <div class="title">{bet['title']}</div>
            <div class="desc">{bet['description'][:260] + ('…' if len(bet['description'])>260 else '')}</div>
            <div class="meta">
                <span class="pill">#{bet['market_id']}</span>
                <span class="pill">polymarket</span>
                {link}
            </div>
        </div>
        """, unsafe_allow_html=True
    )
    # Clickable via lightweight form button
    key = f"sel_{bet['market_id']}"
    if st.button(("✅ Selected" if selected else "Select"), key=key):
        st.session_state.selected_pm = bet["market_id"]
st.markdown('</div>', unsafe_allow_html=True)

# Find the selected top bet
selected_pm: Optional[Dict] = next((b for b in pm_bets if b["market_id"] == st.session_state.get("selected_pm")), None)

st.write("---")
st.markdown(
    '<div class="section-title"><h3>Bottom: Other sources ranked by similarity</h3></div>',
    unsafe_allow_html=True
)

sources = [s for s in list_sources() if s != "polymarket"]
if not sources:
    st.info("No other sources yet. Add another market client (e.g., Manifold, Kalshi, etc.), run a sync, and they’ll appear here.")
else:
    colA, colB = st.columns([2, 5])
    with colA:
        target_source = st.selectbox("Target source", ["All"] + sources)
        show_n = st.slider("Show top N", 10, 300, 80, step=10)
        sim_floor = st.slider("Minimum similarity", 0.0, 1.0, 0.70, step=0.01)
    with colB:
        st.markdown('<div class="controls">', unsafe_allow_html=True)
        if st.button("🔁 Recompute ranking", help="Force recompute cosine similarity"):
            pass
        st.markdown('</div>', unsafe_allow_html=True)

    # Gather bottom candidates
    cand_sources = sources if target_source == "All" else [target_source]
    candidates: List[Dict] = []
    for s in cand_sources:
        candidates.extend(fetch_active_bets(s, limit=1000, search=""))

    if not selected_pm:
        st.warning("Select a Polymarket market above to compute similarities.")
    else:
        # Compute similarity
        with st.spinner("Embedding + ranking by cosine similarity…"):
            pm_vec = ensure_embedding(selected_pm["text"])
            ranked = rank_similar(pm_vec, candidates)
            # Filter & trim
            ranked = [r for r in ranked if r[1] >= sim_floor][:show_n]

        if not ranked:
            st.info("No candidates meet the current filters.")
        else:
            # Render ranked list as cards
            st.markdown('<div class="grid">', unsafe_allow_html=True)
            for cand, score in ranked:
                link = f"<a href='{cand['url']}' target='_blank' style='text-decoration:none;color:inherit'>🔗</a>" if cand["url"] else ""
                st.markdown(
                    f"""
                    <div class="card">
                        <div class="title">{cand['title']}</div>
                        <div class="desc">{cand['description'][:260] + ('…' if len(cand['description'])>260 else '')}</div>
                        <div class="meta">
                            <span class="pill">{cand['source']}</span>
                            <span class="pill">sim: {score:.3f}</span>
                            <span class="pill">#{cand['market_id']}</span>
                            {link}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
                st.button("View", key=f"view_{cand['source']}_{cand['market_id']}")
            st.markdown('</div>', unsafe_allow_html=True)

st.caption("Tip: hit the sidebar **Refresh** after you add a new client to the codebase.")
