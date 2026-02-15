
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from elasticsearch import Elasticsearch

from .config import (
    ES_HOST,
    INDEX_PAPERS,
    INDEX_TABLES,
    INDEX_FIGURES,
    RRF_K,  # Aggiungi in config.py: RRF_K = 60
    USE_QUERY_STRING_BY_DEFAULT, # Aggiungi in config.py: USE_QUERY_STRING_BY_DEFAULT = True
)

@dataclass
class SearchFilters:
    source: Optional[str] = None  # "arxiv" | "pmc"
    date_from: Optional[str] = None  # ISO date or year
    date_to: Optional[str] = None

def _base_bool_filter(filters: Optional[SearchFilters]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not filters:
        return out
    
    # Filtro Fonte
    if filters.source:
        out.append({"term": {"source": filters.source}})
    
    # Filtro Data
    if filters.date_from or filters.date_to:
        rng: Dict[str, Any] = {}
        if filters.date_from:
            rng["gte"] = filters.date_from
        if filters.date_to:
            rng["lte"] = filters.date_to
        # Nota: il campo data nell'indice deve chiamarsi "date"
        out.append({"range": {"date": rng}})
    return out

def build_query(
    query: str,
    fields: List[str],
    *,
    use_query_string: Optional[bool] = None,
    filters: Optional[SearchFilters] = None,
) -> Dict[str, Any]:
    """Build an ES query handling both simple match and complex query_string."""
    if use_query_string is None:
        use_query_string = USE_QUERY_STRING_BY_DEFAULT

    q: Dict[str, Any]
    if use_query_string:
        q = {
            "query_string": {
                "query": query,
                "fields": fields,
                "default_operator": "AND",
            }
        }
    else:
        q = {
            "multi_match": {
                "query": query,
                "fields": fields,
                "type": "best_fields",
                "operator": "AND",
            }
        }

    f = _base_bool_filter(filters)
    if not f:
        return {"query": q}
    
    return {"query": {"bool": {"must": [q], "filter": f}}}

def search_index(
    es: Elasticsearch,
    index: str,
    query: str,
    fields: List[str],
    size: int = 20,
    *,
    use_query_string: Optional[bool] = None,
    filters: Optional[SearchFilters] = None,
) -> Dict[str, Any]:
    body = build_query(query, fields, use_query_string=use_query_string, filters=filters)
    body["size"] = size
    # Aggiungi highlight per vedere dove ha trovato le parole
    body["highlight"] = {
        "fields": { f.split("^")[0]: {} for f in fields },
        "pre_tags": ["<em>"], "post_tags": ["</em>"]
    }
    return es.search(index=index, body=body)

def rrf_fuse(
    ranked_lists: List[Tuple[str, List[Dict[str, Any]]]],
    *,
    k: int = RRF_K,
) -> List[Tuple[str, float, Dict[str, Any]]]:
    """Reciprocal Rank Fusion algorithm."""
    scores: Dict[Tuple[str, str], float] = {}
    hits_map: Dict[Tuple[str, str], Dict[str, Any]] = {}

    for kind, hits in ranked_lists:
        for rank, h in enumerate(hits, start=1):
            doc_id = h.get("_id") or ""
            if not doc_id: continue
            
            key = (kind, doc_id)
            # RRF formula: sum(1 / (k + rank))
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank)
            hits_map[key] = h

    # Ordina per score decrescente
    merged = [(kind, sc, hits_map[(kind, docid)]) for (kind, docid), sc in scores.items()]
    merged.sort(key=lambda x: x[1], reverse=True)
    return merged

def cross_search(
    es: Elasticsearch,
    query: str,
    *,
    size_each: int = 10,
    size_total: Optional[int] = None,
    use_query_string: Optional[bool] = None,
    filters: Optional[SearchFilters] = None,
) -> List[Tuple[str, float, Dict[str, Any]]]:
    """Search papers, tables, figures indices and fuse results."""
    
    # 1. Cerca Papers
    res_p = search_index(
        es, INDEX_PAPERS, query,
        ["title^3", "abstract^2", "full_text"],
        size_each, use_query_string=use_query_string, filters=filters
    )

    # 2. Prepara filtri per oggetti (Table/Fig)
    # Se filtriamo per source nei paper, vale anche per le figure
    f_objs = SearchFilters(source=filters.source) if (filters and filters.source) else None
    
    # 3. Cerca Tabelle
    res_t = search_index(
        es, INDEX_TABLES, query,
        ["caption^3", "body^2", "mentions", "context_paragraphs"],
        size_each, use_query_string=use_query_string, filters=f_objs
    )

    # 4. Cerca Figure
    res_f = search_index(
        es, INDEX_FIGURES, query,
        ["caption^3", "mentions", "context_paragraphs"],
        size_each, use_query_string=use_query_string, filters=f_objs
    )

    # 5. RRF Fusion
    merged = rrf_fuse([
        ("paper", res_p.get("hits", {}).get("hits", [])),
        ("table", res_t.get("hits", {}).get("hits", [])),
        ("figure", res_f.get("hits", {}).get("hits", [])),
    ])

    if size_total is not None:
        return merged[:size_total]
    return merged

def es_client() -> Elasticsearch:
    return Elasticsearch(ES_HOST, request_timeout=30)