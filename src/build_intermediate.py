
import json
import re
import time
from urllib.parse import urljoin
import requests
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
from pathlib import Path
from .config import ARXIV_HTML_DIR, PMC_XML_DIR, INTERMEDIATE_DIR
from .utils import clean_text, parse_date_to_iso, timed

# --- NUOVA FUNZIONE: FALLBACK API ARXIV ---

def fetch_arxiv_meta_api(arxiv_id):
    """
    Recupera metadati (autori e data) tramite l'API ufficiale di arXiv.
    """
    # L'API accetta ID come '1008.4627v1'
    url = f"http://export.arxiv.org/api/query?id_list={arxiv_id}"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            root = ET.fromstring(resp.text)
            # Namespace Atom
            ns = {'atom': 'http://www.w3.org/2005/Atom'}
            entry = root.find('atom:entry', ns)
            
            if entry is not None:
                # 1. Estrazione Data (published)
                published = entry.find('atom:published', ns)
                date_str = published.text if published is not None else None
                
                # 2. Estrazione Autori
                authors = []
                for author in entry.findall('atom:author', ns):
                    name = author.find('atom:name', ns)
                    if name is not None:
                        authors.append(clean_text(name.text))
                
                return authors, date_str
    except Exception as e:
        print(f"  [API ERR] Impossibile recuperare meta per {arxiv_id}: {e}")
    
    return [], None

# --- UTILS GENERALI ---

def get_meta(soup, name):
    m = soup.find("meta", attrs={"name": name})
    if not m: # Fallback per Dublin Core
        m = soup.find("meta", attrs={"name": f"dc.{name.split('_')[-1]}"})
    return clean_text(m["content"]) if m and m.get("content") else ""

def clean_xml_text(node):
    if not node: return ""
    return clean_text(node.get_text(" "))

# --- PARSER ARXIV (HTML) AGGIORNATO ---

def parse_arxiv_html(html_path):
    soup = BeautifulSoup(html_path.read_text(encoding="utf-8", errors="ignore"), "lxml")
    paper_id = html_path.stem # Es: 1008.4627v1

    title = get_meta(soup, "citation_title") or get_meta(soup, "dc.title")
    if not title and soup.title:
        title = clean_text(soup.title.get_text()).replace("arXiv.org", "").strip(" -|")
    
    # Tentativo 1: Estrazione da Meta-tag
    authors = [clean_text(m.get("content")) for m in soup.find_all("meta", attrs={"name": "citation_author"})]
    raw_date = get_meta(soup, "citation_date") or get_meta(soup, "dc.date")

    # Tentativo 2: Fallback API se mancano dati critici (Punto 11 Homework)
    if not authors or not raw_date:
        print(f"  [INFO] Dati mancanti in HTML per {paper_id}. Chiamata API in corso...")
        api_authors, api_date = fetch_arxiv_meta_api(paper_id)
        if not authors: authors = api_authors
        if not raw_date: raw_date = api_date
        time.sleep(0.5) # Gentilezza verso l'API

    date = parse_date_to_iso(raw_date)
    
    abstract = get_meta(soup, "citation_abstract")
    if not abstract:
        ab_node = soup.select_one(".ltx_abstract, #abstract")
        abstract = clean_xml_text(ab_node)

    paragraphs = [clean_xml_text(p) for p in soup.find_all("p") if len(clean_xml_text(p)) > 40]

    tables = []
    figures = []
    base_url = f"https://arxiv.org/html/{paper_id}/"

    # Estrazione Tabelle e Figure (Punti 14-17)
    for i, fig in enumerate(soup.find_all("figure")):
        caption_node = fig.find("figcaption")
        caption = clean_xml_text(caption_node)
        tbl_node = fig.find("table")
        
        if tbl_node:
            t_id = f"T{len(tables)+1}"
            tables.append({
                "table_id": t_id,
                "caption": caption,
                "body": clean_xml_text(tbl_node),
                "table_html": str(tbl_node),
            })
        else:
            f_id = f"F{len(figures)+1}"
            img = fig.find("img")
            img_src = ""
            src_filename = ""
            if img:
                src_filename = img.get("src", "")
                img_src = urljoin(base_url, src_filename)
            
            figures.append({
                "figure_id": f_id,
                "caption": caption,
                "figure_url": img_src,
                "src": src_filename
            })

    return {
        "paper_id": paper_id,
        "source": "arxiv",
        "url": f"https://arxiv.org/abs/{paper_id}",
        "title": title,
        "authors": authors,
        "date": date,
        "abstract": abstract,
        "full_text": "\n".join(paragraphs),
        "paragraphs": paragraphs,
        "tables": tables,
        "figures": figures
    }

# --- PARSER PMC (XML) ---

