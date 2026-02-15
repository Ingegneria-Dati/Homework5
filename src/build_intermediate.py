"""Costruisce JSON intermedi per indicizzazione:
- estrae: title, authors, date, abstract (quando presenti), full_text, paragraphs
- estrae tabelle: table_id, caption, body_text, table_html
- estrae figure: figure_id, caption, figure_url (normalizzato con urljoin), base url del paper

Salva in data/intermediate_json/<source>_<paper_id>.json


import json
import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from .config import ARXIV_HTML_DIR, PMC_HTML_DIR, INTERMEDIATE_DIR, RAW_JSON_DIR
from .utils import clean_text

def meta_content(soup, name):
    m = soup.find("meta", attrs={"name": name})
    if m and m.get("content"):
        return clean_text(m["content"])
    return ""

def extract_paragraphs(soup):
    paras = []
    for p in soup.find_all("p"):
        txt = clean_text(p.get_text(" "))
        if len(txt) >= 40:
            paras.append(txt)
    return paras

def extract_tables_and_figures(soup, paper_id: str, source: str):
    tables = []
    figures = []
    # base url per risoluzione figure relative
    if source == "arxiv":
        base = f"https://arxiv.org/html/{paper_id}/"
        paper_url = f"https://arxiv.org/html/{paper_id}"
    else:
        # pagina articolo PMC tipica
        base = f"https://pmc.ncbi.nlm.nih.gov/articles/PMC{paper_id}/"
        paper_url = base

    # arXiv (LaTeXML) spesso usa <figure class="ltx_table"> e <figure class="ltx_figure">
    fig_nodes = soup.find_all("figure")
    table_count = 0
    fig_count = 0

    for node in fig_nodes:
        cls = " ".join(node.get("class", []))
        caption_tag = node.find("figcaption")
        caption = clean_text(caption_tag.get_text(" ")) if caption_tag else ""

        # prova a distinguere tabelle: presenza di <table> con celle
        inner_table = node.find("table")
        has_cells = bool(inner_table and inner_table.find_all(["td","th"]))

        img = node.find("img")
        src = clean_text(img.get("src","")) if img else ""
        figure_url = urljoin(base, src) if src else ""

        if has_cells:
            table_count += 1
            table_id = f"T{table_count}"
            table_html = str(inner_table) if inner_table else str(node)
            body_text = clean_text(inner_table.get_text(" ")) if inner_table else clean_text(node.get_text(" "))
            tables.append({
                "table_id": table_id,
                "caption": caption,
                "body": body_text,
                "table_html": table_html,
            })
        elif src or ("ltx_figure" in cls):
            fig_count += 1
            figure_id = f"F{fig_count}"
            figures.append({
                "figure_id": figure_id,
                "caption": caption,
                "figure_url": figure_url,
            })

    return paper_url, tables, figures

def build_one(html_path, source: str):
    paper_id = html_path.stem
    html = html_path.read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(html, "lxml")

    title = meta_content(soup, "citation_title") or meta_content(soup, "dc.title")
    if not title and soup.title:
        title = clean_text(soup.title.get_text())
        title = title.replace("arXiv.org", "").strip(" -|")

    authors = [clean_text(m.get("content","")) for m in soup.find_all("meta", attrs={"name":"citation_author"}) if m.get("content")]
    if not authors:
        authors = [clean_text(m.get("content","")) for m in soup.find_all("meta", attrs={"name":"dc.creator"}) if m.get("content")]

    date = meta_content(soup, "citation_publication_date") or meta_content(soup, "citation_date") or meta_content(soup, "dc.date")
    abstract = meta_content(soup, "citation_abstract") or meta_content(soup, "dc.description")
    if not abstract:
        cand = soup.select_one(".ltx_abstract, section#abstract, div#abstract")
        if cand:
            abstract = clean_text(cand.get_text(" "))

    paragraphs = extract_paragraphs(soup)
    full_text = "\n".join(paragraphs)

    paper_url, tables, figures = extract_tables_and_figures(soup, paper_id, source)

    doc = {
        "paper_id": paper_id,
        "source": source,
        "url": paper_url,
        "title": title,
        "authors": authors,
        "date": date,
        "abstract": abstract,
        "paragraphs": paragraphs,
        "full_text": full_text,
        "tables": tables,
        "figures": figures,
    }

    out = INTERMEDIATE_DIR / f"{source}_{paper_id}.json"
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

def main():
    for p in ARXIV_HTML_DIR.glob("*.html"):
        build_one(p, "arxiv")
    for p in PMC_HTML_DIR.glob("*.html"):
        build_one(p, "pmc")
    print(f"[OK] intermedi creati in {INTERMEDIATE_DIR}")

if __name__ == "__main__":
    main()
"""




















