"""Indicizza tabelle e figure come documenti di prima classe, con context:
- mentions: paragrafi che citano direttamente Table/Figure + id
- context_paragraphs: paragrafi 'simili' a caption/body usando more_like_this su INDEX_PARAGRAPHS,
  filtrati per paper_id (stesso articolo), con max_doc_freq per evitare termini non informativi.
"""

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
