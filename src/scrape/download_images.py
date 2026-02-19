import io
import json
import time
import tarfile
import sys
import requests
import xml.etree.ElementTree as ET
from pathlib import Path
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Importa configurazioni
from ..config import INTERMEDIATE_DIR, IMAGES_DIR, OA_URL

def make_session() -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=(429, 500, 502, 503, 504),
    )
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.headers.update({"User-Agent": "Homework5 Student Project"})
    return s

def get_tgz_url(session: requests.Session, pmcid: str) -> str | None:
    try:
        r = session.get(OA_URL, params={"id": pmcid}, timeout=30)
        r.raise_for_status()
        root = ET.fromstring(r.text)
        for link in root.iter("link"):
            if link.attrib.get("format") == "tgz" and "href" in link.attrib:
                return link.attrib["href"].replace("ftp://", "https://")
    except Exception as e:
        print(f"[WARN] Errore API OA per {pmcid}: {e}")
    return None

def normalize_name(name):
    """Rimuove percorsi e estensioni per il confronto"""
    return Path(name).stem.lower()

def main():
    session = make_session()
    
    # Prendi solo i JSON PMC
    files = list(INTERMEDIATE_DIR.glob("pmc_*.json"))
    print(f"Trovati {len(files)} articoli PMC. Avvio download immagini...")

    for json_file in files:
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
        except:
            continue

        paper_id = data.get("paper_id")
        figures = data.get("figures", [])
        
        # Filtra figure valide
        valid_figs = [f for f in figures if f.get("src")]
        if not valid_figs:
            continue
            
        paper_img_dir = IMAGES_DIR / paper_id
        
        # Se la cartella esiste già e ha file, saltiamo per velocità
        # if paper_img_dir.exists() and any(paper_img_dir.iterdir()):
        #     continue

        tgz_url = get_tgz_url(session, paper_id)
        if not tgz_url:
            print(f"[SKIP] {paper_id}: pacchetto non disponibile.")
            continue
        
        print(f"[DOWN] Scarico pacchetto per {paper_id}...", end=" ")
        
        try:
            r = session.get(tgz_url, stream=True, timeout=60)
            r.raise_for_status()
            
            with tarfile.open(fileobj=io.BytesIO(r.content), mode="r:gz") as tf:
                paper_img_dir.mkdir(parents=True, exist_ok=True)
                
                # Mappa di tutti i file immagine nel TAR
                # Usiamo solo file grafici
                valid_exts = ['.jpg', '.jpeg', '.png', '.gif', '.tif', '.tiff', '.webp']
                members_map = {
                    m.name: m for m in tf.getmembers() 
                    if m.isfile() and Path(m.name).suffix.lower() in valid_exts
                }
                
                saved_count = 0
                
                for fig in valid_figs:
                    src_raw = fig.get("src")   # es. "bin/image-01.jpg"
                    target_stem = normalize_name(src_raw) # es. "image-01"

                    found_member = None
                    
                    # --- LOGICA DI MATCHING ELASTICA ---
                    
                    # 1. Cerca nei file del tar
                    for tar_fname, member in members_map.items():
                        tar_stem = normalize_name(tar_fname)
                        
                        # Match 1: I nomi (senza estensione) sono identici
                        if target_stem == tar_stem:
                            found_member = member
                            break
                        
                        # Match 2: Il nome nel tar finisce con il nostro target (es. "PMC123_fig1" finisce con "fig1")
                        if tar_stem.endswith(target_stem) or tar_stem.endswith(f"_{target_stem}"):
                            found_member = member
                            break
                            
                        # Match 3: Il target è contenuto nel nome tar (caso disperato)
                        if target_stem in tar_stem:
                            found_member = member
                            break
                    
                    if found_member:
                        f_obj = tf.extractfile(found_member)
                        # Usiamo l'estensione reale del file trovato nel tar
                        ext = Path(found_member.name).suffix
                        # Salviamo col nome standard ID_FIGURA (es. F1.jpg) così Streamlit lo trova facile
                        dest_path = paper_img_dir / f"{fig['figure_id']}{ext}"
                        
                        if f_obj:
                            dest_path.write_bytes(f_obj.read())
                            saved_count += 1
                
                if saved_count > 0:
                    print(f"OK ({saved_count}/{len(valid_figs)} img)")
                else:
                    print(f"FAIL (0 img trovate)")
                    # Debug solo se fallisce
                    # print(f"   Target cercati: {[normalize_name(f['src']) for f in valid_figs]}")
                    # print(f"   File nel TAR: {[normalize_name(k) for k in members_map.keys()]}")

        except Exception as e:
            print(f"\n[ERR] {paper_id}: {e}")
        
        time.sleep(0.5)

if __name__ == "__main__":
    main()