"""Costruisce JSON intermedi per indicizzazione:
- estrae: title, authors, date, abstract (quando presenti), full_text, paragraphs
- estrae tabelle: table_id, caption, body_text, table_html
- estrae figure: figure_id, caption, figure_url (normalizzato con urljoin), base url del paper

Salva in data/intermediate_json/<source>_<paper_id>.json
"""

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
