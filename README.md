# Homework 5 – Advanced Scientific Search (papers, tables, figures) – Gruppo A + Medico

Questo progetto implementa TUTTI i punti richiesti dall'Homework 5:
- corpus arXiv HTML per **Gruppo A**: titolo/abstract contiene `"Entity resolution"` o `"Entity matching"`
- corpus PMC Open Access (>=500) per **Gruppo 4 medico**: *ultra-processed foods AND cardiovascular risk*
- indicizzazione su Elasticsearch: papers + paragraphs + tables + figures
- ricerca base e avanzata: CLI + Web UI (Streamlit)
- tabelle come oggetti di prima classe (renderizzate in HTML) e figure con preview
- contesti: mentions dirette + paragrafi contestuali via `more_like_this` su indice paragrafi

## 0) Prerequisiti
- Python 3.10+ (consigliato 3.11)
- Docker Desktop (consigliato) per Elasticsearch

## 1) Avvio Elasticsearch (Docker)
Esegui:

```bash
docker run --name es-hw5 -p 9200:9200 -p 9300:9300 \
  -e "discovery.type=single-node" \
  -e "xpack.security.enabled=false" \
  -e "ES_JAVA_OPTS=-Xms1g -Xmx1g" \
  elasticsearch:8.12.0
```

Verifica:
```bash
curl http://localhost:9200
```

## 2) Setup Python (venv consigliato)
Windows PowerShell:
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```


## 3) Pipeline completa (consigliata)
Da root progetto:

```bash
python -m src.pipeline --all
```

Questo:
1) crea indici ES
2) scarica arXiv HTML (tutti quelli disponibili con match)
3) scarica >=550 PMC OA (per garantire >=500 validi)
4) costruisce JSON intermedi
5) indicizza papers + paragrafi
6) indicizza tabelle + figure (con mentions e context_paragraphs)

### Esecuzione step-by-step
```bash
python -m src.es_setup
python -m src.scrape_arxiv
python -m src.scrape_pmc --target 550
python -m src.build_intermediate
python -m src.index_papers
python -m src.index_tables_figures
```

## 4) UI Web (Streamlit)
```bash
streamlit run src/app_streamlit.py
```
Apri il link mostrato (tipicamente http://localhost:8501).

## 5) CLI
Esempi:
```bash
python -m src.search_cli --index papers --query '"entity resolution"'
python -m src.search_cli --index tables --query '(F1 OR precision OR recall) AND (matching OR linkage)'
python -m src.search_cli --index figures --query '(workflow OR pipeline) AND (entity resolution)'
python -m src.search_cli --index cross --query '"ultra-processed" AND cardiovascular'
```

## 6) Cartelle dati
- `data/arxiv_html/` : HTML arXiv scaricati
- `data/pmc_html/` : HTML PMC OA scaricati
- `data/raw_json/` : metadati grezzi (arXiv API / parsing html)
- `data/intermediate_json/` : JSON strutturati (paper, paragraphs, tables, figures)

## 7) Note pratiche
- Non tutti i paper arXiv hanno la pagina `/html/<id>`: quelli senza HTML vengono loggati come `NO_HTML`.
- Per PMC la ricerca parte da PubMed e poi filtra i record che hanno una versione in PMC; questo è il modo robusto per raggiungere >=500 OA.

