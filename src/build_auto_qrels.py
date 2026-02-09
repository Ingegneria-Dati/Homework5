import json
from pathlib import Path
from elasticsearch import Elasticsearch

from src.config import ES_HOST, INDEX_PAPERS, INDEX_TABLES, INDEX_FIGURES

OUT = Path("data/eval/qrels.tsv")
OUT.parent.mkdir(parents=True, exist_ok=True)


def contains_any(text, terms):
    t = (text or "").lower()
    return any(term in t for term in terms)


def main():
    es = Elasticsearch(ES_HOST)

    queries = []
    with open("data/eval/queries.jsonl", encoding="utf-8") as f:
        for l in f:
            queries.append(json.loads(l))

    rows = [["qid", "doc_type", "doc_id", "relevance"]]

    for q in queries:
        qid = q["qid"]
        terms = q["text"].lower().split()

        # PAPERS
        hits = es.search(
            index=INDEX_PAPERS,
            body={"size": 50, "query": {"match_all": {}}}
        )["hits"]["hits"]

        for h in hits:
            s = h["_source"]
            if contains_any(s.get("title"), terms) or contains_any(s.get("abstract"), terms):
                rows.append([qid, "paper", s["paper_id"], 1])

        # TABLES
        hits = es.search(
            index=INDEX_TABLES,
            body={"size": 50, "query": {"match_all": {}}}
        )["hits"]["hits"]

        for h in hits:
            s = h["_source"]
            if contains_any(s.get("caption"), terms) or contains_any(s.get("body"), terms):
                did = f"{s['paper_id']}::{s['table_id']}"
                rows.append([qid, "table", did, 1])

        # FIGURES
        hits = es.search(
            index=INDEX_FIGURES,
            body={"size": 50, "query": {"match_all": {}}}
        )["hits"]["hits"]

        for h in hits:
            s = h["_source"]
            if contains_any(s.get("caption"), terms) or contains_any(" ".join(s.get("context_paragraphs", [])), terms):
                did = f"{s['paper_id']}::{s['figure_id']}"
                rows.append([qid, "figure", did, 1])

    with open(OUT, "w", encoding="utf-8") as f:
        for r in rows:
            f.write("\t".join(map(str, r)) + "\n")

    print(f"[DONE] qrels automatici scritti in {OUT}")


if __name__ == "__main__":
    main()
