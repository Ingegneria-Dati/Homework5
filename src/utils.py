
import csv
import json
import re
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterable, Dict, Any, List, Optional

from .config import LOG_DIR

# --- Text Cleaning ---
WS_RE = re.compile(r"\s+")

def clean_text(s: str) -> str:
    if not s:
        return ""
    s = WS_RE.sub(" ", s)
    return s.strip()

# --- CSV Utils ---
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

# --- Regex Utils ---
def find_mentions(paragraphs: List[str], pattern: str) -> List[str]:
    try:
        rx = re.compile(pattern, flags=re.IGNORECASE)
    except re.error:
        return []
    out = []
    for p in paragraphs:
        if rx.search(p):
            out.append(p)
    return out

# --- Tokenization utils ---
_WORD_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9_\-]{1,}")
_STOPWORDS_EN = {
    "a","an","and","are","as","at","be","by","for","from","has","he","in","is","it","its",
    "of","on","that","the","to","was","were","will","with","we","our","this","these","those",
    "or","not","can","may","might","into","than","then","also","such","using","use","used",
    "et","al","figure","fig","table","tab","section","supplementary","material","materials",
}

def tokenize_informative(text: str, min_len: int = 3) -> List[str]:
    """Simple, deterministic tokenizer used for lexical-overlap context extraction."""
    if not text:
        return []
    toks = []
    for m in _WORD_RE.finditer(text.lower()):
        t = m.group(0)
        if len(t) < min_len:
            continue
        if t in _STOPWORDS_EN:
            continue
        toks.append(t)
    return toks

# --- Date normalization ---
_DATE_CANDIDATES = [
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%Y.%m.%d",
    "%Y-%m",
    "%Y/%m",
    "%Y.%m",
    "%Y",
]

def parse_date_to_iso(s: str | None) -> str | None:
    """Parse various meta date formats into ISO-8601 (YYYY-MM-DD) or YYYY.
    Returns None if parsing fails.
    """
    if not s:
        return None
    s = str(s).strip()
    if not s:
        return None
    # Strip time part if present
    s = s.split("T")[0].split(" ")[0]

    for fmt in _DATE_CANDIDATES:
        try:
            dt = datetime.strptime(s, fmt)
            # If only year provided, keep year
            if fmt == "%Y":
                return dt.strftime("%Y")
            # If year-month, normalize to first day
            if fmt in ("%Y-%m","%Y/%m","%Y.%m"):
                return dt.strftime("%Y-%m-01")
            return dt.strftime("%Y-%m-%d")
        except Exception:
            continue

    # Last chance: find a 4-digit year
    m = re.search(r"\b(19\d{2}|20\d{2})\b", s)
    if m:
        return m.group(1)
    return None

# --- Timing / profiling ---
@contextmanager
def timed(step: str, extra: Dict[str, Any] | None = None):
    """Context manager that appends a JSONL timing entry under data/logs/timings.jsonl."""
    t0 = time.perf_counter()
    ok = True
    err = None
    try:
        yield
    except Exception as e:
        ok = False
        err = repr(e)
        raise
    finally:
        dt = time.perf_counter() - t0
        entry = {
            "ts": time.time(),
            "step": step,
            "seconds": round(dt, 6),
            "ok": ok,
        }
        if extra:
            entry.update(extra)
        if err:
            entry["error"] = err
        
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        # Append to log file safely
        try:
            with (LOG_DIR / "timings.jsonl").open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass
