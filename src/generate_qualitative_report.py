import os
from .search_core import es_client, cross_search

# 1. Definiamo i casi studio qualitativi
# Ogni query è scelta per dimostrare una capacità specifica del sistema
STRATEGIC_QUERIES = [
    {
        "label": "Trattamento Tabelle come Oggetti di I Classe",
        "query": "F1-score",
        "reason": "Dimostra che il sistema trova tabelle tramite il body interno."
    },
    {
        "label": "Recupero tramite Contesto (Punto 19)",
        "query": "comparison of dietary patterns",
        "reason": "Verifica se le tabelle vengono trovate grazie ai paragrafi che le citano."
    },
    {
    "label": "Precisione Booleana e Highlighting",
    "query": "\"ultra-processed foods\" AND cardiovascular",
    "reason": "Mostra il funzionamento dei filtri esatti e la trasparenza dei risultati."
    }
]

def generate_report():
    es = es_client()
    report_file = "REPORT_QUALITATIVO.md"
    
    with open(report_file, "w", encoding="utf-8") as f:
        f.write("# 📝 Report di Valutazione Qualitativa\n")
        f.write("Questo documento analizza la pertinenza dei risultati e la capacità del sistema di trattare tabelle e figure.\n\n")

        for item in STRATEGIC_QUERIES:
            f.write(f"## 🔍 Caso: {item['label']}\n")
            f.write(f"**Query inviata:** `{item['query']}`  \n")
            f.write(f"**Obiettivo:** {item['reason']}\n\n")

            # Eseguiamo la ricerca reale
            results = cross_search(es, item['query'], size_total=3)

            if not results:
                f.write("> ⚠️ Nessun risultato trovato per questa configurazione.\n\n")
                continue

            for rank, (kind, score, hit) in enumerate(results, start=1):
                source = hit['_source']
                title = source.get('title') or source.get('caption') or "Senza Titolo"
                
                f.write(f"### {rank}. [{kind.upper()}] {title}\n")
                f.write(f"- **ID:** `{hit['_id']}`\n")
                f.write(f"- **Score RRF:** `{score:.4f}`\n")

                # Estrazione Highlight (Se presenti)
                if 'highlight' in hit:
                    f.write("- **Highlights trovati:**\n")
                    for field, snippets in hit['highlight'].items():
                        for s in snippets:
                            f.write(f"  - *{field}*: ...{s}...\n")
                
                # Estrazione Contesto (Per tabelle/figure)
                if 'context_paragraphs' in source and source['context_paragraphs']:
                    f.write("- **Contesto (Punto 19):**\n")
                    # Mostriamo solo il primo paragrafo di contesto per brevità
                    context = source['context_paragraphs'][0][:200]
                    f.write(f"  - 📖 *\"{context}...\"*\n")
                
                f.write("\n")
            f.write("---\n\n")

    print(f"✅ Report qualitativo generato: {report_file}")

if __name__ == "__main__":
    generate_report()