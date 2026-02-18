

import time
import random
import json
from urllib.parse import urljoin
import requests
import arxiv

# Assicurati che questi import funzionino nel tuo progetto
from .config import ARXIV_QUERY, ARXIV_MAX_RESULTS, ARXIV_HTML_DIR, RAW_JSON_DIR, LOG_DIR
from .utils import append_csv, load_processed_ids, clean_text

ARXIV_BASE = "https://arxiv.org"

# --- MODIFICA 1: HEADERS DA VERO BROWSER (CHROME) ---
# Copiamo esattamente quello che invia un browser reale per non essere bloccati.
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,it;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0",
}

LOG = LOG_DIR / "arxiv_log.csv"

BLOCKED_PATTERNS = [
    "recaptcha", "captcha", "unusual traffic", "rate limit", "too many requests",
    "access denied", "blocked", "please verify", "robot", "automated access",
    "challenge", "turnstile" # Aggiunti nuovi tipi di blocco comuni
]

# --- MODIFICA 2: SESSIONE GLOBALE (MANTIENE I COOKIE) ---
# Usando una sessione, se Ar5iv ci dà un cookie di "benvenuto", lo riusiamo
# nelle chiamate successive, sembrando un utente che naviga.
session = requests.Session()
session.headers.update(HEADERS)


# --------------------------- FILTRO LOCALE ---------------------------

def matches_title_abs(title: str | None, abstract: str | None) -> bool:
    """
    Filtro locale STRETTO: controlla che compaiano le frasi esatte.
    """
    t = (title or "").lower()
    a = (abstract or "").lower()
    full_text = f"{t} {a}"

    if "entity resolution" in full_text:
        return True
    if "entity matching" in full_text:
        return True
    
    return False


# --------------------------- HTTP ROBUSTO (STEALTH) ---------------------------

def _is_blocked(content: bytes | str) -> bool:
    text = content.decode("utf-8", errors="ignore").lower() if isinstance(content, (bytes, bytearray)) else str(content).lower()
    return any(p in text for p in BLOCKED_PATTERNS)


def safe_get(url: str, retries: int = 3, base_backoff: float = 3.0, max_backoff: float = 30.0) -> requests.Response | None:
    """
    GET usando la SESSIONE globale.
    Smette subito su 404.
    Gestisce i blocchi con attese più lunghe.
    """
    for attempt in range(retries):
        try:
            # USA session.get INVECE DI requests.get
            resp = session.get(url, timeout=30)

            # Se è 404, il file non esiste. Stop.
            if resp.status_code == 404:
                return None 

            # Rate limit / Server Error
            if resp.status_code in (429, 403, 503, 500, 502, 504):
                retry_after = resp.headers.get("Retry-After")
                if retry_after and retry_after.strip().isdigit():
                    sleep_s = min(max_backoff, float(retry_after.strip()))
                else:
                    sleep_s = min(max_backoff, base_backoff * (2 ** attempt)) + random.uniform(1.0, 3.0)
                
                print(f"    HTTP {resp.status_code} su {url} -> sleep {sleep_s:.1f}s")
                time.sleep(sleep_s)
                continue

            # resp.raise_for_status() # Non alzare eccezione subito, controlliamo il contenuto

            # Contenuto bloccato (Cloudflare, Captcha)
            if _is_blocked(resp.content):
                sleep_s = min(max_backoff, base_backoff * (2 ** attempt)) + random.uniform(2.0, 5.0)
                print(f"    Pagina bloccata rilevata su {url} -> sleep {sleep_s:.1f}s")
                
                # Se siamo bloccati, rinnoviamo la sessione (nuovi cookie)
                session.cookies.clear() 
                session.headers.update(HEADERS)
                
                time.sleep(sleep_s)
                continue
            
            # Se siamo qui, è andata bene (o è un errore non bloccante)
            if resp.status_code == 200:
                return resp
            
            return None

        except requests.RequestException as e:
            sleep_s = min(max_backoff, base_backoff * (2 ** attempt)) + random.uniform(1.0, 2.0)
            time.sleep(sleep_s)

    return None


# --------------------------- DOWNLOAD HTML ---------------------------

