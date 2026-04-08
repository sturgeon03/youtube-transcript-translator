"""Register generated Korean subtitles in the Chrome overlay extension.

This helper copies a subtitle file into the extension's `subtitles/` folder and
updates `subtitles/index.json` atomically so the browser overlay can load it.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any


DEFAULT_RELATIVE_SUBTITLE_DIR = Path("subtitles")
DEFAULT_RELATIVE_INDEX_PATH = DEFAULT_RELATIVE_SUBTITLE_DIR / "index.json"


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"videos": {}}
    raw = path.read_text(encoding="utf-8")
    if not raw.strip():
        return {"videos": {}}
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError(f"Index file must contain a JSON object: {path}")
    videos = data.get("videos")
    if not isinstance(videos, dict):
        data["videos"] = {}
    return data


def _write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False, sort_keys=True)
        handle.write("\n")
        temp_path = Path(handle.name)
    os.replace(temp_path, path)


def _normalize_video_id(video_id: str) -> str:
    normalized = video_id.strip()
    if not normalized:
        raise ValueError("video_id must not be empty")
    return normalized


def register_subtitle(
    extension_root: Path,
    video_id: str,
    subtitle_source: Path,
    *,
    label: str | None = None,
) -> Path:
    """Copy a subtitle file into the extension and update the registry."""

    extension_root = extension_root.resolve()
    subtitle_source = subtitle_source.resolve()
    if not subtitle_source.exists():
        raise FileNotFoundError(subtitle_source)

    video_id = _normalize_video_id(video_id)
    subtitle_dir = extension_root / DEFAULT_RELATIVE_SUBTITLE_DIR
    index_path = extension_root / DEFAULT_RELATIVE_INDEX_PATH
    subtitle_dir.mkdir(parents=True, exist_ok=True)

    target_name = f"{video_id}.ko.grouped.srt"
    target_path = subtitle_dir / target_name
    if subtitle_source.resolve() != target_path.resolve():
        shutil.copyfile(subtitle_source, target_path)

    registry = _load_json(index_path)
    videos = registry.setdefault("videos", {})
    entry: dict[str, Any] = dict(videos.get(video_id, {}))
    entry["file"] = f"subtitles/{target_name}"
    if label is not None and label.strip():
        entry["label"] = label.strip()
    videos[video_id] = entry
    _write_json_atomic(index_path, registry)
    return target_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Copy a Korean SRT into the overlay extension and register it."
    )
    parser.add_argument(
        "--extension-root",
        type=Path,
        default=Path(__file__).resolve().parent / "ui" / "chrome_overlay",
        help="Root of the chrome overlay folder. Default: the package's extension folder.",
    )
    parser.add_argument("--video-id", required=True, help="YouTube video id.")
    parser.add_argument(
        "--subtitle",
        type=Path,
        required=True,
        help="Path to the generated Korean subtitle file.",
    )
    parser.add_argument("--label", help="Optional human-readable label for the registry entry.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    target_path = register_subtitle(
        args.extension_root,
        args.video_id,
        args.subtitle,
        label=args.label,
    )
    print(f"Registered: {target_path}")


if __name__ == "__main__":
    main()
