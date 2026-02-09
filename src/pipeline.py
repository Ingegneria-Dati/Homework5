import argparse
from . import es_setup, scrape_arxiv, scrape_pmc, build_intermediate, index_papers, index_tables_figures

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="esegue tutta la pipeline")
    ap.add_argument("--skip-download", action="store_true", help="salta scraping (usa HTML gia' presenti)")
    ap.add_argument("--pmc-target", type=int, default=550)
    args = ap.parse_args()

    es_setup.main()

    if args.all and not args.skip_download:
        scrape_arxiv.main()
        # scrape_pmc ha argparse interno; lo richiamo come funzione principale equivalente:
        import sys
        sys.argv = ["scrape_pmc", "--target", str(args.pmc_target)]
        scrape_pmc.main()

    build_intermediate.main()
    index_papers.main()
    index_tables_figures.main()

    print("[DONE] Pipeline completata.")

if __name__ == "__main__":
    main()
