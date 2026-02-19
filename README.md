# Scientific Research Search Engine

Motore di ricerca unificato per articoli scientifici provenienti da:

- **arXiv (HTML / ar5iv)**: titolo/abstract contiene `"Entity resolution"` o `"Entity matching"`
- **PubMed Central (PMC XML)**: titolo/abstract `"ultra-processed foods AND cardiovascular risk"`

## Pipeline
Il sistema implementa una pipeline completa:
1. Scraping documenti
2. Parsing e normalizzazione
3. Creazione JSON intermedi strutturati
4. Indicizzazione in Elasticsearch
5. Ricerca cross-index (paper, tabelle, figure)
6. Interfaccia CLI e Web (Streamlit)
   
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

## 3) Esecuzione step-by-step
```bash
python -m src.indexing.es_setup
python -m src.scrape.scrape_arxiv
python -m src.scrape.scrape_pmc 
python -m src.build_intermediate
python -m src.indexing.index_papers
python -m src.indexing.index_tables_figures
```

## 4) UI Web (Streamlit)
```bash
streamlit run src/search/app_streamlit.py
```
<img width="1713" height="908" alt="image" src="https://github.com/user-attachments/assets/49c44ec6-ecbf-4604-bb92-6fea7050ad89" />




## 5) CLI
Esempi:
```bash
python -m src.search.search_cli "entity resolution"
python -m src.search.search_cli "entity matching" --source arxiv
python -m src.search.search_cli "ultra-processed foods cardiovascular" --source pmc
```

<img width="1735" height="237" alt="image" src="https://github.com/user-attachments/assets/ca9c1f5c-5ddc-4a3e-89c5-5454b1621f27" />

## Valutazioni
- **Modello LLM llama**

<img width="1347" height="241" alt="image" src="https://github.com/user-attachments/assets/0a731b94-e9cc-400d-b1eb-794e39673a5d" />

- **Manual**
<img width="1346" height="417" alt="image" src="https://github.com/user-attachments/assets/098597d2-22fe-4222-872a-a28e97e50802" />
