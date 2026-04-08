from __future__ import annotations


def find_missing_glossary_targets(text: str, expected_targets: dict[str, str]) -> list[str]:
    missing = []
    lowered = text.lower()
    for target in expected_targets.values():
        if target.lower() not in lowered:
            missing.append(target)
    return missing
