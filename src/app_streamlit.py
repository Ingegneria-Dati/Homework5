

"""
import sys
import os
import streamlit as st
from elasticsearch import Elasticsearch
from pathlib import Path  # <--- AGGIUNGI QUESTA RIGA

# Aggiunge la root del progetto al path
# Aggiunge la root del progetto al path
sys.path.append(os.path.dirname(os.path.abspath(__file__)) + "/..")

from src.config import ES_HOST, INDEX_PAPERS, INDEX_TABLES, INDEX_FIGURES
from src.search_core import search_index, cross_search, SearchFilters

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="Scientific Search", layout="wide", page_icon="🔬")

try:
    es = Elasticsearch(ES_HOST)
    if not es.ping():
        st.error(f"Impossibile connettersi a Elasticsearch su {ES_HOST}")
except Exception as e:
    st.error(f"Errore connessione: {e}")

st.title("🔬 Scientific Research Engine")
st.markdown("Ricerca unificata su **ArXiv** (HTML) e **PubMed Central** (XML)")

# --- SIDEBAR: FILTRI ---
with st.sidebar:
    st.header("🔍 Filtri")
    
    # Filtro Sorgente
    source_sel = st.selectbox("Sorgente Dati", ["(Tutte)", "arxiv", "pmc"], index=0)
    source_filter = None if source_sel == "(Tutte)" else source_sel
    
    st.markdown("---")
    
    # Opzioni Avanzate
    use_query_string = st.checkbox("Sintassi Avanzata (AND/OR)", value=False, help="Usa sintassi Lucene es: 'cancer AND risk'")
    topk = st.slider("Risultati Max", 5, 100, 20)

# Costruzione Oggetto Filtri (Senza date)
filters = SearchFilters(
    source=source_filter,
    date_from=None,
    date_to=None
)

# --- BARRA DI RICERCA ---
query = st.text_input("Inserisci la tua query", placeholder="es. 'entity resolution' OR 'ultra-processed foods'", value="")
search_mode = st.radio("Cerca in:", ["Cross-Search (RRF)", "Solo Articoli", "Solo Tabelle", "Solo Figure"], horizontal=True)

# Funzione Helper per visualizzare le card
def render_card(title, score, meta, content=None, url=None, image_url=None, html_content=None):
    with st.container():
        st.markdown(f"#### {title}")
        
        # Metadata badge
        src_str = meta.get('source', 'UNK').upper()
        color = "blue" if "ARXIV" in src_str else "green"
        
        st.markdown(f":{color}[**{src_str}**] | 🔑 Score: `{score:.3f}`")
        
        if content:
            safe_content = content or ""
            st.caption(safe_content[:600] + "..." if len(safe_content) > 600 else safe_content)
        
        # Rendering HTML (per Tabelle PMC)
        if html_content:
            with st.expander("Visualizza Tabella"):
                st.components.v1.html(html_content, height=300, scrolling=True)
        # Immagini (per Figure)
        elif image_url:
            paper_id = meta.get("paper_id")
            fig_id = meta.get("figure_id")
            
            # 1. Tentativo: Cerca l'immagine scaricata localmente
            # Costruiamo il percorso relativo: data/images/ID_PAPER/ID_FIGURA.*
            local_found = False
            img_folder = Path("data/images") / paper_id
            
            if img_folder.exists():
                # Cerchiamo un file che inizi con l'ID figura (es. F1.jpg, F1.png)
                matches = list(img_folder.glob(f"{fig_id}.*"))
                if matches:
                    local_path = matches[0]
                    st.image(str(local_path), caption=f"Anteprima Locale: {fig_id}", width=600)
                    local_found = True

            # 2. Fallback: Se non è locale, prova il link remoto o mostra link diretto
            if not local_found:
                try:
                    # Rimuoviamo eventuali doppie estensioni rimasugli dei vecchi test
                    clean_url = image_url.replace(".jpg.jpg", ".jpg")
                    st.image(clean_url, caption="Anteprima Remota", width=600)
                except Exception:
                    st.warning("Impossibile caricare l'anteprima (file locale mancante e link remoto protetto).")
                
                # In ogni caso, per PMC, aggiungi il link per aprirla nel browser
                if "pmc" in str(meta.get("source")).lower():
                    st.markdown(f"🔗 [Apri immagine nel browser]({image_url})")

        if url:
            st.link_button("📄 Leggi Full Text", url)
        
        st.divider()

# --- LOGICA DI RICERCA ---
if query:
    if st.button("Cerca") or query:
        with st.spinner("Ricerca in corso..."):
            
            # 1. CROSS SEARCH (Misto)
            if search_mode == "Cross-Search (RRF)":
                results = cross_search(
                    es, query, 
                    size_each=20, 
                    size_total=topk, 
                    use_query_string=use_query_string, 
                    filters=filters
                )
                
                st.success(f"Trovati {len(results)} risultati rilevanti combinati.")
                
                for kind, score, hit in results:
                    s = hit["_source"]
                    if kind == "paper":
                        render_card(f"📄 {s.get('title')}", score, s, s.get("abstract"), s.get("url"))
                    elif kind == "table":
                        render_card(f"📊 Tabella {s.get('table_id')}", score, s, s.get("caption"), s.get("url"), html_content=s.get("table_html") or s.get("body"))
                    elif kind == "figure":
                        render_card(f"🖼️ Figura {s.get('figure_id')}", score, s, s.get("caption"), s.get("url"), image_url=s.get("figure_url"))

            # 2. SOLO ARTICOLI
            elif search_mode == "Solo Articoli":
                res = search_index(es, INDEX_PAPERS, query, ["title^3", "abstract^2", "full_text"], topk, use_query_string=use_query_string, filters=filters)
                hits = res.get("hits", {}).get("hits", [])
                st.write(f"Trovati {len(hits)} articoli.")
                for h in hits:
                    render_card(h["_source"].get("title"), h["_score"], h["_source"], h["_source"].get("abstract"), h["_source"].get("url"))

            # 3. SOLO TABELLE
            elif search_mode == "Solo Tabelle":
                res = search_index(es, INDEX_TABLES, query, ["caption^3", "body^2", "mentions"], topk, use_query_string=use_query_string, filters=filters)
                hits = res.get("hits", {}).get("hits", [])
                st.write(f"Trovate {len(hits)} tabelle.")
                for h in hits:
                    s = h["_source"]
                    render_card(f"Tabella {s.get('table_id')}", h["_score"], s, s.get("caption"), s.get("url"), html_content=s.get("table_html"))

            # 4. SOLO FIGURE
            elif search_mode == "Solo Figure":
                res = search_index(es, INDEX_FIGURES, query, ["caption^3", "mentions"], topk, use_query_string=use_query_string, filters=filters)
                hits = res.get("hits", {}).get("hits", [])
                st.write(f"Trovate {len(hits)} figure.")
                for h in hits:
                    s = h["_source"]
                    render_card(f"Figura {s.get('figure_id')}", h["_score"], s, s.get("caption"), s.get("url"), image_url=s.get("figure_url"))
else:
    st.info("Inserisci una query per iniziare.")

"""

