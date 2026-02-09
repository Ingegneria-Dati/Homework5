"""Scarica >=500 articoli Open Access da PubMedCentral (PMC) su:
'ultra-processed foods AND cardiovascular risk' (query in config.PMC_QUERY).

Pipeline robusta:
1) esearch su PubMed -> PMIDs
2) elink PubMed->PMC -> PMCID numerici disponibili in PMC
3) scarica HTML via efetch (db=pmc)

Uso:
python -m src.scrape_pmc --target 550
"""

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
