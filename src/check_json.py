import json
from src.config import INTERMEDIATE_DIR

files = list(INTERMEDIATE_DIR.glob("pmc_*.json"))
if not files:
    print("Nessun file JSON trovato.")
else:
    f = files[0]
    data = json.loads(f.read_text(encoding="utf-8"))
    print(f"File analizzato: {f.name}")
    figs = data.get("figures", [])
    print(f"Figure trovate: {len(figs)}")
    
    if figs:
        first_fig = figs[0]
        print("Chiavi nella prima figura:", list(first_fig.keys()))
        if "src" not in first_fig or not first_fig["src"]:
            print("\n[ERRORE CRITICO] Manca il campo 'src'! Ecco perché il download non parte.")
        else:
            print(f"\n[OK] Campo 'src' presente: {first_fig['src']}")