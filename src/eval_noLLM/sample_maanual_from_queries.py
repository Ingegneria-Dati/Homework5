import random
import json
import csv
from pathlib import Path
from elasticsearch import Elasticsearch

ES_HOST = "http://localhost:9200"

INDEX_PAPERS = "hw5_papers"
INDEX_TABLES = "hw5_tables"
INDEX_FIGURES = "hw5_figures"

QUERIES_PATH = Path("data/eval/queries_llm.jsonl")
OUT_PATH = Path("data/eval/manual_eval_from_queries.csv")

TOP_K = 5
MAX_QUERIES = 10

def search(es, index, query, fields):
    body = {
        "size": TOP_K,
        "query": {
            "multi_match": {
                "query": query,
                "fields": fields
            }
        }
    }
    return es.search(index=index, body=body)["hits"]["hits"]

def main():
    es = Elasticsearch(ES_HOST)
    random.seed(42)

    queries = []
    with QUERIES_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            queries.append(json.loads(line))

    queries = random.sample(queries, min(MAX_QUERIES, len(queries)))

    rows = []

    for q in queries:
        qid = q["qid"]
        qtext = q["text"]
        target = q["target"]

        if target in ("papers", "cross"):
            hits = search(es, INDEX_PAPERS, qtext, ["title^2","abstract"])
            for h in hits:
                rows.append([
                    qid, qtext, "paper",
                    h["_source"]["paper_id"],
                    h["_source"].get("title","")[:200],
                    "",
                    ""
                ])

        if target in ("tables", "cross"):
            hits = search(es, INDEX_TABLES, qtext, ["caption^2","body"])
            for h in hits:
                src = h["_source"]
                rows.append([
                    qid, qtext, "table",
                    f"{src['paper_id']}::{src['table_id']}",
                    src.get("caption","")[:200],
                    "",
                    ""
                ])

        if target in ("figures", "cross"):
            hits = search(es, INDEX_FIGURES, qtext, ["caption^2"])
            for h in hits:
                src = h["_source"]
                rows.append([
                    qid, qtext, "figure",
                    f"{src['paper_id']}::{src['figure_id']}",
                    src.get("caption","")[:200],
                    "",
                    ""
                ])

    with OUT_PATH.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["qid","query","type","doc_id","short_content","relevance(0/1/2)","notes"])
        w.writerows(rows)

    print(f"[OK] Creato: {OUT_PATH}")

if __name__ == "__main__":
    main()
