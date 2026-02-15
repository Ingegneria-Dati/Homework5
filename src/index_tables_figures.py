"""Indicizza tabelle e figure come documenti di prima classe, con context:
- mentions: paragrafi che citano direttamente Table/Figure + id
- context_paragraphs: paragrafi 'simili' a caption/body usando more_like_this su INDEX_PARAGRAPHS,
  filtrati per paper_id (stesso articolo), con max_doc_freq per evitare termini non informativi.


import json
import re
from elasticsearch import Elasticsearch, helpers
from .config import ES_HOST, INDEX_TABLES, INDEX_FIGURES, INDEX_PARAGRAPHS, INTERMEDIATE_DIR

def mlt_context(es: Elasticsearch, paper_doc_id: str, like_text: str, k: int = 8):
    if not like_text or len(like_text) < 20:
        return []
    body = {
        "size": k,
        "_source": ["text"],
        "query": {
            "bool": {
                "filter": [{"term": {"paper_id": paper_doc_id}}],
                "must": [{
                    "more_like_this": {
                        "fields": ["text"],
                        "like": like_text,
                        "min_term_freq": 1,
                        "min_doc_freq": 1,
                        "max_doc_freq": 500000,  # ES accetta int; qui è molto alto, l'analyzer e il filtro paper_id fanno il resto
                        "max_query_terms": 50
                    }
                }]
            }
        }
    }
    res = es.search(index=INDEX_PARAGRAPHS, body=body, request_timeout=60)
    return [h["_source"]["text"] for h in res["hits"]["hits"]]

def main():
    es = Elasticsearch(ES_HOST)

    table_actions = []
    fig_actions = []

    for path in INTERMEDIATE_DIR.glob("*.json"):
        doc = json.loads(path.read_text(encoding="utf-8"))
        pid = doc["paper_id"]
        paper_doc_id = f"{doc['source']}_{pid}"
        paragraphs = doc.get("paragraphs", [])

        # TABLES
        for t in doc.get("tables", []):
            tid = t.get("table_id","")
            caption = t.get("caption","")
            body_text = t.get("body","")

            # mentions dirette: Table 1, Tab. 2, ecc.
            mention_pat = rf"(table|tab\.)\s*{re.escape(tid.replace('T',''))}\b"
            mentions = [p for p in paragraphs if re.search(mention_pat, p, flags=re.IGNORECASE)]
            like = (caption + "\n" + body_text).strip()
            context_paras = mlt_context(es, paper_doc_id, like_text=like, k=8)

            table_actions.append({
                "_index": INDEX_TABLES,
                "_id": f"{paper_doc_id}_{tid}",
                "_source": {
                    "paper_id": paper_doc_id,
                    "table_id": tid,
                    "caption": caption,
                    "body": body_text,
                    "table_html": t.get("table_html",""),
                    "mentions": mentions,
                    "context_paragraphs": context_paras,
                    "url": doc.get("url",""),
                    "source": doc["source"],
                }
            })

        # FIGURES
        for f in doc.get("figures", []):
            fid = f.get("figure_id","")
            caption = f.get("caption","")
            figure_url = f.get("figure_url","")

            mention_pat = rf"(figure|fig\.)\s*{re.escape(fid.replace('F',''))}\b"
            mentions = [p for p in paragraphs if re.search(mention_pat, p, flags=re.IGNORECASE)]
            context_paras = mlt_context(es, paper_doc_id, like_text=caption, k=8)

            fig_actions.append({
                "_index": INDEX_FIGURES,
                "_id": f"{paper_doc_id}_{fid}",
                "_source": {
                    "paper_id": paper_doc_id,
                    "figure_id": fid,
                    "caption": caption,
                    "figure_url": figure_url,
                    "mentions": mentions,
                    "context_paragraphs": context_paras,
                    "url": doc.get("url",""),
                    "source": doc["source"],
                }
            })

    if table_actions:
        helpers.bulk(es, table_actions, request_timeout=120)
    if fig_actions:
        helpers.bulk(es, fig_actions, request_timeout=120)

    es.indices.refresh(index=INDEX_TABLES)
    es.indices.refresh(index=INDEX_FIGURES)
    print(f"[OK] indicizzate tables={len(table_actions)} figures={len(fig_actions)}")

if __name__ == "__main__":
    main()
"""


"""Indicizza tabelle e figure come documenti di prima classe, con context:
- mentions: paragrafi che citano direttamente Table/Figure + id
- context_paragraphs: paragrafi 'simili' a caption/body usando more_like_this su INDEX_PARAGRAPHS,
  filtrati per paper_id (stesso articolo), con max_doc_freq per evitare termini non informativi.
"""


















