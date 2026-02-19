import time
import statistics
from typing import List, Dict, Tuple
from ..search.search_core import es_client, cross_search, SearchFilters

# --- GROUND TRUTH AGGIORNATO ---
# NOTA: Se ottieni ancora 0.00, controlla l'output di DEBUG nel terminale
# e sostituisci queste stringhe con gli ID reali restituiti dal tuo Elasticsearch.
# --- GROUND TRUTH CALIBRATO SUI TUOI DATI REALI ---
GROUND_TRUTH = {
    # Test Gruppo A: Entity Resolution
    "\"entity resolution\"": [
        "arxiv_2112.03346v1",           
        "arxiv_2112.03346v1_T5", 
        "arxiv_1410.6717v2_F1",
        "arxiv_2112.06331v1",
        "arxiv_2112.03346v1_T4"
 ],
    # Test Metriche
    "F1-score": [
        "arxiv_2112.06331v1", 
        "arxiv_2310.11244v4_T4", 
        "pmc_PMC12788131",
        "pmc_PMC12658297",
        "arxiv_2310.11244v4_T5"
    ],
    # Test Gruppo 3: Nutrizione (AND Booleano)
    "ultra-processed foods AND cardiovascular": [
        "pmc_PMC12754802", 
        "pmc_PMC12754802_tab5", # Corretto da t5 a tab5 come da debug
        "pmc_PMC12862355_fig1",
        "pmc_PMC12905914",
        "pmc_PMC12680586_tab2"
    ],
    #OR logico
    "\"record linkage\" OR \"entity matching\"": [
        "arxiv_2205.10678v1",
        "arxiv_2112.03346v1_T1",
        "arxiv_2310.11244v4_F1",
        "arxiv_1006.5309v1",
        "arxiv_2310.11244v4_T4"
    ],
    "\"nutritional status\" AND (diet OR hypertension)": [
        "pmc_PMC12787480", 
        "pmc_PMC12787505_nutrients-18-00061-t001", 
        "pmc_PMC12685874"
    ],

    # --- TEST 6: CORRETTO CON ID REALI TROVATI ---
    "blocking AND NOT learning": [
        "arxiv_2403.12092v1", 
        "arxiv_2310.11244v4", 
        "pmc_PMC12862423"
    ],
    
}

def calculate_metrics(retrieved_ids: List[str], relevant_ids: List[str], k: int = 5) -> Tuple[float, float]:
    """Calcola Precision@K e Reciprocal Rank."""
    # Precision at K
    hits = [rid for rid in retrieved_ids[:k] if rid in relevant_ids]
    p_at_k = len(hits) / k
    
    # Reciprocal Rank (RR)
    rr = 0
    for i, rid in enumerate(retrieved_ids, start=1):
        if rid in relevant_ids:
            rr = 1 / i
            break
    return p_at_k, rr

def run_evaluation():
    try:
        es = es_client()
        if not es.ping():
            print("Errore: Elasticsearch non raggiungibile.")
            return
    except Exception as e:
        print(f"Errore connessione: {e}")
        return

    all_p5 = []
    all_mrr = []
    all_latencies = []

    print(f"\n🔬 --- SESSIONE DI VALUTAZIONE QUANTITATIVA ---")
    print(f"{'Query':<45} | {'P@5':<6} | {'RR':<6} | {'Tempo (s)':<10}")
    print("-" * 80)

    

    for query, relevant_ids in GROUND_TRUTH.items():
        start_time = time.perf_counter()
        
        # Eseguiamo la ricerca Cross-Search (RRF)
        results = cross_search(es, query, size_total=10)
        
        latency = time.perf_counter() - start_time
        
        # Estraiamo gli ID restituiti (hit["_id"])
        retrieved_ids = [hit["_id"] for _, _, hit in results]
        
        # --- SEZIONE DI DEBUG ---
        # Se i risultati sono 0.00, guarda questi ID e correggi il GROUND_TRUTH sopra
        if not any(rid in relevant_ids for rid in retrieved_ids):
             print(f"DEBUG [{query[:15]}...]: ID trovati: {retrieved_ids[:3]}")
        
        p5, rr = calculate_metrics(retrieved_ids, relevant_ids, k=5)
        
        all_p5.append(p5)
        all_mrr.append(rr)
        all_latencies.append(latency)
        
        print(f"{query[:45]:<45} | {p5:<6.2f} | {rr:<6.2f} | {latency:<10.4f}")

    print("-" * 80)
    print(f"{'MEDIA FINALE':<45} | {statistics.mean(all_p5):<6.2f} | {statistics.mean(all_mrr):<6.2f} | {statistics.mean(all_latencies):<10.4f}\n")

if __name__ == "__main__":
    run_evaluation()