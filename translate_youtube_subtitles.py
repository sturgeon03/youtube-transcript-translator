import argparse
import html
import json
import mimetypes
import os
import re
import subprocess
import sys
import textwrap
import time
import uuid
import xml.etree.ElementTree as ET
from datetime import timedelta
from pathlib import Path
from typing import Any, Iterable
from urllib import error as urllib_error
from urllib import request as urllib_request
from urllib.parse import parse_qs, urlparse

import srt
from deep_translator import GoogleTranslator


DEFAULT_MAX_GROUP_SECONDS = 10.0
DEFAULT_MAX_GROUP_WORDS = 26
DEFAULT_MAX_GAP_SECONDS = 0.9
DEFAULT_WRAP_WIDTH = 28
DEFAULT_BATCH_SIZE = 40
DEFAULT_TEXT_BLOCK_SECONDS = 4.0
DEFAULT_TRANSLATOR = "google"
DEFAULT_OPENAI_MODEL = "gpt-5.4-mini"
DEFAULT_OPENAI_REASONING_EFFORT = "low"
DEFAULT_OPENAI_TIMEOUT_SECONDS = 120.0
DEFAULT_OPENAI_MAX_BATCH_SIZE = 12
DEFAULT_TRANSCRIPT_SOURCE = "auto"
DEFAULT_TRANSCRIPTION_MODEL = "gpt-4o-transcribe-diarize"
DEFAULT_TRANSCRIPTION_LANGUAGE = "en"
DEFAULT_TRANSCRIPTION_TIMEOUT_SECONDS = 900.0
MAX_AUDIO_UPLOAD_BYTES = 25 * 1024 * 1024


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Download English auto subtitles from a YouTube video or load existing "
            "subtitles/transcripts, regroup them into readable chunks, and translate "
            "them into Korean."
        )
    )
    parser.add_argument("--url", help="YouTube video URL.")
    parser.add_argument(
        "--input",
        "--input-srt",
        dest="input_path",
        type=Path,
        help="Existing subtitle source (.srt, Daglo .xml, or Daglo .txt).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output Korean SRT path. Defaults to <input>.ko.grouped.srt.",
    )
    parser.add_argument(
        "--max-group-seconds",
        type=float,
        default=DEFAULT_MAX_GROUP_SECONDS,
        help=f"Maximum duration for a grouped subtitle block. Default: {DEFAULT_MAX_GROUP_SECONDS}.",
    )
    parser.add_argument(
        "--max-group-words",
        type=int,
        default=DEFAULT_MAX_GROUP_WORDS,
        help=f"Maximum approximate word count for a grouped block. Default: {DEFAULT_MAX_GROUP_WORDS}.",
    )
    parser.add_argument(
        "--max-gap-seconds",
        type=float,
        default=DEFAULT_MAX_GAP_SECONDS,
        help=f"Start a new block when the time gap exceeds this value. Default: {DEFAULT_MAX_GAP_SECONDS}.",
    )
    parser.add_argument(
        "--wrap-width",
        type=int,
        default=DEFAULT_WRAP_WIDTH,
        help=f"Approximate line wrap width for Korean subtitle lines. Default: {DEFAULT_WRAP_WIDTH}.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"Translation batch size. Default: {DEFAULT_BATCH_SIZE}.",
    )
    parser.add_argument(
        "--transcript-source",
        choices=("auto", "youtube", "transcribe"),
        default=DEFAULT_TRANSCRIPT_SOURCE,
        help=(
            "How to obtain English subtitles for a YouTube URL. "
            "'auto' tries YouTube subtitles first, then transcription."
        ),
    )
    parser.add_argument(
        "--transcription-model",
        choices=("gpt-4o-transcribe-diarize", "whisper-1"),
        default=DEFAULT_TRANSCRIPTION_MODEL,
        help=(
            "OpenAI speech-to-text model used when --transcript-source requires "
            f"transcription. Default: {DEFAULT_TRANSCRIPTION_MODEL}."
        ),
    )
    parser.add_argument(
        "--transcription-language",
        default=DEFAULT_TRANSCRIPTION_LANGUAGE,
        help=(
            "Language hint for audio transcription. Default: "
            f"{DEFAULT_TRANSCRIPTION_LANGUAGE}."
        ),
    )
    parser.add_argument(
        "--transcription-timeout-seconds",
        type=float,
        default=DEFAULT_TRANSCRIPTION_TIMEOUT_SECONDS,
        help=(
            "HTTP timeout for OpenAI transcription requests in seconds. "
            f"Default: {DEFAULT_TRANSCRIPTION_TIMEOUT_SECONDS}."
        ),
    )
    parser.add_argument(
        "--english-output",
        type=Path,
        help="Optional path to save the resolved English subtitles as SRT.",
    )
    parser.add_argument(
        "--english-text-output",
        type=Path,
        help="Optional path to save the resolved English transcript as plain text.",
    )
    parser.add_argument(
        "--translator",
        choices=("google", "openai"),
        default=DEFAULT_TRANSLATOR,
        help=f"Translation backend. Default: {DEFAULT_TRANSLATOR}.",
    )
    parser.add_argument(
        "--glossary",
        type=Path,
        help="Optional glossary file (.json or text with source=>target pairs).",
    )
    parser.add_argument(
        "--openai-model",
        default=DEFAULT_OPENAI_MODEL,
        help=f"OpenAI model to use when --translator openai. Default: {DEFAULT_OPENAI_MODEL}.",
    )
    parser.add_argument(
        "--openai-reasoning-effort",
        choices=("none", "low", "medium", "high", "xhigh"),
        default=DEFAULT_OPENAI_REASONING_EFFORT,
        help=(
            "Reasoning effort for OpenAI Responses API when --translator openai. "
            f"Default: {DEFAULT_OPENAI_REASONING_EFFORT}."
        ),
    )
    parser.add_argument(
        "--openai-api-key-env",
        default="OPENAI_API_KEY",
        help="Environment variable name that stores the OpenAI API key.",
    )
    parser.add_argument(
        "--openai-timeout-seconds",
        type=float,
        default=DEFAULT_OPENAI_TIMEOUT_SECONDS,
        help=(
            "HTTP timeout for OpenAI API calls in seconds when --translator openai. "
            f"Default: {DEFAULT_OPENAI_TIMEOUT_SECONDS}."
        ),
    )
    args = parser.parse_args()
    if not args.url and not args.input_path:
        parser.error("Provide either --url or --input.")
    return args


