"""
import json
import math
from collections import defaultdict
from elasticsearch import Elasticsearch

from config import (
    ES_HOST,
    INDEX_PAPERS,
    INDEX_TABLES,
    INDEX_FIGURES,
)

TOP_K = 10


def precision_at_k(ranked, relevant, k):
    return sum(1 for d in ranked[:k] if d in relevant) / k


def recall_at_k(ranked, relevant, k):
    if not relevant:
        return 0.0
    return sum(1 for d in ranked[:k] if d in relevant) / len(relevant)


def average_precision(ranked, relevant):
    if not relevant:
        return 0.0
    score = 0.0
    hits = 0
    for i, d in enumerate(ranked, start=1):
        if d in relevant:
            hits += 1
            score += hits / i
    return score / len(relevant)


def ndcg_at_k(ranked, rel_scores, k):
    def dcg(scores):
        return sum(s / math.log2(i + 2) for i, s in enumerate(scores))

    ideal = sorted(rel_scores.values(), reverse=True)[:k]
    actual = [rel_scores.get(d, 0) for d in ranked[:k]]

    return dcg(actual) / dcg(ideal) if dcg(ideal) > 0 else 0.0


def search(es, index, fields, query, k):
    body = {
        "size": k,
        "query": {
            "multi_match": {
                "query": query,
                "fields": fields
            }
        }
    }
    hits = es.search(index=index, body=body)["hits"]["hits"]
    return [h["_id"] for h in hits]


def main():
    es = Elasticsearch(ES_HOST)

    queries = []
    with open("data/eval/queries.jsonl", encoding="utf-8") as f:
        for line in f:
            queries.append(json.loads(line))

    qrels = defaultdict(dict)
    with open("data/eval/qrels.tsv", encoding="utf-8") as f:
        next(f)
        for line in f:
            qid, _, doc_id, rel = line.strip().split("\t")
            qrels[qid][doc_id] = int(rel)

    metrics = defaultdict(list)

    for q in queries:
        qid = q["qid"]
        text = q["text"]
        target = q["target"]

        if target == "papers":
            ranked = search(
                es,
                INDEX_PAPERS,
                ["title^2", "abstract", "full_text"],
                text,
                TOP_K
            )
        elif target == "tables":
            ranked = search(
                es,
                INDEX_TABLES,
                ["caption^2", "body", "mentions", "context_paragraphs"],
                text,
                TOP_K
            )
        elif target == "figures":
            ranked = search(
                es,
                INDEX_FIGURES,
                ["caption^2", "mentions", "context_paragraphs"],
                text,
                TOP_K
            )
        else:
            continue

        relevant = {d for d, r in qrels[qid].items() if r > 0}

        metrics["P@10"].append(precision_at_k(ranked, relevant, 10))
        metrics["R@10"].append(recall_at_k(ranked, relevant, 10))
        metrics["MAP"].append(average_precision(ranked, relevant))
        metrics["nDCG@10"].append(ndcg_at_k(ranked, qrels[qid], 10))

    print("\n=== RISULTATI VALUTAZIONE ===")
    for m, vals in metrics.items():
        print(f"{m}: {sum(vals)/len(vals):.3f}")


if __name__ == "__main__":
    main()
"""

import json
import math
from collections import defaultdict
from elasticsearch import Elasticsearch

from src.config import (
    ES_HOST,
    INDEX_PAPERS,
    INDEX_TABLES,
    INDEX_FIGURES,
)

TOP_K = 10


def precision_at_k(ranked, relevant, k):
    return sum(1 for d in ranked[:k] if d in relevant) / k


def recall_at_k(ranked, relevant, k):
    if not relevant:
        return 0.0
    return sum(1 for d in ranked[:k] if d in relevant) / len(relevant)


def average_precision(ranked, relevant):
    if not relevant:
        return 0.0
    score = 0.0
    hits = 0
    for i, d in enumerate(ranked, start=1):
        if d in relevant:
            hits += 1
            score += hits / i
    return score / len(relevant)


def ndcg_at_k(ranked, rel_scores, k):
    def dcg(scores):
        return sum(s / math.log2(i + 2) for i, s in enumerate(scores))

    ideal = sorted(rel_scores.values(), reverse=True)[:k]
    actual = [rel_scores.get(d, 0) for d in ranked[:k]]

    return dcg(actual) / dcg(ideal) if dcg(ideal) > 0 else 0.0


def search(es, index, fields, query, k):
    body = {
        "size": k,
        "query": {
            "multi_match": {
                "query": query,
                "fields": fields
            }
        }
    }
    hits = es.search(index=index, body=body)["hits"]["hits"]
    return [h["_id"] for h in hits]


def main():
    es = Elasticsearch(ES_HOST)

    queries = []
    with open("data/eval/queries_auto.jsonl", encoding="utf-8") as f:
        for line in f:
            queries.append(json.loads(line))

    qrels = defaultdict(dict)
    with open("data/eval/qrels_noLLM.tsv", encoding="utf-8") as f:
        next(f)
        for line in f:
            qid, _, doc_id, rel = line.strip().split("\t")
            qrels[qid][doc_id] = int(rel)

    metrics = defaultdict(list)

    for q in queries:
        qid = q["qid"]
        text = q["text"]
        target = q["target"]

        if target == "papers":
            ranked = search(
                es,
                INDEX_PAPERS,
                ["title^2", "abstract", "full_text"],
                text,
                TOP_K
            )
        elif target == "tables":
            ranked = search(
                es,
                INDEX_TABLES,
                ["caption^2", "body", "mentions", "context_paragraphs"],
                text,
                TOP_K
            )
        elif target == "figures":
            ranked = search(
                es,
                INDEX_FIGURES,
                ["caption^2", "mentions", "context_paragraphs"],
                text,
                TOP_K
            )
        else:
            continue

        relevant = {d for d, r in qrels[qid].items() if r > 0}

        metrics["P@10"].append(precision_at_k(ranked, relevant, 10))
        metrics["R@10"].append(recall_at_k(ranked, relevant, 10))
        metrics["MAP"].append(average_precision(ranked, relevant))
        metrics["nDCG@10"].append(ndcg_at_k(ranked, qrels[qid], 10))

    print("\n=== RISULTATI VALUTAZIONE ===")
    for m, vals in metrics.items():
        print(f"{m}: {sum(vals)/len(vals):.3f}")


if __name__ == "__main__":
    main()
