import os
import re
import sys
from pathlib import Path
from turtle import mode
from typing import List, Optional, Dict, Any, Tuple

import streamlit as st
from elasticsearch import Elasticsearch

# ============================================================
# PATH / IMPORT CONFIG
# ============================================================
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(PROJECT_ROOT))

from src.config import ES_HOST, INDEX_PAPERS, INDEX_TABLES, INDEX_FIGURES  # noqa

IMAGES_DIR = PROJECT_ROOT / "data" / "images"


# ============================================================
# ELASTICSEARCH SEARCH 
# ============================================================
def es_search_auto(
    es: Elasticsearch,
    index: str,
    query: str,
    fields: List[str],
    size: int = 20,
    source_filter: Optional[str] = None,
    **kwargs,  
) -> Dict[str, Any]:
    filters = []

    if source_filter:
        filters.append({"term": {"source": source_filter}})

    q = (query or "").strip()

    mode_norm = str(mode or "auto").strip().lower()

    if mode_norm == "boolean":
        tokens = tokenize_boolean(q)
        rpn = to_rpn(tokens)
        es_q = rpn_to_es_query(rpn, fields)

    elif mode_norm == "fulltext":
        es_q = {
            "multi_match": {
                "query": q,
                "fields": fields,
                "type": "best_fields",
                "operator": "and",
            }
        }

    else:
        # auto
        if looks_boolean(q):
            tokens = tokenize_boolean(q)
            rpn = to_rpn(tokens)
            es_q = rpn_to_es_query(rpn, fields)
        else:
            es_q = {
                "multi_match": {
                    "query": q,
                    "fields": fields,
                    "type": "best_fields",
                    "operator": "and",
                }
            }


    body = {
        "size": size,
        "query": {
            "bool": {
                "filter": filters,
                "must": [es_q],
            }
        }
    }
    return es.search(index=index, body=body, request_timeout=30)


# ============================================================
# PAPER TITLE LOOKUP (for table/figure cards)
# ============================================================
def get_paper_title_cached(
    es: Elasticsearch,
    paper_doc_id: str,
    cache: Dict[str, str],
) -> str:
    """
    paper_doc_id nel tuo indexing di tables/figures è: "<source>_<paper_id>".
    Qui proviamo a recuperare il titolo dal papers index in modo robusto:
      1) GET per _id (se hai indicizzato papers con lo stesso _id)
      2) fallback: search term su field "paper_id" (se paper_id contiene paper_doc_id)
    """
    if not paper_doc_id:
        return ""
    if paper_doc_id in cache:
        return cache[paper_doc_id]

    title = ""

    # (1) try by _id
    try:
        doc = es.get(index=INDEX_PAPERS, id=paper_doc_id, request_timeout=10)
        src = doc.get("_source", {}) if isinstance(doc, dict) else {}
        title = (src.get("title") or "").strip()
    except Exception:
        pass

    # (2) fallback: term on paper_id
    if not title:
        try:
            res = es.search(
                index=INDEX_PAPERS,
                body={
                    "size": 1,
                    "_source": ["title"],
                    "query": {"term": {"paper_id": paper_doc_id}},
                },
                request_timeout=10,
            )
            hits = res.get("hits", {}).get("hits", [])
            if hits:
                title = (hits[0].get("_source", {}).get("title") or "").strip()
        except Exception:
            pass

    cache[paper_doc_id] = title
    return title


# ============================================================
# PMC LOCAL IMAGE LOOKUP
# ============================================================
def normalize_pmc_folder_from_paper_id(paper_id: str) -> str:
    """
    Converte paper_id ES -> nome cartella immagini.
    Esempi:
      "pmc_PMC12693445" -> "PMC12693445"
      "PMC12693445"     -> "PMC12693445"
      "pmc_12693445"    -> "PMC12693445"
      "12693445"        -> "PMC12693445"
    """
    if not paper_id:
        return ""
    pid = str(paper_id).strip()

    m = re.search(r"(PMC\d+)", pid, flags=re.IGNORECASE)
    if m:
        return m.group(1).upper()

    if re.fullmatch(r"\d+", pid):
        return f"PMC{pid}"

    return pid


def normalize_fig_stem(figure_id: str) -> str:
    """
    Prova a ricondurre figure_id a "F<number>".
    Esempi:
      "F1" -> "F1"
      "nutrients-17-03651-f001" -> "F1"
    """
    if not figure_id:
        return ""
    fid = str(figure_id).strip()

    m = re.fullmatch(r"F(\d+)", fid, flags=re.IGNORECASE)
    if m:
        return f"F{int(m.group(1))}"

    m = re.search(r"[-_](?:f|g)(\d{3,})$", fid, flags=re.IGNORECASE)
    if m:
        return f"F{int(m.group(1))}"

    m = re.search(r"(?:^|[-_])(f|g)(\d{3,})(?:$|[-_])", fid, flags=re.IGNORECASE)
    if m:
        return f"F{int(m.group(2))}"

    return fid


