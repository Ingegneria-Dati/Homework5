import csv
import json
import os
import time
from pathlib import Path
from typing import List, Dict, Any, Tuple
from elasticsearch import Elasticsearch

# --- CONFIGURAZIONE ---
from src.config import ES_HOST, INDEX_PAPERS, INDEX_TABLES, INDEX_FIGURES

QUERIES_PATH = Path("data/eval_noLLM/queries_noLLM.jsonl")
OUT_QRELS = Path("data/eval_noLLM/qrels_noLLM.tsv")

TOP_N_POOL = 10  # Ridotto per velocità, puoi aumentarlo a 20 o 50
MAX_BODY_CHARS = 1400

def es_client() -> Elasticsearch:
    return Elasticsearch(ES_HOST)

def clip(s: str, n: int) -> str:
    s = s or ""
    s = " ".join(s.split())
    return s[:n]

def build_doc_id(doc_type: str, src: Dict[str, Any]) -> str:
    if doc_type == "paper":
        return src["paper_id"]
    if doc_type == "table":
        return f"{src['paper_id']}::{src['table_id']}"
    if doc_type == "figure":
        return f"{src['paper_id']}::{src['figure_id']}"
    raise ValueError(doc_type)

def retrieve_pool(es: Elasticsearch, target: str, query: str, n: int) -> List[Tuple[str, Dict[str, Any]]]:
    out = []
    def search(index: str, fields: List[str]) -> List[Dict[str, Any]]:
        try:
            body = {"size": n, "query": {"multi_match": {"query": query, "fields": fields}}}
            return es.search(index=index, body=body)["hits"]["hits"]
        except Exception as e:
            print(f"Errore ricerca ES su {index}: {e}")
            return []

    if target in ("papers", "cross"):
        hits = search(INDEX_PAPERS, ["title^2", "abstract", "full_text"])
        out += [("paper", h["_source"]) for h in hits]
    if target in ("tables", "cross"):
        hits = search(INDEX_TABLES, ["caption^2", "body", "mentions", "context_paragraphs"])
        out += [("table", h["_source"]) for h in hits]
    if target in ("figures", "cross"):
        hits = search(INDEX_FIGURES, ["caption^2", "mentions", "context_paragraphs"])
        out += [("figure", h["_source"]) for h in hits]

    seen = set()
    uniq = []
    for dt, src in out:
        did = (dt, build_doc_id(dt, src))
        if did in seen: continue
        seen.add(did)
        uniq.append((dt, src))
    return uniq[:n]

def heuristic_judge(qtext: str, content: str) -> Tuple[int, str]:
    """
    Sostituisce l'LLM con un'analisi lessicale.
    - 2: Molte parole chiave della query presenti.
    - 1: Almeno una parola chiave rilevante presente.
    - 0: Nessun match significativo.
    """
    query_words = set(qtext.lower().replace('"', '').split())
    content_words = set(content.lower().split())
    
    # Rimuove parole comuni (stop words semplificate)
    stop_words = {"what", "how", "the", "and", "for", "with", "are", "regarding", "study"}
    query_words = query_words - stop_words
    
    matches = query_words.intersection(content_words)
    match_count = len(matches)
    
    if match_count >= 3:
        return 2, f"Highly relevant: found {match_count} keyword matches ({', '.join(list(matches)[:3])})."
    elif match_count >= 1:
        return 1, f"Partially relevant: found {match_count} keyword matches."
    else:
        return 0, "Not relevant: no significant lexical overlap found."

def judge_relevance(qtext: str, doc_type: str, src: Dict[str, Any]) -> Tuple[int, str]:
    # Estrazione contenuto per il giudice (stessa logica dello script originale)
    if doc_type == "paper":
        content = f"{src.get('title', '')} {src.get('abstract', '')}"
    elif doc_type == "table":
        content = f"{src.get('caption', '')} {src.get('body', '')}"
    elif doc_type == "figure":
        content = f"{src.get('caption', '')} {' '.join(src.get('context_paragraphs', []))}"
    else:
        content = ""
    
    return heuristic_judge(qtext, clip(content, 2000))

def main():
    if not QUERIES_PATH.exists():
        print(f"ERRORE: File query non trovato in {QUERIES_PATH}")
        return

    es = es_client()
    queries = []
    with QUERIES_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            queries.append(json.loads(line))

    OUT_QRELS.parent.mkdir(parents=True, exist_ok=True)
    
    with OUT_QRELS.open("w", encoding="utf-8", newline="") as out:
        w = csv.writer(out, delimiter="\t")
        w.writerow(["qid", "doc_type", "doc_id", "relevance", "explanation"])

        for q in queries:
            qid, qtext, target = q["qid"], q["text"], q["target"]
            print(f"Valutando {qid} [{target}]...", end=" ", flush=True)

            pool = retrieve_pool(es, target, qtext, TOP_N_POOL)
            for doc_type, src in pool:
                doc_id = build_doc_id(doc_type, src)
                rel, exp = judge_relevance(qtext, doc_type, src)
                w.writerow([qid, doc_type, doc_id, str(rel), exp])
            
            print("[OK]")

    print(f"\n[DONE] Giudizi euristici salvati in {OUT_QRELS}")

if __name__ == "__main__":
    main()