def extract_video_id(url: str) -> str:
    parsed = urlparse(url)
    if parsed.netloc.endswith("youtu.be"):
        return parsed.path.strip("/")
    if parsed.path == "/watch":
        query = parse_qs(parsed.query)
        if "v" in query and query["v"]:
            return query["v"][0]
    live_match = re.search(r"/live/([A-Za-z0-9_-]{11})", parsed.path)
    if live_match:
        return live_match.group(1)
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", url):
        return url
    raise ValueError(f"Could not extract a YouTube video ID from: {url}")


def find_existing_youtube_subtitle_file(video_id: str, target_dir: Path) -> Path | None:
    candidates = sorted(target_dir.glob(f"{video_id}*.en*.srt"))
    if candidates:
        return candidates[0]
    return None


def try_download_english_auto_subtitles(url: str, target_dir: Path) -> Path | None:
    video_id = extract_video_id(url)
    existing_path = find_existing_youtube_subtitle_file(video_id, target_dir)
    if existing_path is not None:
        return existing_path

    command = [
        sys.executable,
        "-m",
        "yt_dlp",
        "--no-playlist",
        "--skip-download",
        "--write-auto-sub",
        "--sub-lang",
        "en",
        "--sub-format",
        "srt",
        "-o",
        "%(id)s.%(ext)s",
        url,
    ]
    result = subprocess.run(command, cwd=target_dir, capture_output=True, text=True)
    output_path = find_existing_youtube_subtitle_file(video_id, target_dir)
    if output_path is not None:
        return output_path
    if result.returncode == 0:
        return None
    return None


def download_english_auto_subtitles(url: str, target_dir: Path) -> Path:
    output_path = try_download_english_auto_subtitles(url, target_dir)
    if output_path is None:
        raise FileNotFoundError(f"Could not download English auto subtitles for: {url}")
    return output_path