def find_local_pmc_image(meta: Dict[str, Any]) -> Optional[Path]:
    paper_id = meta.get("paper_id", "")
    fig_id = meta.get("figure_id", "")
    src_name = meta.get("src")  # può essere None

    folder = normalize_pmc_folder_from_paper_id(str(paper_id))
    if not folder:
        return None

    img_folder = IMAGES_DIR / folder
    if not img_folder.exists():
        return None

    candidates = []
    short_stem = normalize_fig_stem(str(fig_id)) if fig_id else ""
    if short_stem and short_stem != fig_id:
        candidates.append(short_stem)

    if fig_id:
        candidates.append(str(fig_id))

    if src_name:
        candidates.append(Path(str(src_name)).stem)

    matches: List[Path] = []
    for stem in candidates:
        if stem:
            matches.extend(list(img_folder.glob(f"{stem}.*")))

    return matches[0] if matches else None


# ============================================================
# UI HELPERS
# ============================================================
def render_meta_if_present(label: str, value: Any):
    if value is None:
        return
    if isinstance(value, str) and not value.strip():
        return
    if isinstance(value, list) and len(value) == 0:
        return
    st.markdown(f"**{label}:** {value}")


def render_card(
    kind: str,
    score: float,
    src: Dict[str, Any],
    es: Elasticsearch,
    paper_title_cache: Dict[str, str],
):
    source = (src.get("source") or "UNK").lower()
    paper_doc_id = src.get("paper_id") or ""  # per tables/figures è <source>_<paper_id>
    if kind == "figure" and source == "arxiv":
        fig_url = (src.get("figure_url") or "").strip()
        if not fig_url:
            return

    paper_title = ""
    if kind in ("table", "figure") and paper_doc_id:
        paper_title = get_paper_title_cached(es, paper_doc_id, paper_title_cache)

    # --- titolo card ---
    if kind == "paper":
        title = src.get("title") or "(no title)"
        icon = "📄"
    elif kind == "table":
        title = paper_title or "(paper title non trovato)"
        icon = "📊"
    else:
        title = paper_title or "(paper title non trovato)"
        icon = "🖼️"

    with st.container():
        col1, col2 = st.columns([0.82, 0.18])
        with col1:
            st.markdown(f"### {icon} {title}")
        with col2:
            st.markdown(f"`score: {score:.3f}`")

        # --- sotto-intestazione: info oggetto ---
        if kind == "table":
            st.markdown(f"**Oggetto:** `table_id={src.get('table_id', 'N/A')}`  |  **paper_doc_id:** `{paper_doc_id}`")
        elif kind == "figure":
            st.markdown(f"**Oggetto:** `figure_id={src.get('figure_id', 'N/A')}`  |  **paper_doc_id:** `{paper_doc_id}`")
        elif kind == "paper":
            render_meta_if_present("paper_id", src.get("paper_id"))

        render_meta_if_present("source", src.get("source"))
        render_meta_if_present("date", src.get("date"))

        if kind == "paper":
            authors = src.get("authors")
            if isinstance(authors, list):
                render_meta_if_present("authors", ", ".join(authors))
            else:
                render_meta_if_present("authors", authors)

        # ... (il resto della tua render_card resta uguale

        # Preview
        if kind == "paper":
            ab = (src.get("abstract") or "").strip()
            if ab:
                st.markdown("**Abstract**")
                st.write(ab[:700] + ("..." if len(ab) > 700 else ""))
        else:
            cap = (src.get("caption") or "").strip()
            if cap:
                st.markdown("**Caption**")
                st.write(cap)




        # Mentions + Context
        mentions = src.get("mentions", [])
        if isinstance(mentions, list) and mentions:
            with st.expander(f"📌 Mentions ({len(mentions)})"):
                for m in mentions[:30]:
                    st.write(f"- {m}")

        ctx = src.get("context_paragraphs", [])
        if isinstance(ctx, list) and ctx:
            with st.expander(f"🌐 Context paragraphs ({len(ctx)})"):
                for p in ctx[:30]:
                    st.write(f"- {p}")

        # Table rendering
        if kind == "table":
            html_content = src.get("table_html")
            body_txt = src.get("body") or ""
            with st.expander("🔎 Visualizza tabella"):
                if isinstance(html_content, str) and html_content.strip():
                    st.components.v1.html(
                        f"<div style='overflow-x:auto; font-family:sans-serif;'>{html_content}</div>",
                        height=360,
                        scrolling=True,
                    )
                else:
                    st.write(body_txt[:2500] + ("..." if len(body_txt) > 2500 else ""))

        # Figure rendering
        if kind == "figure":
            fig_url = (src.get("figure_url") or "").strip()

            if source == "arxiv":
                label = "ar5iv (remoto)" if "ar5iv.labs.arxiv.org" in (src.get("doc_url") or "") else "arXiv (remoto)"
                if fig_url:
                    try:
                        st.image(fig_url, caption=label, width=700)
                    except Exception:
                        st.error("Errore caricamento immagine arXiv/ar5iv remota.")
                if not fig_url:
                    return  # <-- esce da render_card, quindi non viene mostrato nulla

                try:
                    label = "ar5iv (remoto)" if "ar5iv.labs.arxiv.org" in (src.get("doc_url") or "") else "arXiv (remoto)"
                    st.image(fig_url, caption=label, width=700)
                except Exception:
                    return 


            else:
                # PMC: locale -> remoto
                local = find_local_pmc_image(src)
                if local:
                    st.image(str(local), caption=f"PMC (locale): {local.name}", width=700)
                elif fig_url:
                    st.warning("Immagine non trovata localmente: provo remoto.")
                    clean_url = fig_url.replace(".jpg.jpg", ".jpg")
                    try:
                        st.image(clean_url, caption="PMC (remoto)", width=700)
                    except Exception:
                        st.error("Errore caricamento immagine PMC remota.")
                else:
                    st.info("Figura PMC senza URL e senza immagine locale.")

        # Link
        #url = src.get("url")
        doc_url = src.get("doc_url") or src.get("url")
        if doc_url:
            st.link_button("Apri documento", doc_url)

        st.divider()