import sys
import os
import streamlit as st
from elasticsearch import Elasticsearch
from pathlib import Path
import re
# Aggiunge la root del progetto al path
sys.path.append(os.path.dirname(os.path.abspath(__file__)) + "/..")

from src.config import ES_HOST, INDEX_PAPERS, INDEX_TABLES, INDEX_FIGURES
from src.search_core import search_index, cross_search, SearchFilters
PROJECT_ROOT = Path(__file__).resolve().parents[1]   # src/.. = root
IMAGES_DIR = PROJECT_ROOT / "data" / "images"
# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="Scientific Search", layout="wide", page_icon="🔬")

try:
    es = Elasticsearch(ES_HOST)
    if not es.ping():
        st.error(f"Impossibile connettersi a Elasticsearch su {ES_HOST}")
except Exception as e:
    st.error(f"Errore connessione: {e}")

st.title("🔬 Scientific Research Engine")
st.markdown("Ricerca unificata su **ArXiv** (HTML) e **PubMed Central** (XML)")

# --- SIDEBAR: FILTRI ---
with st.sidebar:
    st.header("🔍 Affina Ricerca")
    
    source_sel = st.selectbox("Sorgente Dati", ["(Tutte)", "arxiv", "pmc"], index=0)
    source_filter = None if source_sel == "(Tutte)" else source_sel
    
    st.subheader("📅 Intervallo Temporale")
    # Ipotizziamo articoli dal 2000 al 2026
    date_start = st.text_input("Dal (AAAA-MM-DD)", value="")
    date_end = st.text_input("Al (AAAA-MM-DD)", value="")
    
    st.markdown("---")
    use_query_string = st.checkbox("Sintassi Avanzata (Lucene)", value=True)
    topk = st.slider("Risultati da mostrare", 5, 50, 15)

