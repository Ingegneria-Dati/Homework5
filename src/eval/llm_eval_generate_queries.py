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