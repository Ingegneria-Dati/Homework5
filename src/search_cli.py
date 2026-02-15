"""
import argparse
from elasticsearch import Elasticsearch
from .config import ES_HOST, INDEX_PAPERS, INDEX_TABLES, INDEX_FIGURES
from .search_core import search_index, cross_search

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", choices=["papers","tables","figures","cross"], required=True)
    ap.add_argument("--query", required=True)
    ap.add_argument("--size", type=int, default=20)
    args = ap.parse_args()

    es = Elasticsearch(ES_HOST)

    if args.index == "papers":
        res = search_index(es, INDEX_PAPERS, args.query, ["title^2","authors","abstract","full_text"], args.size)
        for h in res["hits"]["hits"]:
            s = h["_source"]
            print(f"- score={h['_score']:.2f} [{s['source']}] {s.get('title','')}")
            print(f"  paper_id={s.get('paper_id')} url={s.get('url')}")
    elif args.index == "tables":
        res = search_index(es, INDEX_TABLES, args.query, ["caption^2","body","mentions","context_paragraphs"], args.size)
        for h in res["hits"]["hits"]:
            s = h["_source"]
            print(f"- score={h['_score']:.2f} Table {s.get('table_id')} (paper={s.get('paper_id')})")
            print(f"  caption={s.get('caption','')[:120]}")
    elif args.index == "figures":
        res = search_index(es, INDEX_FIGURES, args.query, ["caption^2","mentions","context_paragraphs"], args.size)
        for h in res["hits"]["hits"]:
            s = h["_source"]
            print(f"- score={h['_score']:.2f} Figure {s.get('figure_id')} (paper={s.get('paper_id')})")
            print(f"  url={s.get('figure_url','')}")
    else:
        merged = cross_search(es, args.query, size_each=max(5, args.size//3))
        for kind, ns, h in merged[:args.size]:
            s = h["_source"]
            if kind == "paper":
                print(f"- [PAPER] norm={ns:.2f} score={h['_score']:.2f} {s.get('title','')}")
            elif kind == "table":
                print(f"- [TABLE] norm={ns:.2f} score={h['_score']:.2f} {s.get('table_id')} paper={s.get('paper_id')}")
            else:
                print(f"- [FIGURE] norm={ns:.2f} score={h['_score']:.2f} {s.get('figure_id')} paper={s.get('paper_id')}")

if __name__ == "__main__":
    main()
"""











'''
import argparse
from elasticsearch import Elasticsearch
from .config import ES_HOST, INDEX_PAPERS, INDEX_TABLES, INDEX_FIGURES
from .search_core import search_index, cross_search, SearchFilters

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", choices=["papers","tables","figures","cross"], required=True)
    ap.add_argument("--query", required=True)
    ap.add_argument("--size", type=int, default=20)
    ap.add_argument("--source", choices=["arxiv", "pmc"], default=None)
    ap.add_argument("--date-from", dest="date_from", default=None, help="YYYY or YYYY-MM-DD")
    ap.add_argument("--date-to", dest="date_to", default=None, help="YYYY or YYYY-MM-DD")
    ap.add_argument("--query-string", action="store_true", help="use query_string parser")
    args = ap.parse_args()

    es = Elasticsearch(ES_HOST)

    filters = SearchFilters(source=args.source, date_from=args.date_from, date_to=args.date_to)
    use_qs = True if args.query_string else None

    if args.index == "papers":
        res = search_index(
            es,
            INDEX_PAPERS,
            args.query,
            ["title^2", "authors", "abstract", "full_text"],
            args.size,
            use_query_string=use_qs,
            filters=filters,
        )
        for h in res["hits"]["hits"]:
            s = h["_source"]
            print(f"- score={h['_score']:.2f} [{s['source']}] {s.get('title','')}")
            print(f"  paper_id={s.get('paper_id')} url={s.get('url')}")
    elif args.index == "tables":
        res = search_index(es, INDEX_TABLES, args.query, ["caption^2","body","mentions","context_paragraphs"], args.size,
                           use_query_string=use_qs, filters=SearchFilters(source=args.source))
        for h in res["hits"]["hits"]:
            s = h["_source"]
            print(f"- score={h['_score']:.2f} Table {s.get('table_id')} (paper={s.get('paper_id')})")
            print(f"  caption={s.get('caption','')[:120]}")
    elif args.index == "figures":
        res = search_index(es, INDEX_FIGURES, args.query, ["caption^2","mentions","context_paragraphs"], args.size,
                           use_query_string=use_qs, filters=SearchFilters(source=args.source))
        for h in res["hits"]["hits"]:
            s = h["_source"]
            print(f"- score={h['_score']:.2f} Figure {s.get('figure_id')} (paper={s.get('paper_id')})")
            print(f"  url={s.get('figure_url','')}")
    else:
        merged = cross_search(es, args.query, size_each=max(5, args.size//3), size_total=args.size,
                              use_query_string=use_qs, filters=filters)
        for kind, ns, h in merged[:args.size]:
            s = h["_source"]
            if kind == "paper":
                print(f"- [PAPER] norm={ns:.2f} score={h['_score']:.2f} {s.get('title','')}")
            elif kind == "table":
                print(f"- [TABLE] norm={ns:.2f} score={h['_score']:.2f} {s.get('table_id')} paper={s.get('paper_id')}")
            else:
                print(f"- [FIGURE] norm={ns:.2f} score={h['_score']:.2f} {s.get('figure_id')} paper={s.get('paper_id')}")

if __name__ == "__main__":
    main()
'''


