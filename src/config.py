from pathlib import Path
import re
ES_HOST = "http://localhost:9200"

# =======================
# Search / IR improvements
# =======================

# Analyzer name used in ES mappings
TEXT_ANALYZER = "hw5_en"

# Cross-index fusion (papers/tables/figures)
RRF_K = 60  # Reciprocal Rank Fusion constant

# Default query parser
# - False: use robust multi_match (recommended)
# - True:  use query_string to allow boolean operators and advanced syntax
USE_QUERY_STRING_BY_DEFAULT = False

# Context extraction for tables/figures
# - "mlt"     : Elasticsearch more_like_this over paragraph index
# - "overlap" : lexical overlap between table/figure terms and paragraphs
# - "hybrid"  : union of both (deduplicated)
CONTEXT_METHOD = "hybrid"
OVERLAP_THRESHOLD = 0.30
CONTEXT_TOP_K = 8

# Embeddings / vector search (optional)
EMBEDDINGS_ENABLED = False
# If embeddings are enabled, we try to use sentence-transformers locally.
EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIMS = 384

# Rerank (optional). If enabled and embeddings enabled, we can re-score top N docs.
HYBRID_RERANK_TOP_N = 50

# Temporal filters defaults (UI/CLI can override)
DEFAULT_DATE_FROM = None  
DEFAULT_DATE_TO = None    

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

# Gruppo (arXiv)
#ARXIV_PHRASES = ["entity resolution", "entity matching"]
#ARXIV_PHRASES = [
#    r"\bentity\W+resolution\b",
#    r"\bentity\W+matching\b",
#]

ARXIV_PHRASES = [
    re.compile(r'\bEntity\s+resolution\b', re.IGNORECASE),
    re.compile(r'\bEntity\s+matching\b', re.IGNORECASE),
]


query_parts = [
    '(ti:entity resolution)',
    '(abs:entity resolution)',
    '(ti:entity matching)',
    '(abs:entity matching)'
]
ARXIV_QUERY = " OR ".join(query_parts)
ARXIV_MAX_RESULTS = 5000


PMC_XML_DIR = Path("data/pmc_xml")
PMC_XML_DIR.mkdir(parents=True, exist_ok=True)
RAW_JSON_DIR = Path("data/raw_json")
RAW_JSON_DIR.mkdir(parents=True, exist_ok=True)
LOG = Path("data/pmc_log.csv")
# Query Aggiornata con filtro Open Access per garantire il download
PMC_QUERY = '(("ultra-processed foods"[Title/Abstract] OR "processed food"[Title/Abstract] OR "ultraprocessed foods"[Title/Abstract]) AND "cardiovascular risk"[Title/Abstract] AND "open access"[filter])'


# Cartella per le immagini scaricate
IMAGES_DIR = Path("data/images")
IMAGES_DIR.mkdir(parents=True, exist_ok=True)

# URL del servizio Open Access di PMC
OA_URL = "https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi"


# Indici
INDEX_PAPERS = "hw5_papers"
INDEX_PARAGRAPHS = "hw5_paragraphs"
INDEX_TABLES = "hw5_tables"
INDEX_FIGURES = "hw5_figures"
EMBEDDINGS_ENABLED = False
