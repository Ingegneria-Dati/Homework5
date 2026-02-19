

# src/search_core.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, List, Dict, Any, Tuple
from elasticsearch import Elasticsearch

from src.config import ES_HOST


@dataclass
class SearchFilters:
    source: Optional[str] = None        # "arxiv" | "pmc" | None
    date_from: Optional[str] = None     # "YYYY-MM-DD" or "YYYY"
    date_to: Optional[str] = None       # "YYYY-MM-DD" or "YYYY"


def _build_filters(filters: Optional[SearchFilters]) -> List[Dict[str, Any]]:
    flt: List[Dict[str, Any]] = []
    if not filters:
        return flt

    if filters.source:
        flt.append({"term": {"source": filters.source}})

    # date range (se il mapping di date è "date")
    if filters.date_from or filters.date_to:
        rng: Dict[str, Any] = {}
        if filters.date_from:
            rng["gte"] = filters.date_from
        if filters.date_to:
            rng["lte"] = filters.date_to
        flt.append({"range": {"date": rng}})

    return flt


def search_index(
    es: Elasticsearch,
    index: str,
    query: str,
    fields: List[str],
    topk: int = 20,
    filters: Optional[SearchFilters] = None,
) -> Dict[str, Any]:
    """
    Ricerca SOLO con Elasticsearch multi_match (niente query_string/Lucene).
    fields può includere boost con ^ (es: "title^3").
    """
    query = (query or "").strip()
    if not query:
        return {"hits": {"hits": []}}

    body = {
        "size": topk,
        "query": {
            "bool": {
                "must": [
                    {
                        "multi_match": {
                            "query": query,
                            "fields": fields,
                            "type": "best_fields",
                            "operator": "and",
                            "fuzziness": "AUTO",  # aiuta typo leggeri
                        }
                    }
                ],
                "filter": _build_filters(filters),
            }
        },
    }

    return es.search(index=index, body=body, request_timeout=30)


def cross_search(
    es: Elasticsearch,
    query: str,
    index_papers: str,
    index_tables: str,
    index_figures: str,
    size_each: int = 20,
    size_total: int = 20,
    filters: Optional[SearchFilters] = None,
    mode="auto"
) -> List[Tuple[str, float, Dict[str, Any]]]:
    """
    Cross-search semplice:
    - esegue 3 ricerche separate (papers/tables/figures)
    - fonde i risultati ordinando per score normalizzato (semplice, non RRF puro)
    Ritorna lista di (kind, score, hit)
    """
    q = (query or "").strip()
    if not q:
        return []

    papers = search_index(
        es, index_papers, q,
        fields=["title^3", "abstract^2", "full_text"],
        topk=size_each,
        filters=filters,
    ).get("hits", {}).get("hits", [])

    tables = search_index(
        es, index_tables, q,
        fields=["caption^3", "body^2", "mentions", "context_paragraphs"],
        topk=size_each,
        filters=filters,
    ).get("hits", {}).get("hits", [])

    figures = search_index(
        es, index_figures, q,
        fields=["caption^3", "mentions", "context_paragraphs"],
        topk=size_each,
        filters=filters,
    ).get("hits", {}).get("hits", [])

    # normalizza score per ciascuna lista (evita che un indice domini)
    def norm(hits):
        if not hits:
            return []
        mx = max((h.get("_score") or 0.0) for h in hits) or 1.0
        out = []
        for h in hits:
            out.append((h, float(h.get("_score") or 0.0) / mx))
        return out

    merged: List[Tuple[str, float, Dict[str, Any]]] = []

    for h, s in norm(papers):
        merged.append(("paper", s, h))
    for h, s in norm(tables):
        merged.append(("table", s, h))
    for h, s in norm(figures):
        merged.append(("figure", s, h))

    merged.sort(key=lambda x: x[1], reverse=True)
    return merged[:size_total]

def term_query(term: str, fields: list[str]) -> dict:
    t = (term or "").strip()

    is_phrase = t.startswith('"') and t.endswith('"') and len(t) >= 2
    if is_phrase:
        phrase = t[1:-1].strip()
        if not phrase:
            return {"match_all": {}}
        return {
            "multi_match": {
                "query": phrase,
                "fields": fields,
                "type": "phrase",
                "slop": 0,
            }
        }

    return {
        "multi_match": {
            "query": t,
            "fields": fields,
            "type": "best_fields",
            "operator": "and",
        }
    }

def es_client() -> Elasticsearch:
    return Elasticsearch(ES_HOST, request_timeout=60)
