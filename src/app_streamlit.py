import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)) + "/..")

import streamlit as st
from elasticsearch import Elasticsearch

# IMPORT ASSOLUTI (funzionano con: streamlit run src/app_streamlit.py)
from src.config import ES_HOST, INDEX_PAPERS, INDEX_TABLES, INDEX_FIGURES
from src.search_core import search_index, cross_search

st.set_page_config(page_title="Scientific Research Search", layout="wide")

es = Elasticsearch(ES_HOST)

st.title("Scientific Research Search")

query = st.text_input(
    "Query (supporta AND/OR/NOT, virgolette per frase esatta)",
    value='"entity resolution"'
)
mode = st.radio("Cerca in", ["Articoli", "Tabelle", "Figure", "Cross-index"], horizontal=True)
topk = st.slider("Numero risultati", 5, 50, 20)


def card(title: str, score: float):
    #  stringa multilinea corretta
    st.markdown(
        f"""
### {title}
**score:** {score:.2f}
"""
    )


if st.button("Cerca"):
    if mode == "Articoli":
        res = search_index(
            es,
            INDEX_PAPERS,
            query,
            ["title^2", "authors", "abstract", "full_text"],
            topk
        )
        hits = res.get("hits", {}).get("hits", [])
        st.write(f"Risultati trovati: {len(hits)}")

        for h in hits:
            s = h.get("_source", {})
            score = float(h.get("_score") or 0.0)

            card(s.get("title", "(no title)"), score)
            st.caption(f"{s.get('date','')} | {s.get('source','')} | paper_id={s.get('paper_id')}")

            # se hai un url del paper lo mostri (altrimenti niente)
            if s.get("url"):
                st.link_button("Apri Paper", s["url"])

            st.write((s.get("abstract", "") or "")[:500])
            st.divider()

    elif mode == "Tabelle":
        res = search_index(
            es,
            INDEX_TABLES,
            query,
            ["caption^2", "body", "mentions", "context_paragraphs"],
            topk
        )
        hits = res.get("hits", {}).get("hits", [])
        st.write(f"Risultati trovati: {len(hits)}")

        for h in hits:
            s = h.get("_source", {})
            score = float(h.get("_score") or 0.0)

            card(f"Tabella {s.get('table_id')} (Paper: {s.get('paper_id')})", score)
            st.write(s.get("caption", ""))

            html = s.get("table_html", "")
            if html:
                st.markdown(
                    f"""
<div style="max-height:320px; overflow:auto; border:1px solid #ddd; padding:8px">
{html}
</div>
""",
                    unsafe_allow_html=True
                )
            else:
                st.code((s.get("body", "") or "")[:800])

            if s.get("url"):
                st.link_button("Apri Paper", s["url"])
            st.divider()

    elif mode == "Figure":
        res = search_index(
            es,
            INDEX_FIGURES,
            query,
            ["caption^2", "mentions", "context_paragraphs"],
            topk
        )
        hits = res.get("hits", {}).get("hits", [])
        st.write(f"Risultati trovati: {len(hits)}")

        for h in hits:
            s = h.get("_source", {})
            score = float(h.get("_score") or 0.0)

            card(f"Figura {s.get('figure_id')} (Paper: {s.get('paper_id')})", score)
            st.write(s.get("caption", ""))

            fig_url = s.get("figure_url", "")
            if fig_url:
                try:
                    st.image(fig_url)
                except Exception:
                    st.write("Preview non disponibile. Apri il paper per vedere la figura.")

            if s.get("url"):
                st.link_button("Apri Paper", s["url"])
            st.divider()

    else:
        merged = cross_search(es, query, size_each=max(5, topk // 3))
        st.write(f"Risultati trovati: {min(len(merged), topk)}")

        for kind, ns, h in merged[:topk]:
            s = h.get("_source", {})
            score = float(h.get("_score") or 0.0)

            if kind == "paper":
                card(f"[Articolo] {s.get('title','')}", score)
                st.caption(f"norm={ns:.2f} | {s.get('source','')} | {s.get('date','')}")
                if s.get("url"):
                    st.link_button("Apri Paper", s["url"])

            elif kind == "table":
                card(f"[Tabella] {s.get('table_id')} (paper={s.get('paper_id')})", score)
                st.caption(f"norm={ns:.2f}")
                st.write((s.get("caption","") or "")[:200])

            else:
                card(f"[Figura] {s.get('figure_id')} (paper={s.get('paper_id')})", score)
                st.caption(f"norm={ns:.2f}")
                st.write((s.get("caption","") or "")[:200])

            st.divider()
