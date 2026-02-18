

import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

from elasticsearch import Elasticsearch

from src.config import ES_HOST, INDEX_PAPERS, INDEX_TABLES, INDEX_FIGURES

QUERIES_PATH = Path("data/eval_noLLM/queries_noLLM.jsonl")
QRELS_PATH = Path("data/eval_noLLM/qrels_noLLM.tsv")

TOP_K = 10


def precision_at_k(ranked: List[str], relevant: set, k: int) -> float:
    if k == 0:
        return 0.0
    return sum(1 for d in ranked[:k] if d in relevant) / k


def recall_at_k(ranked: List[str], relevant: set, k: int) -> float:
    if not relevant:
        return 0.0
    return sum(1 for d in ranked[:k] if d in relevant) / len(relevant)


def average_precision(ranked: List[str], relevant: set) -> float:
    if not relevant:
        return 0.0
    score = 0.0
    hits = 0
    for i, d in enumerate(ranked, start=1):
        if d in relevant:
            hits += 1
            score += hits / i
    return score / len(relevant)


def ndcg_at_k(ranked: List[str], rel_scores: Dict[str, int], k: int) -> float:
    def dcg(scores):
        return sum(s / math.log2(i + 2) for i, s in enumerate(scores))

    ideal = sorted(rel_scores.values(), reverse=True)[:k]
    actual = [rel_scores.get(d, 0) for d in ranked[:k]]

    idcg = dcg(ideal)
    return (dcg(actual) / idcg) if idcg > 0 else 0.0


def reciprocal_rank(ranked: List[str], relevant: set) -> float:
    """1 / rank del primo documento rilevante (0 se nessun rilevante)."""
    for i, d in enumerate(ranked, start=1):
        if d in relevant:
            return 1.0 / i
    return 0.0


def success_at_k(ranked: List[str], relevant: set, k: int) -> float:
    """1 se esiste almeno un documento rilevante nei primi k, altrimenti 0."""
    return 1.0 if any(d in relevant for d in ranked[:k]) else 0.0



def build_ranked_list(es: Elasticsearch, target: str, query: str, k: int) -> List[str]:
    def search(index: str, fields: List[str], doc_type: str) -> List[str]:
        body = {"size": k, "query": {"multi_match": {"query": query, "fields": fields}}}
        hits = es.search(index=index, body=body)["hits"]["hits"]
        ranked = []
        for h in hits:
            s = h["_source"]
            if doc_type == "paper":
                ranked.append(s["paper_id"])
            elif doc_type == "table":
                ranked.append(f"{s['paper_id']}::{s['table_id']}")
            elif doc_type == "figure":
                ranked.append(f"{s['paper_id']}::{s['figure_id']}")
        return ranked

    # For metrics we evaluate per-target, not cross mixed (cross would require score calibration).
    if target == "papers":
        return search(INDEX_PAPERS, ["title^2", "abstract", "full_text"], "paper")
    if target == "tables":
        return search(INDEX_TABLES, ["caption^2", "body", "mentions", "context_paragraphs"], "table")
    if target == "figures":
        return search(INDEX_FIGURES, ["caption^2", "mentions", "context_paragraphs"], "figure")
    # default: pick papers as a baseline
    return search(INDEX_PAPERS, ["title^2", "abstract", "full_text"], "paper")

def pct(a, b):
    return (a / b * 100.0) if b else 0.0

