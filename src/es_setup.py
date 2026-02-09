"""Crea (o ricrea) gli indici Elasticsearch richiesti dal progetto."""

from elasticsearch import Elasticsearch
from .config import ES_HOST, INDEX_PAPERS, INDEX_PARAGRAPHS, INDEX_TABLES, INDEX_FIGURES

def ensure_index(es: Elasticsearch, name: str, mapping: dict):
    if es.indices.exists(index=name):
        return
    es.indices.create(index=name, mappings=mapping)

def main():
    es = Elasticsearch(ES_HOST)

    papers_mapping = {
        "properties": {
            "paper_id": {"type": "keyword"},
            "source": {"type": "keyword"},  # arxiv|pmc
            "url": {"type": "keyword", "index": False},
            "title": {"type": "text"},
            "authors": {"type": "keyword"},
            "date": {"type": "keyword"},
            "abstract": {"type": "text"},
            "full_text": {"type": "text"},
        }
    }
    paragraphs_mapping = {
        "properties": {
            "paper_id": {"type": "keyword"},
            "para_id": {"type": "integer"},
            "text": {"type": "text"},
        }
    }
    tables_mapping = {
        "properties": {
            "paper_id": {"type": "keyword"},
            "table_id": {"type": "keyword"},
            "caption": {"type": "text"},
            "body": {"type": "text"},
            "table_html": {"type": "keyword", "index": False, "doc_values": False},
            "mentions": {"type": "text"},
            "context_paragraphs": {"type": "text"},
            "url": {"type": "keyword", "index": False},
            "source": {"type": "keyword"},
        }
    }
    figures_mapping = {
        "properties": {
            "paper_id": {"type": "keyword"},
            "figure_id": {"type": "keyword"},
            "caption": {"type": "text"},
            "figure_url": {"type": "keyword", "index": False},
            "mentions": {"type": "text"},
            "context_paragraphs": {"type": "text"},
            "url": {"type": "keyword", "index": False},
            "source": {"type": "keyword"},
        }
    }

    ensure_index(es, INDEX_PAPERS, papers_mapping)
    ensure_index(es, INDEX_PARAGRAPHS, paragraphs_mapping)
    ensure_index(es, INDEX_TABLES, tables_mapping)
    ensure_index(es, INDEX_FIGURES, figures_mapping)

    print("[OK] Indici pronti:", INDEX_PAPERS, INDEX_PARAGRAPHS, INDEX_TABLES, INDEX_FIGURES)

if __name__ == "__main__":
    main()
