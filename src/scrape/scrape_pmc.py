"""Scarica >=500 articoli Open Access da PubMedCentral (PMC) su:
'ultra-processed foods AND cardiovascular risk' (query in config.PMC_QUERY).

Pipeline robusta:
1) esearch su PubMed -> PMIDs
2) elink PubMed->PMC -> PMCID numerici disponibili in PMC
3) scarica HTML via efetch (db=pmc)

Uso:
python -m src.scrape_pmc --target 550


import argparse
import time
import random
import json
import requests
from urllib.parse import quote_plus
from .config import PMC_QUERY, PMC_HTML_DIR, RAW_JSON_DIR, LOG_DIR

HEADERS = {"User-Agent": "Homework5 student project"}
LOG = LOG_DIR / "pmc_log.csv"

def pubmed_esearch_all(query: str, target_n: int = 2500, page_size: int = 200):
    term = quote_plus(query)
    pmids = []
    retstart = 0
    while len(pmids) < target_n:
        url = (
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
            f"?db=pubmed&term={term}&retmode=json&retmax={page_size}&retstart={retstart}"
        )
        r = requests.get(url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        data = r.json()
        total = int(data["esearchresult"].get("count", 0))
        page_ids = data["esearchresult"].get("idlist", [])
        if not page_ids:
            break
        pmids.extend(page_ids)
        pmids = list(dict.fromkeys(pmids))
        retstart += page_size
        print(f"[PUBMED] total={total} retstart={retstart} pmids={len(pmids)}")
        time.sleep(0.34)
        if retstart >= total:
            break
    return pmids[:target_n]

def pmids_to_pmcids(pmids, batch_size=200):
    pmcids = []
    for i in range(0, len(pmids), batch_size):
        chunk = pmids[i:i+batch_size]
        ids = ",".join(chunk)
        url = (
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/elink.fcgi"
            f"?dbfrom=pubmed&db=pmc&id={ids}&retmode=json"
        )
        r = requests.get(url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        data = r.json()
        for ls in data.get("linksets", []):
            for ldb in ls.get("linksetdbs", []):
                for pmc_numeric in ldb.get("links", []):
                    pmcids.append(str(pmc_numeric))
        pmcids = list(dict.fromkeys(pmcids))
        print(f"[ELINK] {min(i+batch_size, len(pmids))}/{len(pmids)} -> pmcids={len(pmcids)}")
        time.sleep(0.34)
    return pmcids

def fetch_pmc_html_one(pmc_id: str) -> str | None:
    url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pmc&id={pmc_id}&retmode=html"
    for _ in range(3):
        try:
            r = requests.get(url, headers=HEADERS, timeout=60)
            text = r.text.lower()
            if r.status_code == 200 and ("<html" in text or "<body" in text):
                return r.text
        except Exception:
            pass
        time.sleep(1.3 + random.random())
    return None

def append_log(pmc_id: str, status: str):
    import csv
    new_file = not LOG.exists()
    with LOG.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["id","status"])
        if new_file:
            w.writeheader()
        w.writerow({"id": pmc_id, "status": status})

def load_processed():
    if not LOG.exists():
        return set()
    import csv
    with LOG.open("r", encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        return { (row.get("id") or "").strip() for row in r if (row.get("id") or "").strip() }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=int, default=550, help="quanti HTML salvare (metti >500)")
    args = ap.parse_args()

    processed = load_processed()

    pmids = pubmed_esearch_all(PMC_QUERY, target_n=3000, page_size=200)
    print("[PUBMED] PMIDs:", len(pmids))

    pmcids = pmids_to_pmcids(pmids, batch_size=200)
    print("[PMC] PMCIDs disponibili:", len(pmcids))

    saved = 0
    for pmc_id in pmcids:
        if saved >= args.target:
            break
        if pmc_id in processed:
            continue

        out = PMC_HTML_DIR / f"{pmc_id}.html"
        if out.exists():
            append_log(pmc_id, "SKIP_EXISTS")
            continue

        html = fetch_pmc_html_one(pmc_id)
        if html:
            out.write_text(html, encoding="utf-8", errors="ignore")
            append_log(pmc_id, "OK_HTML")
            saved += 1
            # metadati minimi (alcuni verranno ripresi dal parsing html in build_intermediate)
            (RAW_JSON_DIR / f"pmc_{pmc_id}.json").write_text(json.dumps({"paper_id": pmc_id, "source": "pmc"}, indent=2), encoding="utf-8")
            print(f"[OK/PMC] {pmc_id} saved={saved}")
        else:
            append_log(pmc_id, "FAIL_FETCH")
            print(f"[FAIL/PMC] {pmc_id}")

        time.sleep(0.4)

    print(f"[DONE/PMC] saved={saved} in {PMC_HTML_DIR}")

if __name__ == "__main__":
    main()
"""
import argparse
import time
import random
import json
import requests
import csv
from urllib.parse import quote_plus
from pathlib import Path

# --- CONFIGURAZIONE ---
PMC_XML_DIR = Path("data/pmc_xml")
PMC_XML_DIR.mkdir(parents=True, exist_ok=True)
RAW_JSON_DIR = Path("data/raw_json")
RAW_JSON_DIR.mkdir(parents=True, exist_ok=True)
LOG = Path("data/logs/pmc_log.csv")