'''import json
import re
from collections import OrderedDict
from elasticsearch import Elasticsearch, helpers
from .config import (
    ES_HOST,
    INDEX_TABLES,
    INDEX_FIGURES,
    INDEX_PARAGRAPHS,
    INTERMEDIATE_DIR,
    CONTEXT_METHOD,
    OVERLAP_THRESHOLD,
    CONTEXT_TOP_K,
    EMBEDDINGS_ENABLED,
)
from .embeddings import available as embeddings_available, embed
from .utils import tokenize_informative, timed

def mlt_context(es: Elasticsearch, paper_doc_id: str, like_text: str, k: int = 8):
    if not like_text or len(like_text) < 20:
        return []
    body = {
        "size": k,
        "_source": ["text"],
        "query": {
            "bool": {
                "filter": [{"term": {"paper_id": paper_doc_id}}],
                "must": [{
                    "more_like_this": {
                        "fields": ["text"],
                        "like": like_text,
                        "min_term_freq": 1,
                        "min_doc_freq": 1,
                        # Avoid non-informative terms: keep this reasonable
                        "max_doc_freq": 5000,
                        "max_query_terms": 50
                    }
                }]
            }
        }
    }
    res = es.search(index=INDEX_PARAGRAPHS, body=body, request_timeout=60)
    return [h["_source"]["text"] for h in res["hits"]["hits"]]


def overlap_context(paragraphs: list[str], like_text: str, threshold: float, k: int) -> list[str]:
    """Select paragraphs whose token overlap with like_text is above a threshold."""
    terms = set(tokenize_informative(like_text))
    if not terms:
        return []
    scored = []
    for p in paragraphs:
        pt = set(tokenize_informative(p))
        if not pt:
            continue
        score = len(terms & pt) / len(terms)
        if score >= threshold:
            scored.append((score, p))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [p for _, p in scored[:k]]


def dedup_keep_order(items: list[str]) -> list[str]:
    od = OrderedDict()
    for x in items:
        if x and x not in od:
            od[x] = 1
    return list(od.keys())

def main():
    #es = Elasticsearch(ES_HOST)
    es = Elasticsearch(
    ES_HOST,
    request_timeout=120,
    retry_on_timeout=True,
    max_retries=5,
)


    use_vec = EMBEDDINGS_ENABLED and embeddings_available()

    table_actions: list[dict] = []
    fig_actions: list[dict] = []

    with timed("index_tables_figures"):
        for path in INTERMEDIATE_DIR.glob("*.json"):
            doc = json.loads(path.read_text(encoding="utf-8"))
            pid = doc["paper_id"]
            paper_doc_id = f"{doc['source']}_{pid}"
            paragraphs = doc.get("paragraphs", [])

            # TABLES
            for t in doc.get("tables", []):
                tid = t.get("table_id", "")
                caption = t.get("caption", "")
                body_text = t.get("body", "")

                # mentions dirette: Table 1, Tab. 2, ecc.
                mention_pat = rf"(table|tab\.)\s*{re.escape(tid.replace('T',''))}\b"
                mentions = [p for p in paragraphs if re.search(mention_pat, p, flags=re.IGNORECASE)]
                like = (caption + "\n" + body_text).strip()

                ctx_mlt = (
                    mlt_context(es, paper_doc_id, like_text=like, k=CONTEXT_TOP_K)
                    if CONTEXT_METHOD in ("mlt", "hybrid")
                    else []
                )
                ctx_ov = (
                    overlap_context(paragraphs, like, OVERLAP_THRESHOLD, CONTEXT_TOP_K)
                    if CONTEXT_METHOD in ("overlap", "hybrid")
                    else []
                )
                context_paras = dedup_keep_order(ctx_mlt + ctx_ov)

                vec = None
                if use_vec and like:
                    vecs = embed([like])
                    vec = vecs[0] if vecs else None

                src = {
                    "paper_id": paper_doc_id,
                    "table_id": tid,
                    "caption": caption,
                    "body": body_text,
                    "table_html": t.get("table_html", ""),
                    "mentions": mentions,
                    "context_paragraphs": context_paras,
                    "context_meta": {
                        "method": CONTEXT_METHOD,
                        "overlap_threshold": OVERLAP_THRESHOLD,
                        "k": CONTEXT_TOP_K,
                        "mlt_count": len(ctx_mlt),
                        "overlap_count": len(ctx_ov),
                    },
                    "url": doc.get("url", ""),
                    "source": doc["source"],
                }
                if vec is not None:
                    src["caption_body_vec"] = vec

                table_actions.append({
                    "_index": INDEX_TABLES,
                    "_id": f"{paper_doc_id}_{tid}",
                    "_source": src,
                })

            # FIGURES
            for f in doc.get("figures", []):
                fid = f.get("figure_id", "")
                caption = f.get("caption", "")
                figure_url = f.get("figure_url", "")

                mention_pat = rf"(figure|fig\.)\s*{re.escape(fid.replace('F',''))}\b"
                mentions = [p for p in paragraphs if re.search(mention_pat, p, flags=re.IGNORECASE)]
                ctx_mlt = (
                    mlt_context(es, paper_doc_id, like_text=caption, k=CONTEXT_TOP_K)
                    if CONTEXT_METHOD in ("mlt", "hybrid")
                    else []
                )
                ctx_ov = (
                    overlap_context(paragraphs, caption, OVERLAP_THRESHOLD, CONTEXT_TOP_K)
                    if CONTEXT_METHOD in ("overlap", "hybrid")
                    else []
                )
                context_paras = dedup_keep_order(ctx_mlt + ctx_ov)

                vec = None
                if use_vec and caption:
                    vecs = embed([caption])
                    vec = vecs[0] if vecs else None

                src = {
                    "paper_id": paper_doc_id,
                    "figure_id": fid,
                    "caption": caption,
                    "figure_url": figure_url,
                    "mentions": mentions,
                    "context_paragraphs": context_paras,
                    "context_meta": {
                        "method": CONTEXT_METHOD,
                        "overlap_threshold": OVERLAP_THRESHOLD,
                        "k": CONTEXT_TOP_K,
                        "mlt_count": len(ctx_mlt),
                        "overlap_count": len(ctx_ov),
                    },
                    "url": doc.get("url", ""),
                    "source": doc["source"],
                }
                if vec is not None:
                    src["caption_vec"] = vec

                fig_actions.append({
                    "_index": INDEX_FIGURES,
                    "_id": f"{paper_doc_id}_{fid}",
                    "_source": src,
                })

    if table_actions:
        with timed("index_tables:bulk", {"docs": len(table_actions)}):
            helpers.bulk(es, table_actions, request_timeout=120,refresh=False)
    if fig_actions:
        with timed("index_figures:bulk", {"docs": len(fig_actions)}):
            helpers.bulk(es, fig_actions, request_timeout=120,refresh=False)

    #es.indices.refresh(index=INDEX_TABLES)
    #es.indices.refresh(index=INDEX_FIGURES)
    print(f"[OK] indicizzate tables={len(table_actions)} figures={len(fig_actions)}")

if __name__ == "__main__":
    main()
'''


