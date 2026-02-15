"""LLM-as-a-Judge for table/figure context paragraphs.

Goal: estimate how well lexical-overlap thresholding works for selecting
context_paragraphs.

Pipeline:
- Load intermediate_json documents.
- Sample N tables and N figures.
- For each object, build a pool of candidate paragraphs (top M by overlap score).
- Ask the LLM to judge if each paragraph is *relevant context* for the object.

Outputs:
- data/eval/context_qrels_llm.tsv

The metrics / threshold sweep is done by llm_eval_metrics_context.py.
"""

import csv
import json
import os
import random
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

from openai import OpenAI

from src.config import INTERMEDIATE_DIR
from src.utils import tokenize_informative


OUT = Path("data/eval/context_qrels_llm.tsv")
OUT.parent.mkdir(parents=True, exist_ok=True)

MODEL_JUDGE = os.getenv("CONTEXT_JUDGE_MODEL", "llama-3.1-8b-instant")
MAX_CANDIDATES = int(os.getenv("CONTEXT_MAX_CANDIDATES", "20"))
N_TABLES = int(os.getenv("CONTEXT_N_TABLES", "60"))
N_FIGURES = int(os.getenv("CONTEXT_N_FIGURES", "60"))
SEED = int(os.getenv("CONTEXT_SEED", "42"))


def get_client() -> OpenAI:
    api_key = os.getenv("GROQ_API_KEY")
    base_url = "https://api.groq.com/openai/v1"
    return OpenAI(api_key=api_key, base_url=base_url)


def clip(s: str, n: int) -> str:
    s = (s or "").strip()
    s = " ".join(s.split())
    return s[:n]


def overlap_score(terms: set[str], paragraph: str) -> float:
    pt = set(tokenize_informative(paragraph))
    if not terms or not pt:
        return 0.0
    return len(terms & pt) / len(terms)


def judge(client: OpenAI, obj_kind: str, obj_text: str, paragraph: str) -> int:
    prompt = f"""
You are a strict judge.

Object type: {obj_kind}
Object content:
{obj_text}

Candidate paragraph:
{paragraph}

Is the paragraph a *relevant contextual description* for the object?
Label:
0 = Not relevant
1 = Relevant

Return ONLY valid JSON: {{"relevance": 0}} or {{"relevance": 1}}.
""".strip()

    for _ in range(3):
        try:
            resp = client.chat.completions.create(
                model=MODEL_JUDGE,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
            )
            text = resp.choices[0].message.content.strip()
            if "```" in text:
                text = text.replace("```json", "").replace("```", "").strip()
            obj = json.loads(text)
            r = int(obj.get("relevance", 0))
            return 1 if r == 1 else 0
        except Exception:
            time.sleep(1)
    return 0


def iter_objects() -> List[Tuple[str, str, str, List[str]]]:
    """Return list of (kind, obj_id, obj_text, paragraphs) objects."""
    objs = []
    for p in INTERMEDIATE_DIR.glob("*.json"):
        doc = json.loads(p.read_text(encoding="utf-8"))
        paper_doc_id = f"{doc['source']}_{doc['paper_id']}"
        paras = doc.get("paragraphs", [])

        for t in doc.get("tables", []):
            tid = t.get("table_id", "")
            obj_id = f"{paper_doc_id}::{tid}"
            caption = clip(t.get("caption", ""), 300)
            body = clip(t.get("body", ""), 900)
            obj_text = f"CAPTION: {caption}\nBODY: {body}"
            objs.append(("table", obj_id, obj_text, paras))

        for f in doc.get("figures", []):
            fid = f.get("figure_id", "")
            obj_id = f"{paper_doc_id}::{fid}"
            cap = clip(f.get("caption", ""), 500)
            obj_text = f"CAPTION: {cap}"
            objs.append(("figure", obj_id, obj_text, paras))

    return objs


def main():
    random.seed(SEED)
    client = get_client()

    all_objs = iter_objects()
    tables = [o for o in all_objs if o[0] == "table"]
    figs = [o for o in all_objs if o[0] == "figure"]
    random.shuffle(tables)
    random.shuffle(figs)
    sample = tables[:N_TABLES] + figs[:N_FIGURES]

    # Resume support
    done = set()
    if OUT.exists():
        with OUT.open("r", encoding="utf-8") as f:
            rdr = csv.DictReader(f, delimiter="\t")
            for r in rdr:
                done.add((r["obj_id"], r["para_hash"]))

    write_header = not OUT.exists()
    with OUT.open("a", encoding="utf-8", newline="") as out:
        w = csv.writer(out, delimiter="\t")
        if write_header:
            w.writerow(["obj_kind", "obj_id", "para_hash", "overlap", "relevance"])

        for kind, obj_id, obj_text, paras in sample:
            terms = set(tokenize_informative(obj_text))
            scored = [(overlap_score(terms, p), p) for p in paras]
            scored.sort(key=lambda x: x[0], reverse=True)
            for sc, p in scored[:MAX_CANDIDATES]:
                para_hash = str(abs(hash(p)))
                key = (obj_id, para_hash)
                if key in done:
                    continue
                rel = judge(client, kind, obj_text, clip(p, 900))
                w.writerow([kind, obj_id, para_hash, f"{sc:.4f}", str(rel)])
                out.flush()
                time.sleep(0.2)

    print(f"[DONE] context judgments -> {OUT}")


if __name__ == "__main__":
    main()
