from __future__ import annotations

from pathlib import Path


def ensure_cache_dir(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    return root
