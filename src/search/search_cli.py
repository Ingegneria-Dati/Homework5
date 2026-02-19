import argparse
import sys
import json

from .search_core import es_client, cross_search, SearchFilters
from ..config import INDEX_PAPERS, INDEX_TABLES, INDEX_FIGURES

def get_paper_title_cached(es, paper_doc_id: str, cache: dict, index_papers: str) -> str:
    """
    paper_doc_id per tables/figures: "<source>_<paper_id>".
    Prova:
      1) GET per _id
      2) fallback: term query su campo paper_id
    """
    if not paper_doc_id:
        return ""
    if paper_doc_id in cache:
        return cache[paper_doc_id]

    title = ""

    # (1) try by _id
    try:
        doc = es.get(index=index_papers, id=paper_doc_id, request_timeout=10)
        src = doc.get("_source", {}) if isinstance(doc, dict) else {}
        title = (src.get("title") or "").strip()
    except Exception:
        pass

    # (2) fallback: term on paper_id
    if not title:
        try:
            res = es.search(
                index=index_papers,
                body={
                    "size": 1,
                    "_source": ["title"],
                    "query": {"term": {"paper_id": paper_doc_id}},
                },
                request_timeout=10,
            )
            hits = res.get("hits", {}).get("hits", [])
            if hits:
                title = (hits[0].get("_source", {}).get("title") or "").strip()
        except Exception:
            pass

    cache[paper_doc_id] = title
    return title

def main():
    parser = argparse.ArgumentParser(description="Search Engine CLI (Paper, Table, Figure)")

    parser.add_argument("query", type=str, help="Search query (supports boolean syntax)")
    parser.add_argument("--limit", type=int, default=15, help="Total results to show")
    parser.add_argument("--source", type=str, choices=["arxiv", "pmc"], help="Filter by source")
    parser.add_argument("--from-date", type=str, help="Filter from date (YYYY-MM-DD or YYYY)")
    parser.add_argument("--to-date", type=str, help="Filter to date (YYYY-MM-DD or YYYY)")
    parser.add_argument("--raw", action="store_true", help="Output raw JSON")

    args = parser.parse_args()

    # 1) Setup client
    try:
        es = es_client()
        if not es.ping():
            print("Error: Cannot connect to Elasticsearch.")
            sys.exit(1)
    except Exception as e:
        print(f"Connection Error: {e}")
        sys.exit(1)

    paper_title_cache = {}

    # 2) Setup filters
    filters = SearchFilters(
        source=args.source,
        date_from=args.from_date,
        date_to=args.to_date,
    )

    # 3) Execute search
    results = cross_search(
        es,
        args.query,
        INDEX_PAPERS,
        INDEX_TABLES,
        INDEX_FIGURES,
        size_each=20,          # candidati per tipo
        size_total=args.limit,
        filters=filters,
    )

    # 4) Print results
    if args.raw:
        out = []
        for kind, score, hit in results:
            src = hit.get("_source", {}) or {}
            out.append({
                "type": kind,
                "score": score,
                "id": hit.get("_id"),
                "source": src.get("source"),
                "title": src.get("title") or src.get("caption"),
                "date": src.get("date"),
            })
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return

    print(f"\n--- Search Results for: '{args.query}' ---\n")

    if not results:
        print("No results found.")
        return

    for i, (kind, score, hit) in enumerate(results, start=1):
        src = hit.get("_source", {}) or {}

        icon = "📄" if kind == "paper" else "📊" if kind == "table" else "🖼️"

        title = (src.get("title") or "").strip()

        if kind in ("table", "figure"):
            paper_doc_id = (src.get("paper_id") or "").strip()  # per tables/figures è <source>_<paper_id>
            paper_title = get_paper_title_cached(es, paper_doc_id, paper_title_cache, INDEX_PAPERS)
            if paper_title:
                title = paper_title
            else:
                # fallback: se proprio non trovi il paper, usa caption
                cap = (src.get("caption") or "").strip()
                title = (cap[:100] + "...") if len(cap) > 100 else cap

        paper_id = src.get("paper_id") or src.get("id") or hit.get("_id")
        date_str = src.get("date") or "N/A"
        source_db = src.get("source") or "UNK"

        print(f"{i:2d}. {icon} [{kind.upper()}] (Score: {score:.4f})")
        print(f"    Title: {title if title else '(no title)'}")
        if kind == "table":
            print(f"    Obj:   table_id={src.get('table_id','N/A')}")
        elif kind == "figure":
            print(f"    Obj:   figure_id={src.get('figure_id','N/A')}")

        print(f"    Info:  {source_db} | {date_str} | ID: {paper_id}")

        highlight = hit.get("highlight", {}) or {}
        for field, snippets in highlight.items():
            for s in snippets or []:
                clean_snip = str(s).replace("\n", " ").strip()
                print(f"    🔍 match in {field}: ...{clean_snip}...")

        print("-" * 60)


if __name__ == "__main__":
    main()