def parse_pmc_xml(xml_path):
    # Usa il parser XML per gestire correttamente i namespace
    soup = BeautifulSoup(xml_path.read_text(encoding="utf-8", errors="ignore"), "xml")
    paper_id = xml_path.stem 

    article_meta = soup.find("article-meta")
    title_node = article_meta.find("article-title") if article_meta else None
    title = clean_xml_text(title_node)

    authors = []
    for contrib in soup.find_all("contrib", attrs={"contrib-type": "author"}):
        name = contrib.find("name")
        if name:
            surname = clean_xml_text(name.find("surname"))
            given = clean_xml_text(name.find("given-names"))
            authors.append(f"{given} {surname}".strip())

    pub_date = soup.find("pub-date", attrs={"pub-type": "epub"}) or soup.find("pub-date")
    date = None
    if pub_date:
        year = clean_xml_text(pub_date.find("year"))
        month = clean_xml_text(pub_date.find("month")) or "01"
        day = clean_xml_text(pub_date.find("day")) or "01"
        if year:
            date = parse_date_to_iso(f"{year}-{month}-{day}")

    abs_node = article_meta.find("abstract") if article_meta else None
    abstract = clean_xml_text(abs_node)

    body = soup.find("body")
    paragraphs = []
    if body:
        for p in body.find_all("p"):
            txt = clean_xml_text(p)
            if len(txt) > 40: 
                paragraphs.append(txt)

    tables = []
    for i, wrap in enumerate(soup.find_all("table-wrap")):
        t_id = wrap.get("id") or f"T{i+1}"
        cap_node = wrap.find("caption")
        caption = clean_xml_text(cap_node)
        tbl_node = wrap.find("table")
        body_text = clean_xml_text(tbl_node) if tbl_node else clean_xml_text(wrap)
        table_html = str(tbl_node) if tbl_node else ""

        tables.append({
            "table_id": t_id,
            "caption": caption,
            "body": body_text,
            "table_html": table_html
        })

    # --- LOGICA FIGURE CORRETTA E ROBUSTA ---
    figures = []
    base_img_url = f"https://pmc.ncbi.nlm.nih.gov/articles/{paper_id}/bin/"
    
    for i, fig in enumerate(soup.find_all("fig")):
        f_id = fig.get("id") or f"F{i+1}"
        caption = clean_xml_text(fig.find("caption"))
        
        fig_url = ""
        src_filename = ""
        
        graphic = fig.find("graphic")
        if graphic:
            # Estrazione sicura dell'attributo href (gestisce i namespace XML)
            href = graphic.get("xlink:href") or graphic.get("href")
            
            # Se BeautifulSoup non becca il namespace, cerchiamo manualmente tra gli attributi
            if not href and graphic.attrs:
                for attr_name, attr_val in graphic.attrs.items():
                    if "href" in attr_name.lower():
                        href = attr_val
                        break
            
            if href:
                src_filename = href
                # Per la visualizzazione web, aggiungiamo .jpg se manca l'estensione
                display_href = href
                if not href.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".tif")):
                    display_href = f"{href}.jpg"
                fig_url = f"{base_img_url}{display_href}"

        figures.append({
            "figure_id": f_id,
            "caption": caption,
            "figure_url": fig_url,
            "src": src_filename # <--- CAMPO RICHIESTO PER IL DOWNLOAD_IMAGES
        })

    return {
        "paper_id": paper_id,
        "source": "pmc",
        "url": f"https://pmc.ncbi.nlm.nih.gov/articles/{paper_id}/",
        "title": title,
        "authors": authors,
        "date": date,
        "abstract": abstract,
        "full_text": "\n".join(paragraphs),
        "paragraphs": paragraphs,
        "tables": tables,
        "figures": figures
    }

# --- MAIN ---

def main():
    INTERMEDIATE_DIR.mkdir(parents=True, exist_ok=True)

    with timed("build_intermediate:arxiv"):
        files = list(ARXIV_HTML_DIR.glob("*.html"))
        print(f"[ARXIV] Analisi di {len(files)} file HTML...")
        for p in files:
            try:
                doc = parse_arxiv_html(p)
                out = INTERMEDIATE_DIR / f"arxiv_{doc['paper_id']}.json"
                out.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
            except Exception as e:
                print(f"Errore parsing ArXiv {p.name}: {e}")
                
    # 2. Processa PMC (XML)
    with timed("build_intermediate:pmc"):
        if PMC_XML_DIR.exists():
            files = list(PMC_XML_DIR.glob("*.xml"))
            print(f"[PMC] Trovati {len(files)} file XML")
            for p in files:
                try:
                    doc = parse_pmc_xml(p)
                    out = INTERMEDIATE_DIR / f"pmc_{doc['paper_id']}.json"
                    out.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
                except Exception as e:
                    print(f"Errore parsing PMC {p.name}: {e}")
        else:
            print(f"[WARN] Cartella XML non trovata: {PMC_XML_DIR}")

    print(f"[DONE] JSON intermedi generati in {INTERMEDIATE_DIR}")

if __name__ == "__main__":
    main()