from __future__ import annotations

from .text_cleaner import words


def append_with_overlap(existing: str, addition: str) -> str:
    if not existing:
        return addition
    existing_words = words(existing.lower())
    addition_words = words(addition.lower())
    max_overlap = min(len(existing_words), len(addition_words), 8)
    overlap = 0
    for size in range(max_overlap, 0, -1):
        if existing_words[-size:] == addition_words[:size]:
            overlap = size
            break
    if overlap == 0:
        return f"{existing} {addition}".strip()
    remaining = words(addition)[overlap:]
    if not remaining:
        return existing
    return f"{existing} {' '.join(remaining)}".strip()