import json
import re
from collections import OrderedDict
from elasticsearch import Elasticsearch, helpers
from .config import (
    ES_HOST,
    INDEX_TABLES,
    INDEX_FIGURES,
    INDEX_PARAGRAPHS,
    INTERMEDIATE_DIR,
    CONTEXT_METHOD,
    OVERLAP_THRESHOLD,
    CONTEXT_TOP_K,
    EMBEDDINGS_ENABLED,
)
from .embeddings import available as embeddings_available, embed
from .utils import tokenize_informative, timed

def mlt_context(es: Elasticsearch, paper_doc_id: str, like_text: str, k: int = 5):
    if not like_text or len(like_text) < 20:
        return []
    
    # Escape caratteri speciali per query string o usa simple_query_string se preferisci
    # Qui usiamo more_like_this che gestisce il testo raw
    body = {
        "size": k,
        "_source": ["text"],
        "query": {
            "bool": {
                "filter": [{"term": {"paper_id": paper_doc_id}}],
                "must": [{
                    "more_like_this": {
                        "fields": ["text"],
                        "like": like_text,
                        "min_term_freq": 1,
                        "min_doc_freq": 1,
                        "max_doc_freq": 10000,
                        "max_query_terms": 50
                    }
                }]
            }
        }
    }
    try:
        res = es.search(index=INDEX_PARAGRAPHS, body=body, request_timeout=30)
        return [h["_source"]["text"] for h in res["hits"]["hits"]]
    except Exception as e:
        print(f"Errore MLT per {paper_doc_id}: {e}")
        return []

def overlap_context(paragraphs: list[str], like_text: str, threshold: float, k: int) -> list[str]:
    terms = set(tokenize_informative(like_text))
    if not terms:
        return []
    scored = []
    for p in paragraphs:
        pt = set(tokenize_informative(p))
        if not pt: continue
        score = len(terms & pt) / len(terms)
        if score >= threshold:
            scored.append((score, p))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [p for _, p in scored[:k]]

