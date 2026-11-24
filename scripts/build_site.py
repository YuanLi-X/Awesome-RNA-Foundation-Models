"""Build the GitHub Pages site (docs/index.html) from the curated metadata.

The site is a single static page: data/papers.yaml plus the benchmark and survey
lists are serialised to JSON and injected into site/template.html. Run it after
generate_paper_list.py so the README and the site always describe the same data.

    python scripts/build_site.py
"""
from __future__ import annotations

import ast
import datetime as dt
import json
import math
import re
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
PAPERS_FILE = ROOT / "data" / "papers.yaml"
GENERATOR = ROOT / "generate_paper_list.py"
TEMPLATE = ROOT / "site" / "template.html"
OUTPUT = ROOT / "docs" / "index.html"

# Canonical repository (the discovery bot runs there); see generate_paper_list.py.
REPO_URL = "https://github.com/COLA-Laboratory/Awesome-RNA-Foundation-Models"

SCOPES = {
    "core_rna_fm": {
        "label": "Core",
        "long": "Core RNA foundation models",
        "desc": "Reusable RNA or mRNA backbones pre-trained on raw nucleotide sequences for broad transfer or generation.",
    },
    "specialized_rna_fm": {
        "label": "Specialized",
        "long": "Specialized RNA foundation models",
        "desc": "RNA-specific pre-training, scoped to one RNA subtype, species, structural modality or biological question.",
    },
    "adapted_derived": {
        "label": "Adapted",
        "long": "Adapted / derived RNA models",
        "desc": "Adapt or extend existing pre-trained components into a reusable RNA language model.",
    },
    "rna_inclusive_broad": {
        "label": "Broad",
        "long": "Broad RNA-inclusive models",
        "desc": "Not RNA-only, but the pre-training corpus explicitly includes RNA or transcript sequences.",
    },
}

STATUS_OVERRIDES = {"ChaRNABERT": "workshop", "RFamLlama": "workshop", "Helix-mRNA": "workshop"}
PREPRINT_MARKERS = ("arxiv.org", "biorxiv.org", "openreview.net", "doi.org/10.1101", "doi.org/10.64898")


def entry_status(name: str, url: str) -> str | None:
    if name in STATUS_OVERRIDES:
        return STATUS_OVERRIDES[name]
    if "doi.org/10.1101/gr." in url:
        return None
    return "preprint" if any(m in url for m in PREPRINT_MARKERS) else None


def params_in_millions(text) -> float | None:
    """Largest parameter count mentioned, in millions ('650M / 1.6B' -> 1600)."""
    if not text:
        return None
    values = [
        float(num) * (1000 if unit.upper() == "B" else 1)
        for num, unit in re.findall(r"(\d+(?:\.\d+)?)\s*([MB])\b", str(text))
    ]
    return max(values) if values else None


def literal_list(name: str) -> list:
    """Read a module-level list literal from generate_paper_list.py without executing it
    (importing that module rewrites README.md as a side effect)."""
    tree = ast.parse(GENERATOR.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == name for t in node.targets):
            return ast.literal_eval(node.value)
    return []


def resource_records(name: str) -> list[dict]:
    keys = ("name", "title", "url", "date", "github_url", "hf_url", "abstract")
    rows = [dict(zip(keys, item)) for item in literal_list(name)]
    return sorted(rows, key=lambda r: r["date"], reverse=True)


def last_data_change() -> str:
    for args in (["git", "log", "-1", "--format=%cs", "--", str(PAPERS_FILE)], ["git", "log", "-1", "--format=%cs"]):
        try:
            out = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
            if out:
                return out
        except (OSError, subprocess.CalledProcessError):
            pass
    return dt.date.today().isoformat()


def build(template: Path = TEMPLATE, output: Path = OUTPUT) -> None:
    records = yaml.safe_load(PAPERS_FILE.read_text(encoding="utf-8")) or []
    models = []
    for r in records:
        pm = params_in_millions(r.get("params"))
        models.append({
            "name": r["name"],
            "title": r["title"],
            "url": r["paper_url"],
            "date": r["date"],
            "release": r.get("timeline_date") or r["date"],
            "status": entry_status(r["name"], r["paper_url"]),
            "scope": r["scope"],
            "category": r["category"],
            "arch": r["architecture"],
            "arch_detail": r.get("table_architecture") or r["architecture"],
            "token": r["tokenization"],
            "token_detail": r.get("table_tokenization") or r["tokenization"],
            "params": r.get("params") if r.get("params") not in (None, "-") else None,
            "params_m": pm,
            "data": r.get("pretraining_data") if r.get("pretraining_data") not in (None, "-") else None,
            "abstract": " ".join(str(r["abstract"]).split()),
            "github": r.get("github_url"),
            "hf": r.get("hf_url"),
            "hf_port": r.get("hf_official") is False,
            "weights": r.get("weights_url"),
            "note": r.get("availability_note"),
            "evidence": r.get("evidence") or {},
        })

    payload = {
        "models": models,
        "benchmarks": resource_records("benchmarks"),
        "surveys": resource_records("surveys"),
        "scopes": SCOPES,
        "updated": last_data_change(),
        "repo": REPO_URL,
    }
    blob = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = template.read_text(encoding="utf-8").replace("/*__SITE_DATA__*/{}", blob)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")
    (output.parent / ".nojekyll").touch()
    print(f"Wrote {output}: {len(models)} models, "
          f"{len(payload['benchmarks'])} benchmarks, {len(payload['surveys'])} surveys")


if __name__ == "__main__":
    import sys
    if len(sys.argv) == 3:
        build(Path(sys.argv[1]), Path(sys.argv[2]))
    else:
        build()