"""Costruisce JSON intermedi per indicizzazione:
- estrae: title, authors, date, abstract (quando presenti), full_text, paragraphs
- estrae tabelle: table_id, caption, body_text, table_html
- estrae figure: figure_id, caption, figure_url (normalizzato con urljoin), base url del paper

Salva in data/intermediate_json/<source>_<paper_id>.json


import json
import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from .config import ARXIV_HTML_DIR, PMC_HTML_DIR, INTERMEDIATE_DIR, RAW_JSON_DIR
from .utils import clean_text, parse_date_to_iso, timed

def meta_content(soup, name):
    m = soup.find("meta", attrs={"name": name})
    if m and m.get("content"):
        return clean_text(m["content"])
    return ""

def extract_paragraphs(soup):
    paras = []
    for p in soup.find_all("p"):
        txt = clean_text(p.get_text(" "))
        if len(txt) >= 40:
            paras.append(txt)
    return paras

def extract_tables_and_figures(soup, paper_id: str, source: str):
    tables = []
    figures = []
    # base url per risoluzione figure relative
    if source == "arxiv":
        base = f"https://arxiv.org/html/{paper_id}/"
        paper_url = f"https://arxiv.org/html/{paper_id}"
    else:
        # pagina articolo PMC tipica
        base = f"https://pmc.ncbi.nlm.nih.gov/articles/PMC{paper_id}/"
        paper_url = base

    # arXiv (LaTeXML) spesso usa <figure class="ltx_table"> e <figure class="ltx_figure">
    fig_nodes = soup.find_all("figure")
    table_count = 0
    fig_count = 0

    for node in fig_nodes:
        cls = " ".join(node.get("class", []))
        caption_tag = node.find("figcaption")
        caption = clean_text(caption_tag.get_text(" ")) if caption_tag else ""

        # prova a distinguere tabelle: presenza di <table> con celle
        inner_table = node.find("table")
        has_cells = bool(inner_table and inner_table.find_all(["td","th"]))

        img = node.find("img")
        src = clean_text(img.get("src","")) if img else ""
        figure_url = urljoin(base, src) if src else ""

        if has_cells:
            table_count += 1
            table_id = f"T{table_count}"
            table_html = str(inner_table) if inner_table else str(node)
            body_text = clean_text(inner_table.get_text(" ")) if inner_table else clean_text(node.get_text(" "))
            tables.append({
                "table_id": table_id,
                "caption": caption,
                "body": body_text,
                "table_html": table_html,
            })
        elif src or ("ltx_figure" in cls):
            fig_count += 1
            figure_id = f"F{fig_count}"
            figures.append({
                "figure_id": figure_id,
                "caption": caption,
                "figure_url": figure_url,
            })

    return paper_url, tables, figures

def build_one(html_path, source: str):
    paper_id = html_path.stem
    html = html_path.read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(html, "lxml")

    title = meta_content(soup, "citation_title") or meta_content(soup, "dc.title")
    if not title and soup.title:
        title = clean_text(soup.title.get_text())
        title = title.replace("arXiv.org", "").strip(" -|")

    authors = [clean_text(m.get("content","")) for m in soup.find_all("meta", attrs={"name":"citation_author"}) if m.get("content")]
    if not authors:
        authors = [clean_text(m.get("content","")) for m in soup.find_all("meta", attrs={"name":"dc.creator"}) if m.get("content")]

    raw_date = meta_content(soup, "citation_publication_date") or meta_content(soup, "citation_date") or meta_content(soup, "dc.date")
    date = parse_date_to_iso(raw_date)
    abstract = meta_content(soup, "citation_abstract") or meta_content(soup, "dc.description")
    if not abstract:
        cand = soup.select_one(".ltx_abstract, section#abstract, div#abstract")
        if cand:
            abstract = clean_text(cand.get_text(" "))

    paragraphs = extract_paragraphs(soup)
    full_text = "\n".join(paragraphs)

    paper_url, tables, figures = extract_tables_and_figures(soup, paper_id, source)

    doc = {
        "paper_id": paper_id,
        "source": source,
        "url": paper_url,
        "title": title,
        "authors": authors,
        "date": date,
        "abstract": abstract,
        "paragraphs": paragraphs,
        "full_text": full_text,
        "tables": tables,
        "figures": figures,
    }

    out = INTERMEDIATE_DIR / f"{source}_{paper_id}.json"
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

def main():
    with timed("build_intermediate:arxiv", {"source": "arxiv"}):
        for p in ARXIV_HTML_DIR.glob("*.html"):
            build_one(p, "arxiv")
    with timed("build_intermediate:pmc", {"source": "pmc"}):
        for p in PMC_HTML_DIR.glob("*.html"):
            build_one(p, "pmc")
    print(f"[OK] intermedi creati in {INTERMEDIATE_DIR}")

if __name__ == "__main__":
    main()
"""