HEADERS = {"User-Agent": "Homework5 student project"}

# --- QUERY DIRETTA SU PMC (Database Full Text) ---
# Cerca:
# 1. "ultra-processed food" (singolare/plurale) nel TITOLO o ABSTRACT
# 2. "cardiovascular" E "risk" nel TITOLO o ABSTRACT
# 3. Filtro "open access" per licenza di riuso
PMC_QUERY = (
    '(("ultra-processed food"[Title] OR "ultra-processed food"[Abstract] OR '
    '"ultra-processed foods"[Title] OR "ultra-processed foods"[Abstract] OR '
    '"ultraprocessed"[Title] OR "ultraprocessed"[Abstract]) '
    'AND '
    '("cardiovascular"[Title] OR "cardiovascular"[Abstract]) '
    'AND '
    '("risk"[Title] OR "risk"[Abstract]) '
    'AND "open access"[filter])'
)

def pmc_esearch(query: str, target_n: int = 1000, page_size: int = 100):
    """
    Cerca DIRETTAMENTE nel database PMC (db=pmc).
    Restituisce subito i PMCIDs scaricabili.
    """
    term = quote_plus(query)
    ids = []
    retstart = 0
    
    print(f"[PMC-SEARCH] Avvio ricerca diretta in PMC...")
    print(f"[PMC-SEARCH] Query: {query}\n")
    
    while len(ids) < target_n:
        # NOTA: Qui usiamo db=pmc, non db=pubmed
        url = (
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
            f"?db=pmc&term={term}&retmode=json&retmax={page_size}&retstart={retstart}"
        )
        
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            r.raise_for_status()
            data = r.json()
            
            if "esearchresult" not in data:
                print("[ERR] Risposta API non valida.")
                break

            total = int(data["esearchresult"].get("count", "0"))
            page_ids = data["esearchresult"].get("idlist", [])
            
            if not page_ids:
                if retstart == 0:
                    print(f"[STOP] Trovati 0 risultati in PMC.")
                break
                
            ids.extend(page_ids)
            # Rimuovi duplicati
            ids = list(dict.fromkeys(ids))
            
            retstart += page_size
            print(f"   -> Trovati PMC IDs: {len(ids)}/{total}")
            
            if retstart >= total:
                break
            time.sleep(0.4)
            
        except Exception as e:
            print(f"[ERR] Errore richiesta PMC: {e}")
            break
            
    return ids[:target_n]

def fetch_pmc_xml(pmc_id: str) -> str | None:
    """Scarica XML da PMC usando l'ID."""
    # db=pmc è fondamentale qui
    url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pmc&id={pmc_id}&retmode=xml"
    for _ in range(3):
        try:
            r = requests.get(url, headers=HEADERS, timeout=60)
            if r.status_code == 200 and len(r.text) > 200:
                return r.text
            elif r.status_code == 429: # Rate limit
                time.sleep(5)
        except:
            pass
        time.sleep(1)
    return None

def append_log(pmc_id: str, status: str):
    new_file = not LOG.exists()
    with LOG.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["id","status"])
        if new_file: w.writeheader()
        w.writerow({"id": pmc_id, "status": status})

def load_processed():
    if not LOG.exists(): return set()
    with LOG.open("r", encoding="utf-8") as f:
        return {r["id"] for r in csv.DictReader(f)}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=int, default=550)
    args = ap.parse_args()
    
    # 1. CERCA DIRETTAMENTE IN PMC
    pmc_ids = pmc_esearch(PMC_QUERY, target_n=args.target + 200) # Cerchiamo un po' di più per sicurezza
    
    if not pmc_ids:
        print("Nessun articolo trovato. La query è troppo restrittiva per il database PMC.")
        return

    print(f"[INFO] Inizio download di {len(pmc_ids)} articoli XML...")

    processed = load_processed()
    saved = 0
    
    # 2. SCARICA
    for pmc_id in pmc_ids:
        if saved >= args.target:
            break
        
        # PMC restituisce ID numerici (es. 12345), il file standard è PMC12345
        file_name = f"PMC{pmc_id}"
        
        if file_name in processed or pmc_id in processed:
            continue
            
        # Controllo se file esiste già
        if (PMC_XML_DIR / f"{file_name}.xml").exists():
            print(f"[SKIP] {file_name} esiste già.")
            saved += 1
            continue

        xml = fetch_pmc_xml(pmc_id)
        if xml:
            (PMC_XML_DIR / f"{file_name}.xml").write_text(xml, encoding="utf-8", errors="ignore")
            
            # JSON Metadata
            meta = {
                "paper_id": file_name,
                "pmc_id_raw": pmc_id,
                "source": "pmc_direct",
                "query": PMC_QUERY
            }
            (RAW_JSON_DIR / f"{file_name}.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
            
            append_log(file_name, "OK_XML")
            saved += 1
            print(f"[OK] Salvato {file_name} ({saved}/{args.target})")
        else:
            append_log(file_name, "FAIL_FETCH")
            print(f"[FAIL] {file_name}")
            
        time.sleep(0.5)

    print(f"[FINE] Salvati {saved} XML in {PMC_XML_DIR}")

if __name__ == "__main__":
    main()