from __future__ import annotations

import html
import re
from datetime import timedelta


def normalize_text(text: str) -> str:
    text = html.unescape(text)
    text = text.replace("\n", " ")
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def words(text: str) -> list[str]:
    return [part for part in re.split(r"\s+", text) if part]


def parse_timestamp_to_seconds(raw: str) -> float:
    parts = [int(part) for part in raw.split(":")]
    if len(parts) == 2:
        minutes, seconds = parts
        return minutes * 60 + seconds
    if len(parts) == 3:
        hours, minutes, seconds = parts
        return hours * 3600 + minutes * 60 + seconds
    raise ValueError(f"Unsupported timestamp: {raw}")


def seconds_to_timedelta(seconds: float) -> timedelta:
    return timedelta(seconds=max(seconds, 0.0))
