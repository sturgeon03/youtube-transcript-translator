from __future__ import annotations

import json
from pathlib import Path

from ..normalize.text_cleaner import normalize_text


def load_glossary(path: Path | None) -> dict[str, str]:
    if path is None:
        return {}

    path = path.resolve()
    raw_text = path.read_text(encoding="utf-8-sig")
    glossary: dict[str, str] = {}

    if path.suffix.lower() == ".json":
        data = json.loads(raw_text)
        if isinstance(data, dict):
            items = data.items()
        elif isinstance(data, list):
            items = []
            for entry in data:
                if not isinstance(entry, dict):
                    continue
                source = entry.get("source") or entry.get("term") or entry.get("en")
                target = entry.get("target") or entry.get("translation") or entry.get("ko")
                if source and target:
                    items.append((source, target))
        else:
            raise ValueError(f"Unsupported glossary JSON structure: {path}")

        for source, target in items:
            clean_source = normalize_text(str(source))
            clean_target = normalize_text(str(target))
            if clean_source and clean_target:
                glossary[clean_source] = clean_target
        return glossary

    separators = ("\t", "=>", "->", "=")
    for raw_line in raw_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        source = None
        target = None
        for separator in separators:
            if separator in line:
                source, target = line.split(separator, 1)
                break

        if source is None or target is None:
            continue

        clean_source = normalize_text(source)
        clean_target = normalize_text(target)
        if clean_source and clean_target:
            glossary[clean_source] = clean_target

    return glossary
