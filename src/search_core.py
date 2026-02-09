from elasticsearch import Elasticsearch
from .config import ES_HOST, INDEX_PAPERS, INDEX_TABLES, INDEX_FIGURES

def build_query(query: str, fields: list[str]):
    # query_string supporta boolean, virgolette, AND/OR/NOT
    return {
        "query": {
            "query_string": {
                "query": query,
                "fields": fields,
                "default_operator": "AND"
            }
        }
    }

def search_index(es: Elasticsearch, index: str, query: str, fields: list[str], size: int = 20):
    body = build_query(query, fields)
    body["size"] = size
    return es.search(index=index, body=body)

def cross_search(es: Elasticsearch, query: str, size_each: int = 10):
    # Esegue 3 ricerche e normalizza score per indice (semplice)
    res_p = search_index(es, INDEX_PAPERS, query, ["title^2","abstract","full_text"], size_each)
    res_t = search_index(es, INDEX_TABLES, query, ["caption^2","body","mentions","context_paragraphs"], size_each)
    res_f = search_index(es, INDEX_FIGURES, query, ["caption^2","mentions","context_paragraphs"], size_each)

    def norm(hits):
        if not hits: return []
        mx = max(h["_score"] for h in hits) or 1.0
        for h in hits:
            h["_norm"] = h["_score"]/mx
        return hits

    hp = norm(res_p["hits"]["hits"])
    ht = norm(res_t["hits"]["hits"])
    hf = norm(res_f["hits"]["hits"])

    merged = []
    for h in hp:
        merged.append(("paper", h["_norm"], h))
    for h in ht:
        merged.append(("table", h["_norm"], h))
    for h in hf:
        merged.append(("figure", h["_norm"], h))

    merged.sort(key=lambda x: x[1], reverse=True)
    return merged
