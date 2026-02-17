



import json
import random
from pathlib import Path

# Manteniamo i tuoi percorsi originali
OUT_PATH = Path("data/eval/queries_llm.jsonl")
SEEDS_PATH = Path("src/eval/seeds.json")

def generate_offline_queries(domain_name, description, target):
    """
    Simula la generazione di un LLM usando i termini del dominio.
    Genera 6 query: 2 Natural Language, 2 Keyword, 2 Boolean.
    """
    # Estraiamo parole chiave dalla descrizione per rendere le query realistiche
    keywords = [w.strip(",.") for w in description.split() if len(w) > 4]
    
    # Termini specifici per target
    target_terms = {
        "tables": ["table", "results", "hazard ratio", "metrics", "data"],
        "figures": ["figure", "pipeline", "workflow", "plot", "diagram"],
        "papers": ["study", "research", "analysis", "introduction"],
        "cross": ["results", "workflow", "table", "figure"]
    }
    
    t_words = target_terms.get(target, ["research"])
    
    # Template per le query
    queries = [
        # Natural Language
        f"What are the latest findings in {domain_name} regarding {random.choice(keywords)}?",
        f"How to evaluate {random.choice(keywords)} in a scientific {target[:-1]}?",
        # Keywords
        f"{domain_name} {random.choice(keywords)} {random.choice(t_words)}",
        f"{random.choice(keywords)} {random.choice(t_words)} analysis",
        # Boolean/Advanced
        f"\"{random.choice(keywords)}\" AND {random.choice(t_words)}",
        f"\"{domain_name}\" OR \"{random.choice(keywords)}\""
    ]
    return queries

def main():
    if not SEEDS_PATH.exists():
        print(f"ERRORE: Non trovo il file {SEEDS_PATH}. Assicurati di essere nella cartella giusta.")
        return

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    seeds = json.loads(SEEDS_PATH.read_text(encoding="utf-8"))

    all_queries = []
    qid_counter = 1

    for domain_name, cfg in seeds.items():
        description = cfg["description"]
        targets = cfg["targets"]

        for target in targets:
            print(f"Generando query locali per {domain_name} - {target}...")
            
            # Sostituiamo la chiamata a Groq con la nostra funzione locale
            queries = generate_offline_queries(domain_name, description, target)

            for qtext in queries:
                qobj = {
                    "qid": f"LQ{qid_counter:03d}",
                    "domain": domain_name,
                    "target": target,
                    "text": qtext.strip()
                }
                all_queries.append(qobj)
                qid_counter += 1

    # Salvataggio nel formato jsonl richiesto
    with OUT_PATH.open("w", encoding="utf-8") as f:
        for q in all_queries:
            f.write(json.dumps(q, ensure_ascii=False) + "\n")

    print(f"\n[DONE] Generate {len(all_queries)} query simulate in {OUT_PATH}")
    print("Nota: Poiché non è stata usata una API Key, le query sono state generate tramite template locali.")

if __name__ == "__main__":
    main()

















'''import json
import os
from pathlib import Path
from openai import OpenAI

OUT_PATH = Path("src/eval/queries_llm.jsonl")
SEEDS_PATH = Path("src/eval/seeds.json")

# Modello Groq
MODEL = "llama-3.3-70b-versatile"

def get_client() -> OpenAI:
    # Usa la tua API Key di Groq (puoi anche hardcodarla qui come hai fatto nel Judge, se preferisci)
    api_key = os.getenv("GROQ_API_KEY", "LA_TUA_API_KEY_QUI")

    base_url = "https://api.groq.com/openai/v1"
    
    print(f"DEBUG: Usando API Key che inizia con: {api_key[:10]}...")
    return OpenAI(api_key=api_key, base_url=base_url)

def main():
    if not SEEDS_PATH.exists():
        print(f"ERRORE: Non trovo il file {SEEDS_PATH}. Assicurati di essere nella cartella giusta.")
        return

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    seeds = json.loads(SEEDS_PATH.read_text(encoding="utf-8"))
    client = get_client()

    all_queries = []
    qid_counter = 1

    for domain_name, cfg in seeds.items():
        description = cfg["description"]
        targets = cfg["targets"]

    for target in targets:
            # --- PROMPT A PROVA DI ERRORE JSON ---
            prompt = f"""
You are generating realistic search queries for a scientific search system.
Domain: {domain_name}
Domain description: {description}
Target object type: {target}

Task:
Generate 6 realistic user queries. To thoroughly test the search engine, provide exactly:
- 2 Natural Language queries
- 2 Keyword-based queries
- 2 Boolean/Advanced queries using exact match quotes, AND, or OR.

Rules:
- Include at least 2 queries that are table-oriented (mention e.g. 'table', 'results', 'hazard ratio', 'ablation', 'metrics') when target is tables/cross.
- Include at least 2 queries that are figure-oriented (mention e.g. 'figure', 'pipeline', 'workflow', 'forest plot', 'kaplan meier') when target is figures/cross.
- Return ONLY a valid JSON array of strings. 
- CRITICAL JSON RULE: Do NOT use double quotes inside the strings. Use single quotes for exact matches.
Example format: ["natural language question", "keyword keyword", "'exact phrase' AND keyword"]
""".strip()

            try:
                resp = client.chat.completions.create(
                    model=MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.7,
                )
                
                text = resp.choices[0].message.content.strip()
                
                if text.startswith("```json"):
                    text = text.replace("```json", "").replace("```", "")
                elif text.startswith("```"):
                    text = text.replace("```", "")
                
                queries = json.loads(text.strip())
                
                if not isinstance(queries, list) or not all(isinstance(q, str) for q in queries):
                     print(f"Warning: formato JSON non valido per {domain_name}-{target}")
                     continue

            except Exception as e:
                print(f"Errore durante la chiamata API o parsing per {domain_name}-{target}: {e}")
                continue

            for qtext in queries:
                # Sostituisce gli apici singoli con virgolette doppie per Elasticsearch
                qtext_clean = qtext.replace("'", '"').strip()
                
                qobj = {
                    "qid": f"LQ{qid_counter:03d}",
                    "domain": domain_name,
                    "target": target,
                    "text": qtext_clean
                }
                all_queries.append(qobj)
                qid_counter += 1

    with OUT_PATH.open("w", encoding="utf-8") as f:
        for q in all_queries:
            f.write(json.dumps(q, ensure_ascii=False) + "\n")

    print(f"[DONE] Generate {len(all_queries)} queries miste (NL, Keyword, Booleane) in {OUT_PATH}")

if __name__ == "__main__":
    main()'''

