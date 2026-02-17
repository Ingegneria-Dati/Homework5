import csv
import json
import os
import time
from pathlib import Path
from typing import List, Dict, Any, Tuple
from elasticsearch import Elasticsearch

# --- CONFIGURAZIONE ---
from src.config import ES_HOST, INDEX_PAPERS, INDEX_TABLES, INDEX_FIGURES

QUERIES_PATH = Path("src/eval/queries_llm.jsonl")
OUT_QRELS = Path("data/eval/qrels_llm.tsv")

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













'''import csv
import json
import os
import time
from pathlib import Path
from typing import List, Dict, Any, Tuple

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
    api_key = os.getenv("GROQ_API_KEY", "api")
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
        if did in seen:
            continue
        seen.add(did)
        uniq.append((dt, src))

    return uniq[:n]

# NOTA: Ora restituisce un Tuple contenente (voto, spiegazione)
def judge_relevance(client: OpenAI, qtext: str, doc_type: str, src: Dict[str, Any]) -> Tuple[int, str]:
    if doc_type == "paper":
        title = clip(src.get("title", ""), 240)
        abstract = clip(src.get("abstract", ""), 900)
        content = f"TITLE: {title}\nABSTRACT: {abstract}"
    elif doc_type == "table":
        caption = clip(src.get("caption", ""), 300)
        body = clip(src.get("body", ""), MAX_BODY_CHARS)
        content = f"CAPTION: {caption}\nBODY: {body}"
    elif doc_type == "figure":
        caption = clip(src.get("caption", ""), 380)
        ctx = src.get("context_paragraphs") or []
        ctx_text = clip(" ".join(ctx), 900)
        content = f"CAPTION: {caption}\nCONTEXT: {ctx_text}"
    else:
        raise ValueError(doc_type)

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

            pool = retrieve_pool(es, target, qtext, TOP_N_POOL)
            
            current_rows = []
            print(f"Giudicando {qid} ({target}) - {len(pool)} docs...", end="", flush=True)

            for doc_type, src in pool:
                doc_id = build_doc_id(doc_type, src)
                # Ora spacchettiamo i due valori
                rel, exp = judge_relevance(llm, qtext, doc_type, src)
                current_rows.append([qid, doc_type, doc_id, str(rel), exp])
                
                time.sleep(0.2) 

            for row in current_rows:
                w.writerow(row)
            out.flush()
            
            print(" [OK]")

    print(f"[DONE] File salvato in {OUT_QRELS}")

if __name__ == "__main__":
    main()'''

'''
import csv
import json
import os
import time
from pathlib import Path
from typing import List, Dict, Any, Tuple

from elasticsearch import Elasticsearch
from openai import OpenAI

# --- CONFIGURAZIONE ---
# Assicurati che queste variabili d'ambiente o config siano corrette
from src.config import ES_HOST, INDEX_PAPERS, INDEX_TABLES, INDEX_FIGURES

QUERIES_PATH = Path("data/eval/queries_llm.jsonl")
OUT_QRELS = Path("data/eval/qrels_llm.tsv")

# CAMBIO MODELLO: Usiamo quello "instant" (8b) per evitare il limite dei 70b
# Se finisci anche questo, prova: "mixtral-8x7b-32768"
#MODEL_JUDGE = "llama-3.3-70b-versatile"

MODEL_JUDGE = "llama-3.1-8b-instant"

TOP_N_POOL = int(os.getenv("EVAL_TOP_N_POOL", "50"))
MAX_BODY_CHARS = int(os.getenv("EVAL_MAX_BODY_CHARS", "1400"))

def get_openai_client() -> OpenAI:
    # La tua chiave
    #api_key = os.getenv("GROQ_API_KEY")

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

def retrieve_pool(es: Elasticsearch, target: str, query: str, n: int) -> List[Tuple[str, Dict[str, Any]]]:
    out = []
    def search(index: str, fields: List[str]) -> List[Dict[str, Any]]:
        # Aggiunta gestione errori ES base
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
        if did in seen:
            continue
        seen.add(did)
        uniq.append((dt, src))

    return uniq[:n]

def judge_relevance(client: OpenAI, qtext: str, doc_type: str, src: Dict[str, Any]) -> int:
    if doc_type == "paper":
        title = clip(src.get("title", ""), 240)
        abstract = clip(src.get("abstract", ""), 900)
        content = f"TITLE: {title}\nABSTRACT: {abstract}"
    elif doc_type == "table":
        caption = clip(src.get("caption", ""), 300)
        body = clip(src.get("body", ""), MAX_BODY_CHARS)
        content = f"CAPTION: {caption}\nBODY: {body}"
    elif doc_type == "figure":
        caption = clip(src.get("caption", ""), 380)
        ctx = src.get("context_paragraphs") or []
        ctx_text = clip(" ".join(ctx), 900)
        content = f"CAPTION: {caption}\nCONTEXT: {ctx_text}"
    else:
        raise ValueError(doc_type)

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

Return ONLY valid JSON: {{"relevance": 0}} or {{"relevance": 1}} or {{"relevance": 2}} AND {"explanation": "string"}.
""".strip()

    # Riprova fino a 3 volte in caso di errore momentaneo
    max_retries = 3
    for attempt in range(max_retries):
        try:
            resp = client.chat.completions.create(
                model=MODEL_JUDGE,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
            )
            text = resp.choices[0].message.content.strip()
            
            # Pulizia JSON base
            if "```" in text:
                text = text.replace("```json", "").replace("```", "").strip()

            obj = json.loads(text)
            rel = int(obj["relevance"])
            if rel not in (0, 1, 2):
                return 0 # Default a 0 se impazzisce
            return rel
        
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(2) # Aspetta un attimo prima di riprovare
                continue
            else:
                print(f"Errore Judge dopo {max_retries} tentativi: {e}")
                return 0

def main():
    if not QUERIES_PATH.exists():
        raise FileNotFoundError("Missing queries file.")

    es = es_client()
    llm = get_openai_client()

    # 1. Carica query
    queries = []
    with QUERIES_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            queries.append(json.loads(line))

    # 2. Controllo Ripristino: Vediamo cosa abbiamo già fatto
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
                    processed_qids.add(row[0]) # Il primo campo è il QID
        
        if processed_qids:
            print(f"Già completate {len(processed_qids)} query. Riprendo da lì.")
            file_mode = "a" # Append mode
            write_header = False

    # 3. Apertura file in modalità sicura
    with OUT_QRELS.open(file_mode, encoding="utf-8", newline="") as out:
        w = csv.writer(out, delimiter="\t")
        
        if write_header:
            w.writerow(["qid", "doc_type", "doc_id", "relevance"])

        for q in queries:
            qid = q["qid"]
            
            # SKIP se già fatta
            if qid in processed_qids:
                continue

            qtext = q["text"]
            target = q["target"]

            pool = retrieve_pool(es, target, qtext, TOP_N_POOL)
            
            current_rows = []
            print(f"Giudicando {qid} ({target}) - {len(pool)} docs...", end="", flush=True)

            for doc_type, src in pool:
                doc_id = build_doc_id(doc_type, src)
                rel = judge_relevance(llm, qtext, doc_type, src)
                current_rows.append([qid, doc_type, doc_id, str(rel)])
                
                # Sleep minimo per evitare Rate Limit RPM
                time.sleep(0.2) 

            # Scrittura immediata su file
            for row in current_rows:
                w.writerow(row)
            out.flush() # Forza il salvataggio su disco
            
            print(" [OK]")

    print(f"[DONE] File salvato in {OUT_QRELS}")

if __name__ == "__main__":
    main()
'''