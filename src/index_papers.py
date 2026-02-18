

import json
from elasticsearch import Elasticsearch, helpers
from .config import (
    ES_HOST, 
    INDEX_PAPERS, 
    INDEX_PARAGRAPHS, 
    INTERMEDIATE_DIR, 
    EMBEDDINGS_ENABLED
)
from .embeddings import available as embeddings_available, embed
from .utils import timed

def main():
    # Setup connessione elastica con timeout generosi
    es = Elasticsearch(
        ES_HOST,
        request_timeout=120,
        retry_on_timeout=True,
        max_retries=5,
    )

    use_vec = EMBEDDINGS_ENABLED and embeddings_available()

    paper_actions = []
    para_actions = []
    
    # Recupera tutti i file JSON intermedi (sia arxiv_*.json che pmc_*.json)
    files = list(INTERMEDIATE_DIR.glob("*.json"))
    print(f"[INFO] Trovati {len(files)} documenti intermedi da indicizzare.")

    with timed("index_papers"):
        for path in files:
            try:
                doc = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                print(f"[ERR] JSON corrotto: {path.name}")
                continue

            # Dati fondamentali
            pid = doc.get("paper_id")
            source = doc.get("source", "unk")
            
            # ID univoco per Elasticsearch (es. "arxiv_2201.1234" o "pmc_PMC12345")
            es_doc_id = f"{source}_{pid}"

            # Testo combinato per eventuale embedding
            ta_text = f"{doc.get('title','')}\n{doc.get('abstract','')}".strip()
            
            vec = None
            if use_vec and ta_text:
                vecs = embed([ta_text])
                vec = vecs[0] if vecs else None

            # --- Preparazione Documento PAPER ---
            src_doc = {
                "paper_id": es_doc_id,      # ID univoco interno
                "original_id": pid,         # ID originale (senza prefisso)
                "source": source,           # "arxiv" o "pmc"
                "url": doc.get("url", ""),
                "title": doc.get("title", ""),
                "authors": doc.get("authors", []),
                "date": doc.get("date"),    # Formato YYYY-MM-DD
                "abstract": doc.get("abstract", ""),
                "full_text": doc.get("full_text", ""), # Testo completo per ricerca
            }
            
            # Aggiunta embedding se abilitato (e se mappato in es_setup)
            # if vec is not None:
            #     src_doc["title_abstract_vec"] = vec

            paper_actions.append({
                "_index": INDEX_PAPERS,
                "_id": es_doc_id,
                "_source": src_doc,
            })

            # --- Preparazione Documenti PARAGRAPHS ---
            # Indicizziamo i singoli paragrafi per il Context Retrieval delle figure
            for i, ptxt in enumerate(doc.get("paragraphs", [])):
                if len(ptxt) < 20: continue # Salta paragrafi troppo brevi
                
                para_actions.append({
                    "_index": INDEX_PARAGRAPHS,
                    "_id": f"{es_doc_id}_{i}",
                    "_source": {
                        "paper_id": es_doc_id, # Riferimento al padre
                        "para_id": i,
                        "text": ptxt,
                        "source": source
                    }
                })

    # Invio in blocco (Bulk)
    if paper_actions:
        print(f"[BULK] Caricamento {len(paper_actions)} papers...")
        with timed("index_papers:bulk", {"docs": len(paper_actions)}):
            helpers.bulk(es, paper_actions, request_timeout=120, refresh=False)
            
    if para_actions:
        print(f"[BULK] Caricamento {len(para_actions)} paragrafi...")
        with timed("index_paragraphs:bulk", {"docs": len(para_actions)}):
            helpers.bulk(es, para_actions, request_timeout=120, refresh=False)

    print(f"[DONE] Indicizzazione completata: Papers={len(paper_actions)}, Paragraphs={len(para_actions)}")

if __name__ == "__main__":
    main()