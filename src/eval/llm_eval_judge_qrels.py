
import csv
import json
import os
import time
from pathlib import Path
from typing import List, Dict, Any, Tuple
from src.search.search_core import cross_search

from elasticsearch import Elasticsearch
from openai import OpenAI

# --- CONFIGURAZIONE ---
from src.config import ES_HOST, INDEX_PAPERS, INDEX_TABLES, INDEX_FIGURES

QUERIES_PATH = Path("data/eval/queries_llm.jsonl")
OUT_QRELS = Path("data/eval/qrels_llm.tsv")

MODEL_JUDGE = "llama-3.1-8b-instant"

TOP_N_POOL = int(os.getenv("EVAL_TOP_N_POOL", "50"))
MAX_BODY_CHARS = int(os.getenv("EVAL_MAX_BODY_CHARS", "1400"))

def get_openai_client() -> OpenAI:
    api_key = os.getenv("GROQ_API_KEY", "GROQ_API_KEY")
    base_url = "https://api.groq.com/openai/v1"
    return OpenAI(api_key=api_key, base_url=base_url)

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


    
def retrieve_pool(es, query, top_n=50):
    """
    Recupera i top_n risultati usando il sistema finale cross_search (RRF).
    """
    results = cross_search(
        es,
        query,
        size_each=20,      # candidati per indice
        size_total=top_n   # totale finale dopo fusione
    )

    pool = []

    for kind, score, hit in results:
        src = hit["_source"]

        if kind == "paper":
            doc_id = src.get("paper_id") or hit["_id"]
            text = f"{src.get('title','')} {src.get('abstract','')}"
        elif kind == "table":
            doc_id = f"{src.get('paper_id')}::{src.get('table_id')}"
            text = f"{src.get('caption','')} {src.get('body','')}"
        else:  # figure
            doc_id = f"{src.get('paper_id')}::{src.get('figure_id')}"
            text = f"{src.get('caption','')}"

        pool.append({
            "doc_id": doc_id,
            "doc_type": kind,
            "text": text[:3000]  # limite sicurezza token
        })

    return pool     

# NOTA: Ora restituisce un Tuple contenente (voto, spiegazione)
def judge_relevance(client: OpenAI, qtext: str, doc_type: str, text: str) -> Tuple[int, str]:
    content = clip(text, MAX_BODY_CHARS)

    prompt = f"""
You are a strict relevance judge for an information retrieval evaluation.

Query:
{qtext}

Object type: {doc_type}
Object content:
{content}

Label relevance on a 3-point scale:
0 = Not relevant
1 = Partially relevant
2 = Highly relevant

Return ONLY a valid JSON object with EXACTLY two keys: "relevance" (integer) and "explanation" (a brief string explaining why).
Example: {{"relevance": 1, "explanation": "The text mentions the topic briefly but lacks detail."}}
""".strip()

    max_retries = 3
    for attempt in range(max_retries):
        try:
            resp = client.chat.completions.create(
                model=MODEL_JUDGE,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
            )
            text = resp.choices[0].message.content.strip()
            
            if "```" in text:
                text = text.replace("```json", "").replace("```", "").strip()

            obj = json.loads(text)
            rel = int(obj.get("relevance", 0))
            exp = str(obj.get("explanation", "No explanation provided."))
            
            # Pulisce la spiegazione da ritorni a capo per non rompere il CSV
            exp = exp.replace("\n", " ").replace("\t", " ")

            if rel not in (0, 1, 2):
                return 0, exp
            return rel, exp
        
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(2)
                continue
            else:
                print(f"Errore Judge dopo {max_retries} tentativi: {e}")
                return 0, "Errore API LLM"

def main():
    if not QUERIES_PATH.exists():
        raise FileNotFoundError("Missing queries file.")

    es = es_client()
    llm = get_openai_client()

    queries = []
    with QUERIES_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            queries.append(json.loads(line))

    processed_qids = set()
    OUT_QRELS.parent.mkdir(parents=True, exist_ok=True)
    
    file_mode = "w"
    write_header = True
    
    if OUT_QRELS.exists():
        print("Trovato file esistente, leggo le query già fatte...")
        with OUT_QRELS.open("r", encoding="utf-8") as f:
            reader = csv.reader(f, delimiter="\t")
            header = next(reader, None)
            for row in reader:
                if row:
                    processed_qids.add(row[0])
        
        if processed_qids:
            print(f"Già completate {len(processed_qids)} query. Riprendo da lì.")
            file_mode = "a"
            write_header = False

    with OUT_QRELS.open(file_mode, encoding="utf-8", newline="") as out:
        w = csv.writer(out, delimiter="\t")
        
        if write_header:
            # AGGIUNTA COLONNA EXPLANATION
            w.writerow(["qid", "doc_type", "doc_id", "relevance", "explanation"])

        for q in queries:
            qid = q["qid"]
            if qid in processed_qids:
                continue

            qtext = q["text"]
            target = q["target"]

            pool = retrieve_pool(es, qtext, TOP_N_POOL)
            
            current_rows = []
            print(f"Giudicando {qid} ({target}) - {len(pool)} docs...", end="", flush=True)

            for item in pool:
                doc_type = item["doc_type"]
                doc_id = item["doc_id"]
                text = item["text"]

                rel, exp = judge_relevance(llm, qtext, doc_type, text)
                current_rows.append([qid, doc_type, doc_id, str(rel), exp])

                time.sleep(0.2)


            for row in current_rows:
                w.writerow(row)
            out.flush()
            
            print(" [OK]")

    print(f"[DONE] File salvato in {OUT_QRELS}")

if __name__ == "__main__":
    main()


