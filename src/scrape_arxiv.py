"""Scarica HTML da arXiv per Gruppo A.
Requisito: titolo o abstract contiene 'Entity resolution' oppure 'Entity matching' (case-insensitive).
Nota: non tutti i paper arXiv hanno la pagina /html/<id>; quelli senza HTML vengono loggati come NO_HTML.
"""

import time
import requests
import arxiv
from .config import ARXIV_QUERY, ARXIV_MAX_RESULTS, ARXIV_HTML_DIR, RAW_JSON_DIR, LOG_DIR, ARXIV_PHRASES
from .utils import append_csv, load_processed_ids, clean_text

HEADERS = {"User-Agent": "Homework5 student project"}
LOG = LOG_DIR / "arxiv_log.csv"

def matches_group_a(title: str, summary: str) -> bool:
    t = (title or "").lower()
    s = (summary or "").lower()
    return any(p in t for p in ARXIV_PHRASES) or any(p in s for p in ARXIV_PHRASES)

def download_html(url: str) -> str | None:
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        if r.status_code == 200 and "<html" in r.text.lower():
            return r.text
        return None
    except Exception:
        return None

def main():
    processed = load_processed_ids(LOG)
    client = arxiv.Client(page_size=100, delay_seconds=1.0, num_retries=3)

    search = arxiv.Search(
        query=ARXIV_QUERY,
        max_results=ARXIV_MAX_RESULTS,
        sort_by=arxiv.SortCriterion.Relevance,
    )

    ok_html = 0
    matched = 0
    total_seen = 0

    for res in client.results(search):
        total_seen += 1
        arxiv_id = res.get_short_id()
        if arxiv_id in processed:
            continue

        title = clean_text(res.title or "")
        summary = clean_text(res.summary or "")
        hit = matches_group_a(title, summary)

        status = "NO_MATCH"
        html_url = f"https://arxiv.org/html/{arxiv_id}"
        if hit:
            matched += 1
            html = download_html(html_url)
            if html:
                (ARXIV_HTML_DIR / f"{arxiv_id}.html").write_text(html, encoding="utf-8", errors="ignore")
                status = "OK_HTML"
                ok_html += 1
            else:
                status = "NO_HTML"

        # metadati grezzi
        meta = {
            "paper_id": arxiv_id,
            "source": "arxiv",
            "url": html_url,
            "title": title,
            "authors": [a.name for a in (res.authors or [])],
            "date": (res.published.isoformat() if res.published else ""),
            "abstract": summary,
        }
        (RAW_JSON_DIR / f"{arxiv_id}.json").write_text(__import__("json").dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

        append_csv(LOG, {"id": arxiv_id, "status": status, "title": title}, ["id","status","title"])

        if total_seen % 50 == 0:
            print(f"[arXiv] seen={total_seen} matched={matched} html_saved={ok_html}")

        time.sleep(0.15)

    print(f"[DONE/arXiv] seen={total_seen} matched={matched} html_saved={ok_html}")
    print(f"HTML in folder: {len(list(ARXIV_HTML_DIR.glob('*.html')))}")

if __name__ == "__main__":
    main()