def find_downloaded_audio_file(video_id: str, target_dir: Path) -> Path | None:
    candidates = sorted(target_dir.glob(f"{video_id}.audio.*"))
    if candidates:
        return candidates[0]
    return None


def download_audio_for_transcription(url: str, target_dir: Path) -> Path:
    video_id = extract_video_id(url)
    existing_path = find_downloaded_audio_file(video_id, target_dir)
    if existing_path is not None:
        return existing_path

    command = [
        sys.executable,
        "-m",
        "yt_dlp",
        "--no-playlist",
        "-f",
        "ba[ext=m4a]/ba[ext=webm]/bestaudio/best",
        "-S",
        "+abr,+size",
        "-o",
        "%(id)s.audio.%(ext)s",
        url,
    ]
    subprocess.run(command, cwd=target_dir, check=True)
    output_path = find_downloaded_audio_file(video_id, target_dir)
    if output_path is None:
        raise FileNotFoundError(f"Expected audio file was not created for: {url}")
    return output_path


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


def collect_subtitles_from_daglo_xml(path: Path) -> list[srt.Subtitle]:
    root = ET.fromstring(path.read_text(encoding="utf-8-sig"))
    timebase_text = root.findtext("./sequence/rate/timebase") or root.findtext(".//rate/timebase") or "30"
    fps = float(timebase_text)
    subtitles: list[srt.Subtitle] = []

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
            srt.Subtitle(
                index=len(subtitles) + 1,
                start=seconds_to_timedelta(start_seconds),
                end=seconds_to_timedelta(end_seconds),
                content=clean_text,
            )
        )

    subtitles.sort(key=lambda subtitle: subtitle.start)
    for index, subtitle in enumerate(subtitles, start=1):
        subtitle.index = index
    return subtitles


def collect_subtitles_from_daglo_txt(path: Path) -> list[srt.Subtitle]:
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

    subtitles: list[srt.Subtitle] = []
    for index, (start_seconds, text) in enumerate(entries, start=1):
        if index < len(entries):
            next_start_seconds = entries[index][0]
            end_seconds = next_start_seconds if next_start_seconds > start_seconds else start_seconds + DEFAULT_TEXT_BLOCK_SECONDS
        else:
            end_seconds = start_seconds + DEFAULT_TEXT_BLOCK_SECONDS

        subtitles.append(
            srt.Subtitle(
                index=index,
                start=seconds_to_timedelta(start_seconds),
                end=seconds_to_timedelta(end_seconds),
                content=text,
            )
        )
    return subtitles


def load_subtitles(input_path: Path) -> list[srt.Subtitle]:
    suffix = input_path.suffix.lower()
    if suffix == ".srt":
        return list(srt.parse(input_path.read_text(encoding="utf-8-sig")))
    if suffix == ".xml":
        return collect_subtitles_from_daglo_xml(input_path)
    if suffix == ".txt":
        return collect_subtitles_from_daglo_txt(input_path)
    raise ValueError(f"Unsupported input format: {input_path.suffix}")


def subtitles_to_plain_text(subtitles: Iterable[srt.Subtitle]) -> str:
    lines = []
    for subtitle in subtitles:
        text = normalize_text(subtitle.content)
        if text:
            lines.append(text)
    return "\n".join(lines)


def default_transcribed_english_srt_path(video_id: str, target_dir: Path) -> Path:
    return target_dir / f"{video_id}.en.transcribed.srt"


def default_transcribed_english_txt_path(video_id: str, target_dir: Path) -> Path:
    return target_dir / f"{video_id}.en.transcribed.txt"


def write_english_outputs(
    subtitles: list[srt.Subtitle],
    *,
    srt_path: Path | None,
    text_path: Path | None,
) -> None:
    if srt_path is not None:
        srt_path.write_text(srt.compose(subtitles), encoding="utf-8-sig")
    if text_path is not None:
        text_path.write_text(subtitles_to_plain_text(subtitles), encoding="utf-8-sig")


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


