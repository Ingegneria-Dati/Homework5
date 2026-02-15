
import json
import os
from pathlib import Path
from openai import OpenAI

OUT_PATH = Path("data/eval/queries_llm.jsonl")
SEEDS_PATH = Path("data/eval/seeds.json")

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
    main()

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