import argparse
import sys
import json
from .search_core import es_client, cross_search, SearchFilters

def main():
    parser = argparse.ArgumentParser(description="Search Engine CLI (Paper, Table, Figure)")
    
    parser.add_argument("query", type=str, help="Search query (supports boolean syntax)")
    parser.add_argument("--limit", type=int, default=15, help="Total results to show")
    parser.add_argument("--source", type=str, choices=["arxiv", "pmc"], help="Filter by source")
    parser.add_argument("--from-date", type=str, help="Filter from date (YYYY-MM-DD or YYYY)")
    parser.add_argument("--to-date", type=str, help="Filter to date (YYYY-MM-DD or YYYY)")
    parser.add_argument("--raw", action="store_true", help="Output raw JSON")
    
    args = parser.parse_args()

    # 1. Setup client
    try:
        es = es_client()
        if not es.ping():
            print("Error: Cannot connect to Elasticsearch.")
            sys.exit(1)
    except Exception as e:
        print(f"Connection Error: {e}")
        sys.exit(1)

    # 2. Setup filters
    filters = SearchFilters(
        source=args.source,
        date_from=args.from_date,
        date_to=args.to_date
    )

    # 3. Execute Search
    results = cross_search(
        es, 
        args.query, 
        size_each=20,     # Preleva 20 candidati per tipo
        size_total=args.limit, 
        filters=filters
    )

    # 4. Print Results
    if args.raw:
        # Output JSON puro per integrazioni
        out = []
        for kind, score, hit in results:
            src = hit["_source"]
            out.append({
                "type": kind,
                "score": score,
                "id": hit["_id"],
                "source": src.get("source"),
                "title": src.get("title") or src.get("caption"),
                "date": src.get("date")
            })
        print(json.dumps(out, indent=2))
    else:
        # Output leggibile per umano
        print(f"\n--- Search Results for: '{args.query}' ---\n")
        if not results:
            print("No results found.")
            return

        for i, (kind, score, hit) in enumerate(results, start=1):
            src = hit["_source"]
            
            # Icona carina in base al tipo
            icon = "📄" if kind == "paper" else "📊" if kind == "table" else "🖼️"
            
            title = src.get("title")
            if not title and kind in ("table", "figure"):
                title = src.get("caption", "")[:100] + "..."
            
            paper_id = src.get("paper_id") or src.get("id")
            date_str = src.get("date", "N/A")
            source_db = src.get("source", "UNK")

            print(f"{i:2d}. {icon} [{kind.upper()}] (Score: {score:.4f})")
            print(f"    Title: {title}")
            print(f"    Info:  {source_db} | {date_str} | ID: {paper_id}")
            
            # Mostra snippet evidenziati se ci sono
            highlight = hit.get("highlight", {})
            for field, snippets in highlight.items():
                for s in snippets:
                    clean_snip = s.replace('\n', ' ').strip()
                    print(f"    🔍 match in {field}: ...{clean_snip}...")
            print("-" * 60)

if __name__ == "__main__":
    main()