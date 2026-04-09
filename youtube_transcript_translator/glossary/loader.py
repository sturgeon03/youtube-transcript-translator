from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..normalize.text_cleaner import normalize_text


DEFAULT_GLOSSARIES_DIR = Path(__file__).resolve().parents[2] / "glossaries"
DEFAULT_GLOSSARY_REGISTRY_PATH = DEFAULT_GLOSSARIES_DIR / "registry.json"


@dataclass(frozen=True)
class GlossaryProfile:
    name: str
    path: Path
    label: str
    description: str = ""
    source_urls: tuple[str, ...] = ()


def _normalize_glossary_items(items: list[tuple[Any, Any]]) -> dict[str, str]:
    glossary: dict[str, str] = {}
    for source, target in items:
        clean_source = normalize_text(str(source))
        clean_target = normalize_text(str(target))
        if clean_source and clean_target:
            glossary[clean_source] = clean_target
    return glossary


def load_glossary_file(path: Path) -> dict[str, str]:
    path = path.resolve()
    raw_text = path.read_text(encoding="utf-8-sig")

    if path.suffix.lower() == ".json":
        data = json.loads(raw_text)
        if isinstance(data, dict):
            items = list(data.items())
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
        return _normalize_glossary_items(items)

    items: list[tuple[str, str]] = []
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
        items.append((source, target))

    return _normalize_glossary_items(items)


def resolve_glossary_registry_path(registry_path: Path | None = None) -> Path:
    return (registry_path or DEFAULT_GLOSSARY_REGISTRY_PATH).resolve()


def _coerce_source_urls(raw_source_urls: Any) -> tuple[str, ...]:
    if isinstance(raw_source_urls, list):
        return tuple(str(item).strip() for item in raw_source_urls if str(item).strip())
    return ()


def load_glossary_registry(registry_path: Path | None = None) -> dict[str, GlossaryProfile]:
    registry_file = resolve_glossary_registry_path(registry_path)
    if not registry_file.exists():
        return {}

    data = json.loads(registry_file.read_text(encoding="utf-8"))
    profiles_data = data.get("profiles", {}) if isinstance(data, dict) else {}
    if not isinstance(profiles_data, dict):
        raise ValueError(f"Glossary registry must contain a 'profiles' object: {registry_file}")

    profiles: dict[str, GlossaryProfile] = {}
    for name, raw_entry in profiles_data.items():
        if not isinstance(raw_entry, dict):
            continue
        file_value = raw_entry.get("file")
        if not isinstance(file_value, str) or not file_value.strip():
            continue
        label = str(raw_entry.get("label") or name).strip()
        description = str(raw_entry.get("description") or "").strip()
        source_urls = _coerce_source_urls(raw_entry.get("source_urls"))
        profiles[name] = GlossaryProfile(
            name=name,
            path=(registry_file.parent / file_value).resolve(),
            label=label,
            description=description,
            source_urls=source_urls,
        )
    return profiles


def list_glossary_profiles(registry_path: Path | None = None) -> list[GlossaryProfile]:
    return sorted(load_glossary_registry(registry_path).values(), key=lambda profile: profile.name)


def resolve_glossary_path(
    glossary_path: Path | None = None,
    *,
    glossary_profile: str | None = None,
    registry_path: Path | None = None,
) -> Path | None:
    if glossary_path is not None and glossary_profile:
        raise ValueError("Use either a direct glossary path or a glossary profile, not both.")
    if glossary_path is not None:
        return glossary_path.resolve()
    if not glossary_profile:
        return None

    profiles = load_glossary_registry(registry_path)
    try:
        return profiles[glossary_profile].path
    except KeyError as exc:
        available = ", ".join(sorted(profiles)) or "(none)"
        raise KeyError(
            f"Unknown glossary profile '{glossary_profile}'. Available profiles: {available}"
        ) from exc


def load_glossary(
    glossary_path: Path | None = None,
    *,
    glossary_profile: str | None = None,
    registry_path: Path | None = None,
) -> dict[str, str]:
    resolved_path = resolve_glossary_path(
        glossary_path,
        glossary_profile=glossary_profile,
        registry_path=registry_path,
    )
    if resolved_path is None:
        return {}
    return load_glossary_file(resolved_path)