# Aggiorna l'oggetto filters
filters = SearchFilters(
    source=source_filter, 
    date_from=date_start if date_start else None, 
    date_to=date_end if date_end else None
)
# --- BARRA DI RICERCA ---
query = st.text_input("Inserisci la tua query", placeholder="es. 'entity resolution' OR 'ultra-processed foods'", value="")
search_mode = st.radio("Cerca in:", ["Cross-Search (RRF)", "Solo Articoli", "Solo Tabelle", "Solo Figure"], horizontal=True)

def normalize_pmc_folder(paper_id: str) -> str:
    """
    Converte vari formati di paper_id in nome cartella immagini.
    Esempi:
      pmc_PMC12693445 -> PMC12693445
      PMC12693445     -> PMC12693445
      pmc_12693445    -> PMC12693445
      12693445        -> PMC12693445
    """
    if not paper_id:
        return ""
    pid = paper_id.strip()
    m = re.search(r"(PMC\d+)", pid, flags=re.IGNORECASE)
    if m:
        return m.group(1).upper()
    # fallback: se è solo numero
    m2 = re.fullmatch(r"\d+", pid)
    if m2:
        return f"PMC{pid}"
    return pid

def normalize_fig_stem(figure_id: str) -> str:
    """
    Prova a ridurre figure_id a uno stem corto tipo F1, F12.
    Esempi:
      F1 -> F1
      nutrients-17-03651-f001 -> F1
      ...-g001 -> F1 (se capita)
    """
    if not figure_id:
        return ""
    fid = figure_id.strip()

    # già nel formato F<number>
    m = re.fullmatch(r"F(\d+)", fid, flags=re.IGNORECASE)
    if m:
        return f"F{int(m.group(1))}"

    # prende f001 / g001 finali tipici
    m = re.search(r"[-_](?:f|g)(\d{3,})$", fid, flags=re.IGNORECASE)
    if m:
        return f"F{int(m.group(1))}"

    # prova anche "f001" non necessariamente in fondo
    m = re.search(r"(?:^|[-_])(f|g)(\d{3,})(?:$|[-_])", fid, flags=re.IGNORECASE)
    if m:
        return f"F{int(m.group(2))}"

    return fid


def candidate_paper_dirs(images_root: Path, paper_id: str | None):
    if not paper_id:
        return []
    pid = str(paper_id)
    dirs = [images_root / pid]
    if pid.startswith("PMC"):
        dirs.append(images_root / pid[3:])
    else:
        dirs.append(images_root / ("PMC" + pid))
    # rimuovi duplicati mantenendo ordine
    seen = set()
    out = []
    for d in dirs:
        if str(d) not in seen:
            out.append(d)
            seen.add(str(d))
    return out
