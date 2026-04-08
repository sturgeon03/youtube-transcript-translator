from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

import srt

from ..normalize.text_cleaner import normalize_text, parse_timestamp_to_seconds, seconds_to_timedelta
from ..transcript.models import TranscriptSegment, from_srt_subtitles


DEFAULT_TEXT_BLOCK_SECONDS = 4.0


def collect_subtitles_from_daglo_xml(path: Path) -> list[TranscriptSegment]:
    root = ET.fromstring(path.read_text(encoding="utf-8-sig"))
    timebase_text = root.findtext("./sequence/rate/timebase") or root.findtext(".//rate/timebase") or "30"
    fps = float(timebase_text)
    subtitles: list[TranscriptSegment] = []

    for item in root.findall(".//generatoritem"):
        start_text = item.findtext("start")
        end_text = item.findtext("end")
        if start_text is None or end_text is None:
            continue

        text_value = ""
        for parameter in item.findall(".//parameter"):
            if (parameter.findtext("parameterid") or "").strip() != "str":
                continue
            value = parameter.find("value")
            if value is not None:
                text_value = "".join(value.itertext())
            break

        clean_text = normalize_text(text_value)
        if not clean_text:
            continue

        start_seconds = float(start_text) / fps
        end_seconds = float(end_text) / fps
        if end_seconds <= start_seconds:
            continue

        subtitles.append(
            TranscriptSegment(
                index=len(subtitles) + 1,
                start=seconds_to_timedelta(start_seconds),
                end=seconds_to_timedelta(end_seconds),
                text=clean_text,
                source="daglo_xml",
            )
        )

    subtitles.sort(key=lambda subtitle: subtitle.start)
    for index, subtitle in enumerate(subtitles, start=1):
        subtitle.index = index
    return subtitles


def collect_subtitles_from_daglo_txt(path: Path) -> list[TranscriptSegment]:
    raw_text = path.read_text(encoding="utf-8-sig")
    blocks = re.split(r"\r?\n\s*\r?\n", raw_text)
    timestamp_pattern = re.compile(r"^(?P<timestamp>\d{1,2}:\d{2}(?::\d{2})?)\b")
    entries: list[tuple[float, str]] = []

    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if len(lines) < 2:
            continue
        match = timestamp_pattern.match(lines[0])
        if not match:
            continue

        text = normalize_text(" ".join(lines[1:]))
        if not text:
            continue
        entries.append((parse_timestamp_to_seconds(match.group("timestamp")), text))

    subtitles: list[TranscriptSegment] = []
    for index, (start_seconds, text) in enumerate(entries, start=1):
        if index < len(entries):
            next_start_seconds = entries[index][0]
            end_seconds = next_start_seconds if next_start_seconds > start_seconds else start_seconds + DEFAULT_TEXT_BLOCK_SECONDS
        else:
            end_seconds = start_seconds + DEFAULT_TEXT_BLOCK_SECONDS

        subtitles.append(
            TranscriptSegment(
                index=index,
                start=seconds_to_timedelta(start_seconds),
                end=seconds_to_timedelta(end_seconds),
                text=text,
                source="daglo_txt",
            )
        )
    return subtitles


def load_subtitles(input_path: Path) -> list[TranscriptSegment]:
    suffix = input_path.suffix.lower()
    if suffix == ".srt":
        subtitles = list(srt.parse(input_path.read_text(encoding="utf-8-sig")))
        return from_srt_subtitles(subtitles, source="srt")
    if suffix == ".xml":
        return collect_subtitles_from_daglo_xml(input_path)
    if suffix == ".txt":
        return collect_subtitles_from_daglo_txt(input_path)
    raise ValueError(f"Unsupported input format: {input_path.suffix}")