'''

import json
import os
from pathlib import Path
from openai import OpenAI

OUT_PATH = Path("data/eval/queries_llm.jsonl")
SEEDS_PATH = Path("data/eval/seeds.json")

# Modello: usiamo un modello supportato da Groq se non specificato diversamente
# "llama3" è gratuito e veloce su Groq
MODEL = "llama-3.3-70b-versatile"

def get_client() -> OpenAI:
    api_key = os.getenv("GROQ_API_KEY")
    base_url = "https://api.groq.com/openai/v1"
    
    print(f"DEBUG: Usando API Key che inizia con: {api_key[:10]}...")
    print(f"DEBUG: Usando Base URL: {base_url}")

    return OpenAI(api_key=api_key, base_url=base_url)

def main():
    # Crea la cartella se non esiste
    if not SEEDS_PATH.exists():
        print(f"ERRORE: Non trovo il file {SEEDS_PATH}. Assicurati di essere nella cartella giusta.")
        return

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    seeds = json.loads(SEEDS_PATH.read_text(encoding="utf-8"))
    client = get_client()

    all_queries = []
    qid_counter = 1

    for domain_name, cfg in seeds.items():
        description = cfg["description"]
        targets = cfg["targets"]

        for target in targets:
            prompt = f"""
You are generating realistic search queries for a scientific search system.
Domain: {domain_name}
Domain description: {description}
Target object type: {target}

Task:
Generate 6 realistic user queries (short, like a researcher would type).
Rules:
- Do NOT include quotes unless needed.
- Prefer query phrases that would retrieve relevant content.
- Include at least 2 queries that are table-oriented (mention e.g. 'table', 'results', 'hazard ratio', 'ablation', 'metrics') when target is tables/cross.
- Include at least 2 queries that are figure-oriented (mention e.g. 'figure', 'pipeline', 'workflow', 'forest plot', 'kaplan meier') when target is figures/cross.
Return ONLY a JSON array of strings. Example: ["query 1", "query 2"]
""".strip()

            try:
                # CORREZIONE QUI: La sintassi standard è chat.completions.create
                resp = client.chat.completions.create(
                    model=MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.6,
                )
                
                # Otteniamo il testo dalla risposta
                text = resp.choices[0].message.content.strip()
                
                # Pulizia base se il modello mette markdown
                if text.startswith("```json"):
                    text = text.replace("```json", "").replace("```", "")
                
                queries = json.loads(text)
                
                if not isinstance(queries, list) or not all(isinstance(q, str) for q in queries):
                     print(f"Warning: formato JSON non valido per {domain_name}-{target}")
                     continue

            except Exception as e:
                print(f"Errore durante la chiamata API o parsing: {e}")
                continue

            for qtext in queries:
                qobj = {
                    "qid": f"LQ{qid_counter:03d}",
                    "domain": domain_name,
                    "target": target,
                    "text": qtext.strip()
                }
                all_queries.append(qobj)
                qid_counter += 1

    with OUT_PATH.open("w", encoding="utf-8") as f:
        for q in all_queries:
            f.write(json.dumps(q, ensure_ascii=False) + "\n")

    print(f"[DONE] Wrote {len(all_queries)} queries to {OUT_PATH}")

if __name__ == "__main__":
    main()
'''