BOOL_OPS = {"AND", "OR", "NOT"}

def looks_boolean(q: str) -> bool:
    if not q:
        return False
    # basta che contenga AND/OR/NOT come token oppure parentesi
    return bool(re.search(r"\b(AND|OR|NOT)\b", q, flags=re.IGNORECASE)) or ("(" in q) or (")" in q)

def tokenize_boolean(q: str) -> List[str]:
    """
    Tokenizza:
      - "frasi tra virgolette"
      - AND/OR/NOT
      - parentesi
      - parole/termini
    """
    tokens = []
    i = 0
    n = len(q)
    while i < n:
        c = q[i]
        if c.isspace():
            i += 1
            continue
        if c in "()":
            tokens.append(c)
            i += 1
            continue
        if c == '"':
            j = i + 1
            while j < n and q[j] != '"':
                j += 1
            phrase = q[i+1:j] if j < n else q[i+1:]
            tokens.append(f'"{phrase}"')
            i = j + 1 if j < n else n
            continue

        # parola / operatore
        j = i
        while j < n and (not q[j].isspace()) and q[j] not in "()":
            j += 1
        tok = q[i:j]
        tokens.append(tok)
        i = j
    return tokens

def to_rpn(tokens: List[str]) -> List[str]:
    """
    Shunting-yard: NOT > AND > OR
    """
    prec = {"NOT": 3, "AND": 2, "OR": 1}
    out = []
    stack = []

    def is_op(t: str) -> bool:
        return t.upper() in BOOL_OPS

    for t in tokens:
        tu = t.upper()
        if t == "(":
            stack.append(t)
        elif t == ")":
            while stack and stack[-1] != "(":
                out.append(stack.pop())
            if stack and stack[-1] == "(":
                stack.pop()
        elif is_op(t):
            # NOT è unario: gestiamo comunque come operatore con precedenza più alta
            while stack and stack[-1] != "(" and stack[-1].upper() in BOOL_OPS and prec[stack[-1].upper()] >= prec[tu]:
                out.append(stack.pop())
            stack.append(tu)
        else:
            out.append(t)

    while stack:
        out.append(stack.pop())
    return out

def term_query(term: str, fields: List[str]) -> Dict[str, Any]:
    t = (term or "").strip()

    is_phrase = t.startswith('"') and t.endswith('"') and len(t) >= 2
    if is_phrase:
        phrase = t[1:-1].strip()
        if not phrase:
            return {"match_all": {}}

        # Phrase match su più campi
        return {
            "multi_match": {
                "query": phrase,
                "fields": fields,
                "type": "phrase",
                "slop": 0,  # metti 1-2 se vuoi tollerare piccole variazioni
            }
        }

    # Termine singolo (non tra virgolette)
    return {
        "multi_match": {
            "query": t,
            "fields": fields,
            "type": "best_fields",
            "operator": "and",
        }
    }