# Funzione Helper per visualizzare le card
def render_card(title, score, meta, content=None, url=None, image_url=None, html_content=None):
    with st.container():
        # Layout a colonne per titolo e score
        col1, col2 = st.columns([0.85, 0.15])
        with col1:
            st.markdown(f"#### {title}")
        with col2:
            st.markdown(f"`Score: {score:.3f}`")
        
        src_str = meta.get('source', 'UNK').upper()
        color = "blue" if "ARXIV" in src_str else "green"
        st.markdown(f":{color}[**{src_str}**] | 📅 Data: `{meta.get('date', 'N/A')}`")
        
        if content:
            st.markdown(f"**Abstract/Preview:**")
            safe_content = content or ""
            st.write(safe_content[:600] + "..." if len(safe_content) > 600 else safe_content)
        

        # --- MOSTRA CONTESTO E MENTIONS ---
        mentions = meta.get("mentions", [])
        if mentions:
            with st.expander(f"📖 Vedi {len(mentions)} citazioni nel testo (Mentions)"):
                for m in mentions:
                    st.write(f"- {m}")

        ctx_paras = meta.get("context_paragraphs", [])
        if ctx_paras:
            with st.expander("🌐 Paragrafi di contesto (Rilevanza correlata)"):
                for cp in ctx_paras:
                    st.write(f"- {cp}")

        # --- LOGICA TABELLE ---
        if html_content:
            with st.expander("Visualizza Tabella"):
                st.components.v1.html(
                    f"<div style='overflow-x:auto; font-family:sans-serif;'>{html_content}</div>", 
                    height=350, scrolling=True
                )
        # --- LOGICA FIGURE (MIGLIORATA) ---
        elif image_url:
            
            paper_id = meta.get("paper_id", "")
            fig_id = meta.get("figure_id", "")
            src_name = meta.get("src")

            folder_name = normalize_pmc_folder(paper_id)
            img_folder = Path(IMAGES_DIR) / folder_name

            st.write(f"[debug] paper_id={paper_id} -> folder={img_folder}")
            st.write(f"[debug] figure_id={fig_id} src={src_name}")

            local_found = False
            if img_folder.exists():
                candidates = []

                # 1) prova F<number> derivato da figure_id
                short_stem = normalize_fig_stem(fig_id)
                if short_stem and short_stem != fig_id:
                    candidates.append(short_stem)

                # 2) prova figure_id originale
                if fig_id:
                    candidates.append(fig_id)

                # 3) prova src_name (se esiste)
                if src_name:
                    candidates.append(Path(src_name).stem)

                # cerca qualunque estensione
                matches = []
                for stem in candidates:
                    matches.extend(list(img_folder.glob(f"{stem}.*")))

                if matches:
                    local_path = matches[0]
                    st.image(str(local_path), caption=f"Anteprima Locale ({local_path.name})", width=700)
                    local_found = True

            if not local_found:
                st.warning(f"Immagine non trovata localmente in {img_folder}. Provo remoto.")
                clean_url = image_url.replace(".jpg.jpg", ".jpg")
                st.image(clean_url, caption="Anteprima Remota", width=700)
        
        if url:
            st.link_button("📄 Leggi Full Text", url)
        
        st.divider()

# --- LOGICA DI RICERCA ---
if query:
    if st.button("Cerca") or query:
        with st.spinner("Ricerca in corso..."):
            if search_mode == "Cross-Search (RRF)":
                results = cross_search(es, query, size_each=20, size_total=topk, use_query_string=use_query_string, filters=filters)
                st.success(f"Trovati {len(results)} risultati rilevanti combinati.")
                for kind, score, hit in results:
                    s = hit["_source"]
                    if kind == "paper":
                        render_card(f"📄 {s.get('title')}", score, s, s.get("abstract"), s.get("url"))
                    elif kind == "table":
                        render_card(f"📊 Tabella {s.get('table_id')}", score, s, s.get("caption"), s.get("url"), html_content=s.get("table_html") or s.get("body"))
                    elif kind == "figure":
                        render_card(f"🖼️ Figura {s.get('figure_id')}", score, s, s.get("caption"), s.get("url"), image_url=s.get("figure_url"))

            elif search_mode == "Solo Articoli":
                res = search_index(es, INDEX_PAPERS, query, ["title^3", "abstract^2", "full_text"], topk, use_query_string=use_query_string, filters=filters)
                hits = res.get("hits", {}).get("hits", [])
                st.write(f"Trovati {len(hits)} articoli.")
                for h in hits:
                    render_card(h["_source"].get("title"), h["_score"], h["_source"], h["_source"].get("abstract"), h["_source"].get("url"))

            elif search_mode == "Solo Tabelle":
                res = search_index(es, INDEX_TABLES, query, ["caption^3", "body^2", "mentions"], topk, use_query_string=use_query_string, filters=filters)
                hits = res.get("hits", {}).get("hits", [])
                st.write(f"Trovate {len(hits)} tabelle.")
                for h in hits:
                    s = h["_source"]
                    render_card(f"Tabella {s.get('table_id')}", h["_score"], s, s.get("caption"), s.get("url"), html_content=s.get("table_html"))

            elif search_mode == "Solo Figure":
                res = search_index(es, INDEX_FIGURES, query, ["caption^3", "mentions"], topk, use_query_string=use_query_string, filters=filters)
                hits = res.get("hits", {}).get("hits", [])
                st.write(f"Trovate {len(hits)} figure.")
                for h in hits:
                    s = h["_source"]
                    render_card(f"Figura {s.get('figure_id')}", h["_score"], s, s.get("caption"), s.get("url"), image_url=s.get("figure_url"))
else:
    st.info("Inserisci una query per iniziare.")