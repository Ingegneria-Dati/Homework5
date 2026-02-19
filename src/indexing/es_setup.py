
import argparse
from elasticsearch import Elasticsearch

from ..config import (
    ES_HOST,
    INDEX_PAPERS,
    INDEX_PARAGRAPHS,
    INDEX_TABLES,
    INDEX_FIGURES,
    TEXT_ANALYZER,
    EMBEDDINGS_ENABLED,
    EMBEDDING_DIMS,
)


def create_or_replace_index(es: Elasticsearch, name: str, body: dict, recreate: bool = False):
    if recreate and es.indices.exists(index=name):
        es.indices.delete(index=name)
    if es.indices.exists(index=name):
        return
    es.indices.create(index=name, body=body)


def common_settings() -> dict:
    return {
        "analysis": {
            "filter": {
                "english_stop": {
                    "type": "stop",
                    "stopwords": "_english_"
                },
                "english_stemmer": {
                    "type": "stemmer",
                    "language": "english"
                },
                "hw5_shingle": {
                    "type": "shingle",
                    "min_shingle_size": 2,
                    "max_shingle_size": 3,
                    "output_unigrams": True
                },
            },
            "analyzer": {
                TEXT_ANALYZER: {
                    "type": "custom",
                    "tokenizer": "standard",
                    "filter": [
                        "lowercase",
                        "asciifolding",
                        "english_stop",
                        "english_stemmer",
                        "hw5_shingle"
                    ],
                }
            },
        }
    }



def field_text() -> dict:
    return {"type": "text", "analyzer": TEXT_ANALYZER}


def field_text_with_keyword() -> dict:
    return {
        "type": "text",
        "analyzer": TEXT_ANALYZER,
        "fields": {"keyword": {"type": "keyword", "ignore_above": 256}},
    }


def maybe_vector() -> dict:
    if not EMBEDDINGS_ENABLED:
        return {}
    # ES supports dense_vector. kNN syntax depends on ES version; we keep mapping portable.
    return {"type": "dense_vector", "dims": EMBEDDING_DIMS, "index": False}


def main(argv: list[str] | None = None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--recreate", action="store_true", help="Drop and recreate indices")
    args = ap.parse_args(argv)

    es = Elasticsearch(ES_HOST)

    settings = common_settings()

    papers_body = {
        "settings": settings,
        "mappings": {
            "properties": {
                "paper_id": {"type": "keyword"},
                "source": {"type": "keyword"},
                "url": {"type": "keyword", "index": False},
                "title": field_text_with_keyword(),
                "authors": {
                    "type": "text",
                    "analyzer": TEXT_ANALYZER,
                    "fields": {"keyword": {"type": "keyword", "ignore_above": 256}},
                },
                "date": {"type": "date", "format": "strict_date_optional_time||yyyy-MM-dd||yyyy"},
                "abstract": field_text(),
                "full_text": field_text(),
                # Optional: semantic search vectors (use with hybrid retrieval)
                #"title_abstract_vec": maybe_vector(),
            }
        },
    }

    paragraphs_body = {
        "settings": settings,
        "mappings": {
            "properties": {
                "paper_id": {"type": "keyword"},
                "para_id": {"type": "integer"},
                "text": field_text(),
            }
        },
    }

    tables_body = {
        "settings": settings,
        "mappings": {
            "properties": {
                "paper_id": {"type": "keyword"},
                "table_id": {"type": "keyword"},
                "caption": field_text_with_keyword(),
                "body": field_text(),
                "table_html": {"type": "keyword", "index": False, "doc_values": False},
                "mentions": field_text(),
                "context_paragraphs": field_text(),
                "context_meta": {"type": "object", "enabled": True},
                "url": {"type": "keyword", "index": False},
                "source": {"type": "keyword"},
                #"caption_body_vec": maybe_vector(),
            }
        },
    }

    figures_body = {
        "settings": settings,
        "mappings": {
            "properties": {
                "paper_id": {"type": "keyword"},
                "figure_id": {"type": "keyword"},
                "caption": field_text_with_keyword(),
                "figure_url": {"type": "keyword", "index": False},
                "mentions": field_text(),
                "context_paragraphs": field_text(),
                "context_meta": {"type": "object", "enabled": True},
                "url": {"type": "keyword", "index": False},
                "source": {"type": "keyword"},
                #"caption_vec": maybe_vector(),
            }
        },
    }

    create_or_replace_index(es, INDEX_PAPERS, papers_body, recreate=args.recreate)
    create_or_replace_index(es, INDEX_PARAGRAPHS, paragraphs_body, recreate=args.recreate)
    create_or_replace_index(es, INDEX_TABLES, tables_body, recreate=args.recreate)
    create_or_replace_index(es, INDEX_FIGURES, figures_body, recreate=args.recreate)

    print("[OK] Indici pronti:", INDEX_PAPERS, INDEX_PARAGRAPHS, INDEX_TABLES, INDEX_FIGURES)


if __name__ == "__main__":
    main()
