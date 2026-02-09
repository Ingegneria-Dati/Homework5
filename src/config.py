from pathlib import Path

ES_HOST = "http://localhost:9200"

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ARXIV_HTML_DIR = DATA / "arxiv_html"
PMC_HTML_DIR = DATA / "pmc_html"
RAW_JSON_DIR = DATA / "raw_json"
INTERMEDIATE_DIR = DATA / "intermediate_json"
LOG_DIR = DATA / "logs"

ARXIV_HTML_DIR.mkdir(parents=True, exist_ok=True)
PMC_HTML_DIR.mkdir(parents=True, exist_ok=True)
RAW_JSON_DIR.mkdir(parents=True, exist_ok=True)
INTERMEDIATE_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Gruppo A (arXiv)
ARXIV_PHRASES = ["entity resolution", "entity matching"]
ARXIV_QUERY = '(all:"entity resolution" OR all:"entity matching")'
ARXIV_MAX_RESULTS = 5000

# Gruppo medico (PMC)
PMC_QUERY = (
    '("ultra-processed" OR ultraprocessed OR "NOVA") '
    'AND (cardiovascular OR cardiometabolic OR heart OR stroke OR hypertension OR "cardiovascular risk")'
)

# Indici
INDEX_PAPERS = "hw5_papers"
INDEX_PARAGRAPHS = "hw5_paragraphs"
INDEX_TABLES = "hw5_tables"
INDEX_FIGURES = "hw5_figures"
