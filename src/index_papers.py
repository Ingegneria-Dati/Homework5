"""Indicizza papers e paragrafi su Elasticsearch."""

import json
from elasticsearch import Elasticsearch, helpers
from .config import ES_HOST, INDEX_PAPERS, INDEX_PARAGRAPHS, INTERMEDIATE_DIR

def main():
    es = Elasticsearch(ES_HOST)

    paper_actions = []
    para_actions = []
    for path in INTERMEDIATE_DIR.glob("*.json"):
        doc = json.loads(path.read_text(encoding="utf-8"))
        pid = doc["paper_id"]

        paper_actions.append({
            "_index": INDEX_PAPERS,
            "_id": f"{doc['source']}_{pid}",
            "_source": {
                "paper_id": pid,
                "source": doc["source"],
                "url": doc.get("url",""),
                "title": doc.get("title",""),
                "authors": doc.get("authors",[]),
                "date": doc.get("date",""),
                "abstract": doc.get("abstract",""),
                "full_text": doc.get("full_text",""),
            }
        })

        for i, ptxt in enumerate(doc.get("paragraphs", [])):
            para_actions.append({
                "_index": INDEX_PARAGRAPHS,
                "_id": f"{doc['source']}_{pid}_{i}",
                "_source": {"paper_id": f"{doc['source']}_{pid}", "para_id": i, "text": ptxt}
            })

    if paper_actions:
        helpers.bulk(es, paper_actions, request_timeout=120)
    if para_actions:
        helpers.bulk(es, para_actions, request_timeout=120)

    es.indices.refresh(index=INDEX_PAPERS)
    es.indices.refresh(index=INDEX_PARAGRAPHS)
    print(f"[OK] indicizzati papers={len(paper_actions)} paragraphs={len(para_actions)}")

if __name__ == "__main__":
    main()
