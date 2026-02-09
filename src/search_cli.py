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
