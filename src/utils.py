import csv
import re
from pathlib import Path
from typing import Iterable, Dict, Any, List

WS_RE = re.compile(r"\s+")
def clean_text(s: str) -> str:
    if not s:
        return ""
    s = WS_RE.sub(" ", s)
    return s.strip()

def ensure_csv_header(path: Path, fieldnames: List[str]):
    new_file = not path.exists()
    if new_file:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()

def append_csv(path: Path, row: Dict[str, Any], fieldnames: List[str]):
    ensure_csv_header(path, fieldnames)
    with path.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writerow(row)

def load_processed_ids(path: Path) -> set:
    if not path.exists():
        return set()
    with path.open("r", encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        return { (row.get("id") or "").strip() for row in r if (row.get("id") or "").strip() }

def find_mentions(paragraphs: List[str], pattern: str) -> List[str]:
    rx = re.compile(pattern, flags=re.IGNORECASE)
    out = []
    for p in paragraphs:
        if rx.search(p):
            out.append(p)
    return out