def combine_and(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    return {"bool": {"must": [a, b]}}

def combine_or(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    return {"bool": {"should": [a, b], "minimum_should_match": 1}}

def apply_not(a: Dict[str, Any]) -> Dict[str, Any]:
    return {"bool": {"must_not": [a]}}

def rpn_to_es_query(rpn: List[str], fields: List[str]) -> Dict[str, Any]:
    stack: List[Dict[str, Any]] = []
    for t in rpn:
        tu = t.upper()
        if tu == "NOT":
            if not stack:
                continue
            a = stack.pop()
            stack.append(apply_not(a))
        elif tu in ("AND", "OR"):
            if len(stack) < 2:
                continue
            b = stack.pop()
            a = stack.pop()
            stack.append(combine_and(a, b) if tu == "AND" else combine_or(a, b))
        else:
            stack.append(term_query(t, fields))

    if not stack:
        # fallback sicuro
        return {"match_all": {}}
    # se ci sono più termini senza operatori, comportati come AND
    q = stack[0]
    for extra in stack[1:]:
        q = combine_and(q, extra)
    return q

# ============================================================
# STREAMLIT APP
# ============================================================
st.set_page_config(page_title="Scientific Search", layout="wide", page_icon="🔬")
st.title("🔬 Scientific Research Engine")
st.markdown("Ricerca unificata su **ArXiv (HTML)** e **PubMed Central (XML)** indicizzati in Elasticsearch.")

# ES connection
try:
    es = Elasticsearch(ES_HOST)
    if not es.ping():
        st.error(f"Impossibile connettersi a Elasticsearch su {ES_HOST}")
        st.stop()
except Exception as e:
    st.error(f"Errore connessione Elasticsearch: {e}")
    st.stop()

paper_title_cache: Dict[str, str] = {}

# Sidebar filters
with st.sidebar:
    st.header("🔍 Impostazioni ricerca")

    source_sel = st.selectbox("Sorgente", ["(Tutte)", "arxiv", "pmc"], index=0)
    source_filter = None if source_sel == "(Tutte)" else source_sel

    st.markdown("---")
    st.subheader("Modalità query")

    query_mode = st.radio(
        "Tipo di query",
        ["Auto", "Full-text", "Boolean"],
        index=0,
        help="Auto: riconosce AND/OR/NOT e parentesi. Full-text: ricerca normale. Boolean: usa sempre la logica booleana.",
    )

    query_mode_map = {
        "Auto": "auto",
        "Full-text": "fulltext",
        "Boolean": "boolean",
    }
    st.markdown("---")
    st.subheader("Risultati")
    #operator = st.selectbox("Operator", ["and", "or"], index=0, help="and = più preciso; or = più recall")
    topk = st.slider("Risultatu", 5, 50, 15)
    #size_each = st.slider("Cross-search: risultati per indice", 5, 40, 20)

    st.markdown("---")
    st.subheader("Scelta fields ")

    # ---- Dropdown fields choices with ALL ----
    PAPER_FIELD_OPTIONS = [
        "ALL (tutti i fields)",
        "title",
        "abstract",
        "full_text",
        "authors",
    ]
    TABLE_FIELD_OPTIONS = [
        "ALL (tutti i fields)",
        "caption",
        "body",
        "mentions",
        "context_paragraphs",
    ]
    FIG_FIELD_OPTIONS = [
        "ALL (tutti i fields)",
        "caption",
        "mentions",
        "context_paragraphs",
    ]

    paper_fields_sel = st.multiselect("Papers fields", PAPER_FIELD_OPTIONS, default=["ALL (tutti i fields)"])
    table_fields_sel = st.multiselect("Tables fields", TABLE_FIELD_OPTIONS, default=["ALL (tutti i fields)"])
    fig_fields_sel = st.multiselect("Figures fields", FIG_FIELD_OPTIONS, default=["ALL (tutti i fields)"])

def build_fields(selected: List[str], kind: str) -> List[str]:
    """
    Converte la selezione utente in lista fields ES con pesi.
    """
    sel = set(selected or [])
    if "ALL (tutti i fields)" in sel or len(sel) == 0:
        if kind == "paper":
            return ["title^3", "abstract^2", "full_text", "authors"]
        if kind == "table":
            return ["caption^3", "body^2", "mentions", "context_paragraphs"]
        if kind == "figure":
            return ["caption^3", "mentions", "context_paragraphs"]

    fields = []
    if kind == "paper":
        if "title" in sel: fields.append("title^3")
        if "abstract" in sel: fields.append("abstract^2")
        if "full_text" in sel: fields.append("full_text")
        if "authors" in sel: fields.append("authors")
        return fields or ["title^3", "abstract^2", "full_text"]

    if kind == "table":
        if "caption" in sel: fields.append("caption^3")
        if "body" in sel: fields.append("body^2")
        if "mentions" in sel: fields.append("mentions")
        if "context_paragraphs" in sel: fields.append("context_paragraphs")
        return fields or ["caption^3", "body^2", "mentions"]

    if kind == "figure":
        if "caption" in sel: fields.append("caption^3")
        if "mentions" in sel: fields.append("mentions")
        if "context_paragraphs" in sel: fields.append("context_paragraphs")
        return fields or ["caption^3", "mentions"]

    return ["caption^3"]


papers_fields = build_fields(paper_fields_sel, "paper")
tables_fields = build_fields(table_fields_sel, "table")
figures_fields = build_fields(fig_fields_sel, "figure")

# Main controls
query = st.text_input("Query", placeholder="es. entity resolution", value="")
search_mode = st.radio(
    "Cerca in:",
    ["Cross-Search", "Solo Articoli", "Solo Tabelle", "Solo Figure"],
    horizontal=True,
)

if not query.strip():
    st.info("Inserisci una query per iniziare.")
    st.stop()

if st.button("Cerca"):
    with st.spinner("Ricerca in corso..."):

        if search_mode == "Solo Articoli":
            res = es_search_auto(
                es=es,
                index=INDEX_PAPERS,
                query=query,
                fields=papers_fields,
                size=topk,
                source_filter=source_filter,
                
            )
            hits = res.get("hits", {}).get("hits", [])
            st.success(f"Trovati {len(hits)} articoli.")
            for h in hits:
                render_card("paper", float(h.get("_score", 0.0)), h.get("_source", {}), es, paper_title_cache)

        elif search_mode == "Solo Tabelle":
            res = es_search_auto(
                es=es,
                index=INDEX_TABLES,
                query=query,
                fields=tables_fields,
                size=topk,
                source_filter=source_filter,
                
            )
            hits = res.get("hits", {}).get("hits", [])
            st.success(f"Trovate {len(hits)} tabelle.")
            for h in hits:
                render_card("table", float(h.get("_score", 0.0)), h.get("_source", {}), es, paper_title_cache)

        elif search_mode == "Solo Figure":
            res = es_search_auto(
                es=es,
                index=INDEX_FIGURES,
                query=query,
                fields=figures_fields,
                size=topk,
                source_filter=source_filter,
                
            )
            hits = res.get("hits", {}).get("hits", [])
            st.success(f"Trovate {len(hits)} figure.")
            for h in hits:
                render_card("figure", float(h.get("_score", 0.0)), h.get("_source", {}), es, paper_title_cache)

        else:
            papers_res = es_search_auto(
                es=es,
                index=INDEX_PAPERS,
                query=query,
                fields=papers_fields,
                size=topk,
                source_filter=source_filter,
                
            )
            tables_res = es_search_auto(
                es=es,
                index=INDEX_TABLES,
                query=query,
                fields=tables_fields,
                size=topk,
                source_filter=source_filter,
                
            )
            figs_res = es_search_auto(
                es=es,
                index=INDEX_FIGURES,
                query=query,
                fields=figures_fields,
                size=topk,
                source_filter=source_filter,
                
            )

            papers_hits = papers_res.get("hits", {}).get("hits", [])
            tables_hits = tables_res.get("hits", {}).get("hits", [])
            figs_hits = figs_res.get("hits", {}).get("hits", [])

            merged: List[Tuple[str, float, Dict[str, Any]]] = []
            for h in papers_hits:
                merged.append(("paper", float(h.get("_score", 0.0)), h.get("_source", {})))
            for h in tables_hits:
                merged.append(("table", float(h.get("_score", 0.0)), h.get("_source", {})))
            for h in figs_hits:
                merged.append(("figure", float(h.get("_score", 0.0)), h.get("_source", {})))

            merged.sort(key=lambda x: x[1], reverse=True)
            merged = merged[:topk]

            st.success(
                f"Cross-Search: papers={len(papers_hits)}, tables={len(tables_hits)}, figures={len(figs_hits)} → mostrati {len(merged)}"
            )

            for kind, sc, src in merged:
                render_card(kind, sc, src, es, paper_title_cache)