def dedup_keep_order(items: list[str]) -> list[str]:
    od = OrderedDict()
    for x in items:
        if x and x not in od:
            od[x] = 1
    return list(od.keys())

def main():
    es = Elasticsearch(ES_HOST, request_timeout=120, max_retries=3, retry_on_timeout=True)
    use_vec = EMBEDDINGS_ENABLED and embeddings_available()

    table_actions = []
    fig_actions = []

    files = list(INTERMEDIATE_DIR.glob("*.json"))
    print(f"Indicizzazione di {len(files)} documenti...")

    with timed("index_tables_figures"):
        for path in files:
            try:
                doc = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
                
            pid = doc.get("paper_id")
            source = doc.get("source", "unk")
            # ID univoco del paper in ES
            paper_doc_id = f"{source}_{pid}"
            paragraphs = doc.get("paragraphs", [])

            # --- TABLES ---
            for t in doc.get("tables", []):
                tid = t.get("table_id", "T0")
                caption = t.get("caption", "")
                body_text = t.get("body", "")
                
                # Cerca mention tipo "Table 1" o "Tab. 1"
                # Rimuoviamo 'T' dall'ID per cercare il numero (es. T1 -> 1)
                num_id = re.escape(tid.replace("T", ""))
                mention_pat = rf"\b(table|tab\.?)\s*{num_id}\b"
                
                mentions = [p for p in paragraphs if re.search(mention_pat, p, flags=re.IGNORECASE)]
                
                # Context Retrieval
                like_txt = (caption + " " + body_text).strip()
                ctx_paras = []
                
                if like_txt:
                    ctx_mlt = mlt_context(es, paper_doc_id, like_txt, k=CONTEXT_TOP_K) if "mlt" in CONTEXT_METHOD else []
                    ctx_ov = overlap_context(paragraphs, like_txt, OVERLAP_THRESHOLD, CONTEXT_TOP_K) if "overlap" in CONTEXT_METHOD else []
                    ctx_paras = dedup_keep_order(ctx_mlt + ctx_ov)

                # Embedding
                vec = None
                if use_vec and caption:
                    vec = embed([caption])[0]

                src = {
                    "paper_id": paper_doc_id,
                    "table_id": tid,
                    "caption": caption,
                    "body": body_text,
                    "table_html": t.get("table_html", ""),
                    "mentions": mentions,
                    "context_paragraphs": ctx_paras,
                    "url": doc.get("url", ""),
                    "source": source,
                    "date": doc.get("date") # Utile per filtri
                }
                if vec: src["caption_vec"] = vec # O caption_body_vec

                table_actions.append({
                    "_index": INDEX_TABLES,
                    "_id": f"{paper_doc_id}_{tid}",
                    "_source": src
                })

            # --- FIGURES ---
            for f in doc.get("figures", []):
                fid = f.get("figure_id", "F0")
                caption = f.get("caption", "")
                
                num_id = re.escape(fid.replace("F", ""))
                mention_pat = rf"\b(figure|fig\.?)\s*{num_id}\b"
                
                mentions = [p for p in paragraphs if re.search(mention_pat, p, flags=re.IGNORECASE)]
                
                ctx_paras = []
                if caption:
                    ctx_mlt = mlt_context(es, paper_doc_id, caption, k=CONTEXT_TOP_K) if "mlt" in CONTEXT_METHOD else []
                    ctx_ov = overlap_context(paragraphs, caption, OVERLAP_THRESHOLD, CONTEXT_TOP_K) if "overlap" in CONTEXT_METHOD else []
                    ctx_paras = dedup_keep_order(ctx_mlt + ctx_ov)

                vec = None
                if use_vec and caption:
                    vec = embed([caption])[0]

                src = {
                    "paper_id": paper_doc_id,
                    "figure_id": fid,
                    "caption": caption,
                    "figure_url": f.get("figure_url", ""),
                    "mentions": mentions,
                    "context_paragraphs": ctx_paras,
                    "url": doc.get("url", ""),
                    "source": source,
                    "date": doc.get("date")
                }
                if vec: src["caption_vec"] = vec

                fig_actions.append({
                    "_index": INDEX_FIGURES,
                    "_id": f"{paper_doc_id}_{fid}",
                    "_source": src
                })

    # Bulk Indexing
    if table_actions:
        print(f"Caricamento {len(table_actions)} tabelle...")
        helpers.bulk(es, table_actions, request_timeout=120, refresh=False)
    
    if fig_actions:
        print(f"Caricamento {len(fig_actions)} figure...")
        helpers.bulk(es, fig_actions, request_timeout=120, refresh=False)

    print("[DONE] Indicizzazione completata.")

if __name__ == "__main__":
    main()