def build_openai_translation_instructions(glossary: dict[str, str]) -> str:
    lines = [
        "You translate English lecture subtitles into accurate, concise Korean subtitles.",
        "Return only JSON that matches the requested schema.",
        "Translate every segment independently without dropping or merging meaning.",
        "Preserve equations, symbols, variable names, code identifiers, filenames, and URLs exactly.",
        "Use natural spoken Korean suitable for technical lecture subtitles.",
        "Keep robotics, control, optimization, and math terminology consistent across the batch.",
        "Do not add commentary, speaker labels, or explanations.",
    ]
    if glossary:
        lines.append("Use the following glossary entries exactly when the source term appears:")
        for source, target in sorted(glossary.items()):
            lines.append(f"- {source} => {target}")
    return "\n".join(lines)


def build_openai_translation_schema(expected_count: int) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "translations": {
                "type": "array",
                "minItems": expected_count,
                "maxItems": expected_count,
                "items": {
                    "type": "object",
                    "properties": {
                        "index": {"type": "integer", "minimum": 0},
                        "translation": {"type": "string", "minLength": 1},
                    },
                    "required": ["index", "translation"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["translations"],
        "additionalProperties": False,
    }


def extract_openai_output_text(response_data: dict[str, Any]) -> str:
    direct_text = response_data.get("output_text")
    if isinstance(direct_text, str) and direct_text.strip():
        return direct_text.strip()

    parts: list[str] = []
    for item in response_data.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            content_text = content.get("text")
            if isinstance(content_text, str) and content_text.strip():
                parts.append(content_text.strip())
    return "\n".join(parts).strip()


def openai_responses_create(
    *,
    api_key: str,
    model: str,
    instructions: str,
    input_text: str,
    reasoning_effort: str,
    timeout_seconds: float,
    schema: dict[str, Any],
) -> dict[str, Any]:
    request_body = {
        "model": model,
        "instructions": instructions,
        "input": input_text,
        "reasoning": {"effort": reasoning_effort},
        "text": {
            "format": {
                "type": "json_schema",
                "name": "subtitle_batch_translation",
                "strict": True,
                "schema": schema,
            }
        },
        "store": False,
    }

    request = urllib_request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(request_body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib_request.urlopen(request, timeout=timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib_error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI API request failed with status {exc.code}: {body}") from exc
    except urllib_error.URLError as exc:
        raise RuntimeError(f"OpenAI API request failed: {exc}") from exc


def encode_multipart_form_data(
    *,
    fields: list[tuple[str, str]],
    files: list[tuple[str, str, str, bytes]],
) -> tuple[bytes, str]:
    boundary = f"----CodexBoundary{uuid.uuid4().hex}"
    chunks: list[bytes] = []

    for name, value in fields:
        chunks.append(f"--{boundary}\r\n".encode("utf-8"))
        chunks.append(
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode("utf-8")
        )

    for field_name, filename, content_type, content in files:
        chunks.append(f"--{boundary}\r\n".encode("utf-8"))
        chunks.append(
            (
                f'Content-Disposition: form-data; name="{field_name}"; '
                f'filename="{filename}"\r\n'
            ).encode("utf-8")
        )
        chunks.append(f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"))
        chunks.append(content)
        chunks.append(b"\r\n")

    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(chunks), boundary


def parse_transcription_segments(response_data: dict[str, Any]) -> list[srt.Subtitle]:
    segments = response_data.get("segments")
    if not isinstance(segments, list):
        raise ValueError("Transcription response did not include segments.")

    subtitles: list[srt.Subtitle] = []
    for index, segment in enumerate(segments, start=1):
        if not isinstance(segment, dict):
            continue
        text = normalize_text(str(segment.get("text") or ""))
        start = segment.get("start")
        end = segment.get("end")
        if not text or start is None or end is None:
            continue
        start_seconds = float(start)
        end_seconds = float(end)
        if end_seconds <= start_seconds:
            end_seconds = start_seconds + 0.8
        subtitles.append(
            srt.Subtitle(
                index=index,
                start=seconds_to_timedelta(start_seconds),
                end=seconds_to_timedelta(end_seconds),
                content=text,
            )
        )
    if not subtitles:
        raise ValueError("Transcription response did not contain usable subtitle segments.")
    return subtitles


def transcribe_audio_with_openai(
    audio_path: Path,
    *,
    model: str,
    language: str,
    api_key: str,
    timeout_seconds: float,
) -> list[srt.Subtitle]:
    audio_bytes = audio_path.read_bytes()
    if len(audio_bytes) > MAX_AUDIO_UPLOAD_BYTES:
        raise ValueError(
            f"Audio file is {len(audio_bytes)} bytes, which exceeds the 25 MB transcription limit."
        )

    if model == "gpt-4o-transcribe-diarize":
        fields = [
            ("model", model),
            ("response_format", "diarized_json"),
            ("chunking_strategy", "auto"),
            ("language", language),
        ]
    elif model == "whisper-1":
        fields = [
            ("model", model),
            ("response_format", "verbose_json"),
            ("language", language),
        ]
    else:
        raise ValueError(f"Unsupported transcription model for subtitle timestamps: {model}")

    content_type = mimetypes.guess_type(audio_path.name)[0] or "application/octet-stream"
    body, boundary = encode_multipart_form_data(
        fields=fields,
        files=[("file", audio_path.name, content_type, audio_bytes)],
    )
    request = urllib_request.Request(
        "https://api.openai.com/v1/audio/transcriptions",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )

    try:
        with urllib_request.urlopen(request, timeout=timeout_seconds) as response:
            response_data = json.loads(response.read().decode("utf-8"))
    except urllib_error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI transcription request failed with status {exc.code}: {body_text}") from exc
    except urllib_error.URLError as exc:
        raise RuntimeError(f"OpenAI transcription request failed: {exc}") from exc

    return parse_transcription_segments(response_data)


def resolve_subtitles_from_url(
    url: str,
    *,
    target_dir: Path,
    transcript_source: str,
    transcription_model: str,
    transcription_language: str,
    openai_api_key_env: str,
    transcription_timeout_seconds: float,
    english_output: Path | None,
    english_text_output: Path | None,
) -> tuple[list[srt.Subtitle], Path]:
    video_id = extract_video_id(url)

    if transcript_source in ("auto", "youtube"):
        subtitle_path = try_download_english_auto_subtitles(url, target_dir)
        if subtitle_path is not None:
            subtitles = load_subtitles(subtitle_path)
            effective_text_output = english_text_output
            if effective_text_output is not None:
                write_english_outputs(
                    subtitles,
                    srt_path=english_output,
                    text_path=effective_text_output.resolve(),
                )
            elif english_output is not None:
                write_english_outputs(
                    subtitles,
                    srt_path=english_output.resolve(),
                    text_path=None,
                )
            return subtitles, subtitle_path.resolve()
        if transcript_source == "youtube":
            raise FileNotFoundError(f"No English YouTube subtitles were available for: {url}")

    audio_path = download_audio_for_transcription(url, target_dir)
    api_key = resolve_openai_api_key(openai_api_key_env)
    subtitles = transcribe_audio_with_openai(
        audio_path,
        model=transcription_model,
        language=transcription_language,
        api_key=api_key,
        timeout_seconds=transcription_timeout_seconds,
    )

    english_srt_path = english_output.resolve() if english_output else default_transcribed_english_srt_path(video_id, target_dir)
    english_txt_path = (
        english_text_output.resolve()
        if english_text_output
        else default_transcribed_english_txt_path(video_id, target_dir)
    )
    write_english_outputs(
        subtitles,
        srt_path=english_srt_path,
        text_path=english_txt_path,
    )
    return subtitles, english_srt_path


def translate_batch_openai_once(
    batch: list[srt.Subtitle],
    *,
    glossary: dict[str, str],
    model: str,
    reasoning_effort: str,
    api_key: str,
    timeout_seconds: float,
) -> list[str]:
    indexed_segments = [
        {
            "index": index,
            "text": normalize_text(group.content),
        }
        for index, group in enumerate(batch)
    ]
    schema = build_openai_translation_schema(len(indexed_segments))
    response_data = openai_responses_create(
        api_key=api_key,
        model=model,
        instructions=build_openai_translation_instructions(glossary),
        input_text=json.dumps({"segments": indexed_segments}, ensure_ascii=False),
        reasoning_effort=reasoning_effort,
        timeout_seconds=timeout_seconds,
        schema=schema,
    )

    response_text = extract_openai_output_text(response_data)
    if not response_text:
        raise RuntimeError("OpenAI API returned an empty translation payload.")

    payload = json.loads(response_text)
    translations = payload.get("translations")
    if not isinstance(translations, list):
        raise ValueError("OpenAI translation payload did not contain a translations list.")

    mapped: dict[int, str] = {}
    for entry in translations:
        if not isinstance(entry, dict):
            continue
        index = entry.get("index")
        translation = entry.get("translation")
        if not isinstance(index, int) or not isinstance(translation, str):
            continue
        clean_translation = normalize_text(translation)
        if clean_translation:
            mapped[index] = clean_translation

    ordered = []
    for index in range(len(indexed_segments)):
        if index not in mapped:
            raise ValueError(f"OpenAI translation payload was missing segment index {index}.")
        ordered.append(mapped[index])
    return ordered


def translate_batch_openai(
    batch: list[srt.Subtitle],
    *,
    glossary: dict[str, str],
    model: str,
    reasoning_effort: str,
    api_key: str,
    timeout_seconds: float,
    depth: int = 0,
) -> list[str]:
    try:
        return translate_batch_openai_once(
            batch,
            glossary=glossary,
            model=model,
            reasoning_effort=reasoning_effort,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
        )
    except Exception:
        if len(batch) <= 1 or depth >= 4:
            raise
        midpoint = len(batch) // 2
        left = translate_batch_openai(
            batch[:midpoint],
            glossary=glossary,
            model=model,
            reasoning_effort=reasoning_effort,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            depth=depth + 1,
        )
        right = translate_batch_openai(
            batch[midpoint:],
            glossary=glossary,
            model=model,
            reasoning_effort=reasoning_effort,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            depth=depth + 1,
        )
        return left + right


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


def should_split_group(
    current_text: str,
    current_start: float,
    previous_end: float,
    next_start: float,
    max_group_seconds: float,
    max_group_words: int,
    max_gap_seconds: float,
) -> bool:
    if previous_end and next_start - previous_end > max_gap_seconds:
        return True
    if next_start - current_start > max_group_seconds:
        return True
    if len(words(current_text)) >= max_group_words:
        return True
    return False


def regroup_subtitles(
    subtitles: Iterable[srt.Subtitle],
    max_group_seconds: float,
    max_group_words: int,
    max_gap_seconds: float,
) -> list[srt.Subtitle]:
    grouped: list[srt.Subtitle] = []
    current_index = 1
    current_start = None
    current_end = None
    current_text = ""

    for subtitle in subtitles:
        text = normalize_text(subtitle.content)
        if not text:
            continue
        start_seconds = subtitle.start.total_seconds()
        end_seconds = subtitle.end.total_seconds()
        if current_start is None:
            current_start = subtitle.start
            current_end = subtitle.end
            current_text = text
            continue

        candidate_text = append_with_overlap(current_text, text)
        if subtitle.end <= current_end and candidate_text == current_text:
            continue

        if should_split_group(
            current_text=current_text,
            current_start=current_start.total_seconds(),
            previous_end=current_end.total_seconds(),
            next_start=start_seconds,
            max_group_seconds=max_group_seconds,
            max_group_words=max_group_words,
            max_gap_seconds=max_gap_seconds,
        ):
            grouped.append(
                srt.Subtitle(
                    index=current_index,
                    start=current_start,
                    end=current_end,
                    content=current_text,
                )
            )
            current_index += 1
            current_start = max(subtitle.start, current_end)
            if subtitle.end <= current_start:
                current_start = None
                current_end = None
                current_text = ""
                continue
            current_end = subtitle.end
            current_text = text
            continue

        current_end = max(current_end, subtitle.end)
        current_text = candidate_text

    if current_start is not None:
        grouped.append(
            srt.Subtitle(
                index=current_index,
                start=current_start,
                end=current_end,
                content=current_text,
            )
        )
    return grouped


def wrap_korean_text(text: str, width: int) -> str:
    if len(text) <= width:
        return text
    wrapped = textwrap.fill(text, width=width, break_long_words=False, break_on_hyphens=False)
    return wrapped


def merge_text_segments(parts: list[str], target_count: int = 2) -> list[str]:
    if len(parts) <= target_count:
        return parts

    total_length = sum(len(part) for part in parts)
    target_length = max(total_length / target_count, 1)
    merged: list[str] = []
    current = ""

    for part in parts:
        candidate = f"{current} {part}".strip() if current else part
        if current and len(candidate) > target_length and len(merged) < target_count - 1:
            merged.append(current)
            current = part
            continue
        current = candidate

    if current:
        merged.append(current)
    return merged


def split_text_for_translation(text: str) -> list[str]:
    split_patterns = [
        r"(?<=[.!?])\s+",
        r"(?<=[,;:])\s+",
        r"(?<=\))\s+",
    ]

    for pattern in split_patterns:
        parts = [part.strip() for part in re.split(pattern, text) if part.strip()]
        if len(parts) > 1:
            return merge_text_segments(parts)

    word_parts = words(text)
    if len(word_parts) > 6:
        midpoint = len(word_parts) // 2
        return [
            " ".join(word_parts[:midpoint]).strip(),
            " ".join(word_parts[midpoint:]).strip(),
        ]

    midpoint = len(text) // 2
    split_at = text.rfind(" ", 0, midpoint)
    if split_at == -1:
        split_at = text.find(" ", midpoint)
    if split_at == -1:
        return [text]
    return [text[:split_at].strip(), text[split_at:].strip()]


def translate_text_google(translator: GoogleTranslator, text: str, depth: int = 0) -> str:
    clean_text = normalize_text(text)
    if not clean_text:
        return ""

    try:
        translated = translator.translate(clean_text)
        if translated is None:
            raise ValueError("Translator returned no text.")
        translated = translated.strip()
        if not translated:
            raise ValueError("Translator returned an empty string.")
        return translated
    except Exception:
        if depth >= 4:
            raise

        parts = split_text_for_translation(clean_text)
        if len(parts) <= 1:
            raise

        translated_parts = []
        for part in parts:
            translated_parts.append(translate_text_google(translator, part, depth + 1))
            time.sleep(0.2)
        return " ".join(part.strip() for part in translated_parts if part.strip())


def translate_batch_google(translator: GoogleTranslator, texts: list[str]) -> list[str]:
    try:
        return translator.translate_batch(texts)
    except Exception:
        translated = []
        for text in texts:
            translated.append(translate_text_google(translator, text))
            time.sleep(0.2)
        return translated


def translate_groups_google(groups: list[srt.Subtitle], wrap_width: int, batch_size: int) -> list[srt.Subtitle]:
    translator = GoogleTranslator(source="en", target="ko")
    translated: list[srt.Subtitle] = []
    next_index = 1

    for offset in range(0, len(groups), batch_size):
        batch = groups[offset : offset + batch_size]
        batch_texts = [group.content for group in batch]
        translated_texts = translate_batch_google(translator, batch_texts)
        for group, text in zip(batch, translated_texts):
            clean_text = normalize_text(text)
            clean_text = wrap_korean_text(clean_text, wrap_width)
            translated.append(
                srt.Subtitle(
                    index=next_index,
                    start=group.start,
                    end=group.end,
                    content=clean_text,
                )
            )
            next_index += 1
        print(f"Translated {min(offset + batch_size, len(groups))}/{len(groups)} groups", flush=True)
        time.sleep(0.4)
    return translated


def resolve_openai_api_key(env_name: str) -> str:
    api_key = os.environ.get(env_name, "").strip()
    if not api_key:
        raise ValueError(
            f"OpenAI translator selected, but environment variable {env_name} is not set."
        )
    return api_key


def translate_groups_openai(
    groups: list[srt.Subtitle],
    *,
    wrap_width: int,
    batch_size: int,
    glossary: dict[str, str],
    model: str,
    reasoning_effort: str,
    api_key_env: str,
    timeout_seconds: float,
) -> list[srt.Subtitle]:
    api_key = resolve_openai_api_key(api_key_env)
    translated: list[srt.Subtitle] = []
    next_index = 1
    effective_batch_size = min(batch_size, DEFAULT_OPENAI_MAX_BATCH_SIZE)

    for offset in range(0, len(groups), effective_batch_size):
        batch = groups[offset : offset + effective_batch_size]
        translated_texts = translate_batch_openai(
            batch,
            glossary=glossary,
            model=model,
            reasoning_effort=reasoning_effort,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
        )
        for group, text in zip(batch, translated_texts):
            clean_text = normalize_text(text)
            clean_text = wrap_korean_text(clean_text, wrap_width)
            translated.append(
                srt.Subtitle(
                    index=next_index,
                    start=group.start,
                    end=group.end,
                    content=clean_text,
                )
            )
            next_index += 1
        print(
            f"Translated {min(offset + effective_batch_size, len(groups))}/{len(groups)} groups",
            flush=True,
        )
        time.sleep(0.4)
    return translated


def translate_groups(
    groups: list[srt.Subtitle],
    *,
    wrap_width: int,
    batch_size: int,
    translator_name: str,
    glossary: dict[str, str],
    openai_model: str,
    openai_reasoning_effort: str,
    openai_api_key_env: str,
    openai_timeout_seconds: float,
) -> list[srt.Subtitle]:
    if translator_name == "openai":
        return translate_groups_openai(
            groups,
            wrap_width=wrap_width,
            batch_size=batch_size,
            glossary=glossary,
            model=openai_model,
            reasoning_effort=openai_reasoning_effort,
            api_key_env=openai_api_key_env,
            timeout_seconds=openai_timeout_seconds,
        )
    return translate_groups_google(groups, wrap_width=wrap_width, batch_size=batch_size)


def default_output_path(input_srt: Path) -> Path:
    name = input_srt.name
    if name.endswith(".en.srt"):
        return input_srt.with_name(name.replace(".en.srt", ".ko.grouped.srt"))
    return input_srt.with_suffix(".ko.grouped.srt")


def main() -> None:
    args = parse_args()
    target_dir = Path.cwd()
    glossary = load_glossary(args.glossary)
    input_reference: Path | None = None

    if args.input_path is not None:
        input_reference = args.input_path.resolve()
        subtitles = load_subtitles(input_reference)
        if args.english_text_output is not None:
            write_english_outputs(
                subtitles,
                srt_path=args.english_output.resolve() if args.english_output else None,
                text_path=args.english_text_output.resolve(),
            )
        elif args.english_output is not None:
            write_english_outputs(
                subtitles,
                srt_path=args.english_output.resolve(),
                text_path=None,
            )
    elif args.url:
        subtitles, input_reference = resolve_subtitles_from_url(
            args.url,
            target_dir=target_dir,
            transcript_source=args.transcript_source,
            transcription_model=args.transcription_model,
            transcription_language=args.transcription_language,
            openai_api_key_env=args.openai_api_key_env,
            transcription_timeout_seconds=args.transcription_timeout_seconds,
            english_output=args.english_output,
            english_text_output=args.english_text_output,
        )
    else:
        raise ValueError("No input subtitle source was resolved.")

    output_path = args.output.resolve() if args.output else default_output_path(input_reference)
    grouped = regroup_subtitles(
        subtitles,
        max_group_seconds=args.max_group_seconds,
        max_group_words=args.max_group_words,
        max_gap_seconds=args.max_gap_seconds,
    )
    translated = translate_groups(
        grouped,
        wrap_width=args.wrap_width,
        batch_size=args.batch_size,
        translator_name=args.translator,
        glossary=glossary,
        openai_model=args.openai_model,
        openai_reasoning_effort=args.openai_reasoning_effort,
        openai_api_key_env=args.openai_api_key_env,
        openai_timeout_seconds=args.openai_timeout_seconds,
    )
    output_path.write_text(srt.compose(translated), encoding="utf-8-sig")

    print(f"English input: {input_reference}")
    print(f"Grouped entries: {len(grouped)}")
    print(f"Translator: {args.translator}")
    if args.url:
        print(f"Transcript source: {args.transcript_source}")
        if input_reference.name.endswith(".en.transcribed.srt"):
            print(f"Transcription model: {args.transcription_model}")
    if args.translator == "openai":
        print(f"OpenAI model: {args.openai_model}")
    if glossary:
        print(f"Glossary entries: {len(glossary)}")
    print(f"Korean output: {output_path}")


if __name__ == "__main__":
    main()
