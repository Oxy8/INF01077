#!/usr/bin/env python3
"""Validação estrutural do atlas offline. Uso: python -B scripts/verify_atlas_evidencias.py"""

from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "atlas_evidencias"


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.refs = []

    def handle_starttag(self, tag, attrs):
        data = dict(attrs)
        for field in ("href", "src"):
            if field in data:
                self.refs.append(data[field])


def main() -> None:
    manifest = json.loads((OUT / "manifesto_figuras.json").read_text(encoding="utf-8"))
    assert (manifest["original_svg"], manifest["original_png"], manifest["derived_svg"]) == (99, 4, 4)
    assert len(manifest["figures"]) == 107
    paths = [item["path"] for item in manifest["figures"]]
    assert len(paths) == len(set(paths))
    ids = [item["id"] for item in manifest["figures"]]
    assert len(ids) == len(set(ids))
    for entry in manifest["figures"]:
        target = ROOT / entry["path"]
        if not target.is_file(): raise AssertionError(f"Figura ausente: {target}")
        if entry["table"] and not (ROOT / entry["table"]).is_file():
            raise AssertionError(f"Tabela ausente: {entry['table']}")
        if target.suffix == ".svg":
            ET.parse(target)
            if re.search(r'(?<![\w])(?:nan|inf)(?![\w])', target.read_text(encoding="utf-8"), re.I):
                raise AssertionError(f"Número inválido em {target}")
    htmls = sorted(OUT.rglob("*.html"))
    assert len(htmls) == 12, len(htmls)  # índice, catálogo, 5 temas, 5 operações
    count = 0
    for page in htmls:
        parser = Links(); parser.feed(page.read_text(encoding="utf-8"))
        for ref in parser.refs:
            parsed = urlsplit(ref)
            if parsed.scheme or parsed.netloc:
                raise AssertionError(f"Dependência externa em {page}: {ref}")
            if not parsed.path: continue
            target = (page.parent / unquote(parsed.path)).resolve()
            if not target.is_file():
                raise AssertionError(f"Link quebrado em {page}: {ref} -> {target}")
            count += 1
    audit = json.loads((OUT / "auditoria_recalculos.json").read_text(encoding="utf-8"))
    assert 1.2 < audit["ratios"]["Zoom_In_1t_off_over_avx"] < 1.3
    print(f"OK: {len(htmls)} páginas, 99 SVGs e 4 PNGs originais, 4 SVGs novos, {count} links locais, razões recalculadas")


if __name__ == "__main__":
    try: main()
    except Exception as exc:
        print(f"FALHA: {exc}", file=sys.stderr)
        raise
