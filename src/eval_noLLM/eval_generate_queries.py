



import json
import random
from pathlib import Path

# Manteniamo i tuoi percorsi originali
OUT_PATH = Path("data/eval_noLLM/queries_noLLM.jsonl")
SEEDS_PATH = Path("src/eval_noLLM/seeds.json")

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