def main():
    if not QUERIES_PATH.exists():
        raise FileNotFoundError("Missing queries_llm.jsonl")
    if not QRELS_PATH.exists():
        raise FileNotFoundError("Missing qrels_llm.tsv")

    es = Elasticsearch(ES_HOST)

    # load queries
    queries = []
    with QUERIES_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            queries.append(json.loads(line))

    # load qrels
    qrels = defaultdict(dict)  # qid -> doc_id -> rel
    with QRELS_PATH.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for r in reader:
            qrels[r["qid"]][r["doc_id"]] = int(r["relevance"])

    metrics = defaultdict(list)

    metrics_by_type = {
    "papers": defaultdict(list),
    "tables": defaultdict(list),
    "figures": defaultdict(list),
    }

    # stats globali e per tipo
    label_stats_global = {"total": 0, "rel_pos": 0, "rel_2": 0}
    label_stats_by_type = {
        "papers": {"total": 0, "rel_pos": 0, "rel_2": 0},
        "tables": {"total": 0, "rel_pos": 0, "rel_2": 0},
        "figures": {"total": 0, "rel_pos": 0, "rel_2": 0},
    }


    for q in queries:
        qid = q["qid"]
        qtext = q["text"]
        target = q["target"]

        # We compute metrics only for single-target queries (papers/tables/figures)
        if target not in ("papers", "tables", "figures"):
            continue

        ranked = build_ranked_list(es, target, qtext, TOP_K)

        rel_scores = qrels[qid]


        # conta quanti doc sono stati giudicati per questa query e quanti sono rilevanti
        stats = label_stats_by_type[target]
        for _, r in rel_scores.items():
            label_stats_global["total"] += 1
            stats["total"] += 1
            if r > 0:
                label_stats_global["rel_pos"] += 1
                stats["rel_pos"] += 1
            if r == 2:
                label_stats_global["rel_2"] += 1
                stats["rel_2"] += 1




        relevant = {d for d, r in rel_scores.items() if r > 0}

        metrics["P@10"].append(precision_at_k(ranked, relevant, 10))
        metrics["R@10"].append(recall_at_k(ranked, relevant, 10))
        metrics["MAP"].append(average_precision(ranked, relevant))
        metrics["nDCG@10"].append(ndcg_at_k(ranked, rel_scores, 10))
        metrics["MRR"].append(reciprocal_rank(ranked, relevant))
        metrics["Success@1"].append(success_at_k(ranked, relevant, 1))
        metrics["Success@3"].append(success_at_k(ranked, relevant, 3))
        metrics["Success@5"].append(success_at_k(ranked, relevant, 5))
        metrics["Success@10"].append(success_at_k(ranked, relevant, 10))

        mbt = metrics_by_type[target]
        mbt["P@10"].append(precision_at_k(ranked, relevant, 10))
        mbt["R@10"].append(recall_at_k(ranked, relevant, 10))
        mbt["MAP"].append(average_precision(ranked, relevant))
        mbt["nDCG@10"].append(ndcg_at_k(ranked, rel_scores, 10))
        mbt["MRR"].append(reciprocal_rank(ranked, relevant))
        mbt["Success@1"].append(success_at_k(ranked, relevant, 1))
        mbt["Success@3"].append(success_at_k(ranked, relevant, 3))
        mbt["Success@5"].append(success_at_k(ranked, relevant, 5))
        mbt["Success@10"].append(success_at_k(ranked, relevant, 10))

    report = {
        "metrics": metrics,
        "metrics_by_type": metrics_by_type,
        "labels": label_stats_global
    }
     
    print("\n=== LLM-as-a-Judge Evaluation (proxy) ===")
    for m, vals in metrics.items():
        if vals:
            print(f"{m}: {sum(vals)/len(vals):.3f}  (n={len(vals)})")
        else:
            print(f"{m}: n/a (no evaluable queries)")

    print("\n=== Breakdown per tipo di oggetto ===")
    for t, md in metrics_by_type.items():
        # evita divisione per zero
        if not md["P@10"]:
            continue
        print(f"\n-- {t.upper()} (n={len(md['P@10'])}) --")
        for m, vals in md.items():
            print(f"{m}: {sum(vals)/len(vals):.3f}")


    print("\n=== Distribuzione etichette (LLM-as-a-Judge) ===")
    print(f"GLOBAL: total={label_stats_global['total']}  rel>0={label_stats_global['rel_pos']} ({pct(label_stats_global['rel_pos'], label_stats_global['total']):.1f}%)"
        f"  rel=2={label_stats_global['rel_2']} ({pct(label_stats_global['rel_2'], label_stats_global['total']):.1f}%)")

    for t, st in label_stats_by_type.items():
        print(f"{t.upper()}: total={st['total']}  rel>0={st['rel_pos']} ({pct(st['rel_pos'], st['total']):.1f}%)"
            f"  rel=2={st['rel_2']} ({pct(st['rel_2'], st['total']):.1f}%)")
        

    # --- SALVATAGGIO DEI RISULTATI ---
    OUT_REPORT = Path("data/eval_noLLM/metrics_summary.json")
    with OUT_REPORT.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=4)
    
    print(f"\n✅ Risultati salvati con successo in: {OUT_REPORT}")

if __name__ == "__main__":
    main()
