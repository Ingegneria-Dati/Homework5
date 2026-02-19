import argparse
import sys

from .indexing import es_setup, index_papers, index_tables_figures

from .scrape import scrape_arxiv, scrape_pmc 
from . import build_intermediate

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="esegue tutta la pipeline")
    ap.add_argument("--skip-download", action="store_true", help="salta scraping (usa HTML gia' presenti)")
    ap.add_argument("--pmc-target", type=int, default=550)
    args = ap.parse_args()

    # SALVA gli argomenti originali e "svuota" sys.argv per ingannare i sottomoduli
    original_args = sys.argv
    sys.argv = [sys.argv[0]]
    try:
        es_setup.main()
    finally:
        sys.argv = original_args # Ripristina SEMPRE gli argomenti originali

    if args.all and not args.skip_download:
        scrape_arxiv.main()
        sys.argv = ["scrape_pmc", "--target", str(args.pmc_target)]
        scrape_pmc.main()

    build_intermediate.main()
    index_papers.main()
    index_tables_figures.main()

    print("[DONE] Pipeline completata.")

if __name__ == "__main__":
    main()