"""
Costruisce JSON intermedi standardizzati per l'indicizzazione.
- ArXiv: legge HTML -> estrae testo, tabelle, figure.
- PMC: legge XML (JATS) -> estrae testo, tabelle, figure.

Output: data/intermediate_json/<source>_<paper_id>.json
"""



import json
import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from pathlib import Path
from .config import ARXIV_HTML_DIR, PMC_XML_DIR, INTERMEDIATE_DIR
from .utils import clean_text, parse_date_to_iso, timed

# --- UTILS GENERALI ---

def get_meta(soup, name):
    """Estrae content dai meta tag HTML."""
    m = soup.find("meta", attrs={"name": name})
    return clean_text(m["content"]) if m and m.get("content") else ""

def clean_xml_text(node):
    """Pulisce il testo da un nodo XML/HTML."""
    if not node: return ""
    return clean_text(node.get_text(" "))

# --- PARSER ARXIV (HTML) ---

def parse_arxiv_html(html_path):
    soup = BeautifulSoup(html_path.read_text(encoding="utf-8", errors="ignore"), "lxml")
    paper_id = html_path.stem

    title = get_meta(soup, "citation_title") or get_meta(soup, "dc.title")
    if not title and soup.title:
        title = clean_text(soup.title.get_text()).replace("arXiv.org", "").strip(" -|")
    
    authors = [clean_text(m.get("content")) for m in soup.find_all("meta", attrs={"name": "citation_author"})]
    date = parse_date_to_iso(get_meta(soup, "citation_date") or get_meta(soup, "dc.date"))
    
    abstract = get_meta(soup, "citation_abstract")
    if not abstract:
        ab_node = soup.select_one(".ltx_abstract, #abstract")
        abstract = clean_xml_text(ab_node)

    paragraphs = [clean_xml_text(p) for p in soup.find_all("p") if len(clean_xml_text(p)) > 40]

    tables = []
    figures = []
    base_url = f"https://arxiv.org/html/{paper_id}/"

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
                "src": src_filename # Fondamentale per coerenza
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

    # 1. Processa ArXiv (HTML)
    with timed("build_intermediate:arxiv"):
        files = list(ARXIV_HTML_DIR.glob("*.html"))
        print(f"[ARXIV] Trovati {len(files)} file HTML")
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