def download_html_via_latexml(arxiv_id: str) -> tuple[str | None, str | None]:
    """
    Strategia 3 livelli: ArXiv -> Ar5iv (v1) -> Ar5iv (Clean)
    """
    
    # 1. ArXiv Ufficiale
    official_url = f"{ARXIV_BASE}/html/{arxiv_id}"
    resp = safe_get(official_url, retries=1)

    if resp and "<html" in resp.text.lower():
        text_lower = resp.text.lower()
        # Controllo che non sia una pagina di errore mascherata
        if "latexml" in text_lower or "ltx_" in text_lower or "article" in text_lower:
            return resp.text, official_url

    # 2. Ar5iv (Con versione)
    ar5iv_url_v = f"https://ar5iv.labs.arxiv.org/html/{arxiv_id}"
    resp = safe_get(ar5iv_url_v, retries=2)

    if resp and "<html" in resp.text.lower() and "no article found" not in resp.text.lower():
        # A volte Ar5iv mette un "loading..." in JS. Lo ignoriamo per ora, prendiamo quello che c'è.
        return resp.text, ar5iv_url_v

    # 3. Ar5iv (Senza versione - FALLBACK POTENTE)
    clean_id = arxiv_id.split('v')[0]
    if clean_id != arxiv_id:
        ar5iv_url_clean = f"https://ar5iv.labs.arxiv.org/html/{clean_id}"
        # print(f"    [Tentativo Extra] Provo Ar5iv senza versione: {ar5iv_url_clean}")
        resp = safe_get(ar5iv_url_clean, retries=2)

        if resp and "<html" in resp.text.lower() and "no article found" not in resp.text.lower():
            return resp.text, ar5iv_url_clean

    return None, None


# --------------------------- MAIN ---------------------------

def iter_results_with_backoff(client: arxiv.Client, search: arxiv.Search, max_backoff: int = 600):
    backoff = 10 
    while True:
        try:
            for r in client.results(search):
                yield r
            return 
        except arxiv.HTTPError as e:
            if "HTTP 429" in str(e):
                sleep_s = min(max_backoff, backoff) + random.uniform(0, 2.0)
                print(f"[arXiv API] Rate limit (429). Dormo {sleep_s:.1f}s...")
                time.sleep(sleep_s)
                backoff = min(max_backoff, int(backoff * 2))
                continue
            raise


def main():
    processed = load_processed_ids(LOG)

    print(f"--- Avvio Scraping arXiv (Stealth Mode Attiva) ---")
    print(f"Query API: {ARXIV_QUERY}")
    print(f"Max results API: {ARXIV_MAX_RESULTS}")

    client = arxiv.Client(page_size=50, delay_seconds=3.0, num_retries=5)

    search = arxiv.Search(
        query=ARXIV_QUERY,
        max_results=ARXIV_MAX_RESULTS,
        sort_by=arxiv.SortCriterion.Relevance,
    )

    ok_html = 0
    matched = 0
    total_seen = 0
    html_unavailable = 0

    for res in iter_results_with_backoff(client, search):
        total_seen += 1

        arxiv_id = res.get_short_id()
        safe_id = arxiv_id.replace("/", "_")

        if safe_id in processed:
            continue

        title = clean_text(res.title or "")
        summary = clean_text(res.summary or "")

        hit = matches_title_abs(title, summary)

        status = "NO_MATCH"
        canonical_html_url = f"{ARXIV_BASE}/html/{arxiv_id}"
        used_html_url = None

        if hit:
            matched += 1
            html, used_html_url = download_html_via_latexml(arxiv_id)
            
            if html:
                (ARXIV_HTML_DIR / f"{safe_id}.html").write_text(html, encoding="utf-8", errors="ignore")
                status = "OK_HTML"
                ok_html += 1
            else:
                status = "NO_HTML"
                html_unavailable += 1
        else:
            status = "SKIPPED_IRRELEVANT"

        meta = {
            "paper_id": arxiv_id,
            "safe_id": safe_id,
            "source": "arxiv",
            "url": canonical_html_url,
            "latexml_url": used_html_url,
            "title": title,
            "authors": [a.name for a in (res.authors or [])],
            "date": (res.published.isoformat() if res.published else ""),
            "abstract": summary,
        }
        (RAW_JSON_DIR / f"{safe_id}.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

        append_csv(LOG, {"id": safe_id, "status": status, "title": title}, ["id", "status", "title"])

        if total_seen % 20 == 0: # Print più frequente per vedere che succede
            print(f"[arXiv] Visti={total_seen} | Rilevanti={matched} | HTML Salvati={ok_html} | No HTML={html_unavailable}")

        # Sleep randomico per sembrare umani (tra 1 e 2 secondi)
        time.sleep(random.uniform(1.0, 2.0))

    print("-" * 50)
    print(f"[DONE] Visti Totali: {total_seen}")
    print(f"[DONE] Rilevanti: {matched}")
    print(f"[DONE] HTML Salvati: {ok_html}")
    print(f"[DONE] No HTML: {html_unavailable}")
    print(f"File nella cartella: {len(list(ARXIV_HTML_DIR.glob('*.html')))}")


if __name__ == "__main__":
    main()