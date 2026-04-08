from __future__ import annotations

import json
import mimetypes
import os
import tempfile
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

from ..app.config import MAX_AUDIO_UPLOAD_BYTES
from ..render.srt_writer import write_srt
from ..render.txt_writer import write_plain_text
from ..sources.youtube import (
    download_audio_for_transcription,
    download_audio_section_for_transcription,
    extract_video_id,
    format_yt_dlp_timestamp,
    probe_video_duration_seconds,
)
from .local_asr import transcribe_audio_with_faster_whisper
from .models import TranscriptSegment
from .youtube_subtitles import resolve_youtube_english_subtitles
from ..normalize.text_cleaner import normalize_text, seconds_to_timedelta


def default_transcribed_english_srt_path(video_id: str, target_dir: Path) -> Path:
    return target_dir / f"{video_id}.en.transcribed.srt"


def default_transcribed_english_txt_path(video_id: str, target_dir: Path) -> Path:
    return target_dir / f"{video_id}.en.transcribed.txt"


def write_english_outputs(
    subtitles: list[TranscriptSegment],
    *,
    srt_path: Path | None,
    text_path: Path | None,
) -> None:
    if srt_path is not None:
        write_srt(srt_path, subtitles)
    if text_path is not None:
        write_plain_text(text_path, subtitles)


def encode_multipart_form_data(
    *,
    fields: list[tuple[str, str]],
    files: list[tuple[str, str, str, bytes]],
) -> tuple[bytes, str]:
    boundary = f"----CodexBoundary{uuid.uuid4().hex}"
    chunks: list[bytes] = []

    for name, value in fields:
        chunks.append(f"--{boundary}\r\n".encode("utf-8"))
        chunks.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode("utf-8"))

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


def parse_transcription_segments(response_data: dict[str, Any]) -> list[TranscriptSegment]:
    segments = response_data.get("segments")
    if not isinstance(segments, list):
        raise ValueError("Transcription response did not include segments.")

    subtitles: list[TranscriptSegment] = []
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
            TranscriptSegment(
                index=index,
                start=seconds_to_timedelta(start_seconds),
                end=seconds_to_timedelta(end_seconds),
                text=text,
                source="openai_transcription",
            )
        )
    if not subtitles:
        raise ValueError("Transcription response did not contain usable subtitle segments.")
    return subtitles


def resolve_openai_api_key(env_name: str) -> str:
    api_key = os.environ.get(env_name, "").strip()
    if not api_key:
        raise ValueError(f"OpenAI API use requires environment variable {env_name} to be set.")
    return api_key


def transcribe_audio_with_openai(
    audio_path: Path,
    *,
    model: str,
    language: str,
    api_key: str,
    timeout_seconds: float,
) -> list[TranscriptSegment]:
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


def offset_segments(
    subtitles: list[TranscriptSegment],
    *,
    offset_seconds: float,
    next_index: int,
) -> list[TranscriptSegment]:
    offset = timedelta(seconds=offset_seconds)
    shifted: list[TranscriptSegment] = []
    for subtitle in subtitles:
        shifted.append(
            TranscriptSegment(
                index=next_index,
                start=subtitle.start + offset,
                end=subtitle.end + offset,
                text=subtitle.text,
                source=subtitle.source,
                metadata=dict(subtitle.metadata),
            )
        )
        next_index += 1
    return shifted


def reindex_segments(subtitles: list[TranscriptSegment]) -> list[TranscriptSegment]:
    return [subtitle.with_index(index) for index, subtitle in enumerate(subtitles, start=1)]


def transcribe_openai_url_range(
    url: str,
    *,
    target_dir: Path,
    start_seconds: float,
    end_seconds: float,
    section_index: int,
    model: str,
    language: str,
    api_key: str,
    timeout_seconds: float,
    min_split_seconds: float = 60.0,
) -> tuple[list[TranscriptSegment], int]:
    chunk_audio_path = download_audio_section_for_transcription(
        url,
        target_dir,
        start_seconds=start_seconds,
        end_seconds=end_seconds,
        section_index=section_index,
    )
    try:
        chunk_subtitles = transcribe_audio_with_openai(
            chunk_audio_path,
            model=model,
            language=language,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
        )
    except ValueError as exc:
        if "25 MB transcription limit" not in str(exc):
            raise
        chunk_length = end_seconds - start_seconds
        if chunk_length <= min_split_seconds:
            raise
        midpoint = start_seconds + chunk_length / 2
        left_subtitles, next_section_index = transcribe_openai_url_range(
            url,
            target_dir=target_dir,
            start_seconds=start_seconds,
            end_seconds=midpoint,
            section_index=section_index + 1,
            model=model,
            language=language,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            min_split_seconds=min_split_seconds,
        )
        right_subtitles, next_section_index = transcribe_openai_url_range(
            url,
            target_dir=target_dir,
            start_seconds=midpoint,
            end_seconds=end_seconds,
            section_index=next_section_index,
            model=model,
            language=language,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            min_split_seconds=min_split_seconds,
        )
        return left_subtitles + right_subtitles, next_section_index

    shifted = offset_segments(
        chunk_subtitles,
        offset_seconds=start_seconds,
        next_index=1,
    )
    print(
        "Transcribed audio chunk "
        f"{section_index}: {format_yt_dlp_timestamp(start_seconds)} - {format_yt_dlp_timestamp(end_seconds)}",
        flush=True,
    )
    return shifted, section_index + 1


def transcribe_url_with_openai_chunked(
    url: str,
    *,
    target_dir: Path,
    model: str,
    language: str,
    api_key: str,
    timeout_seconds: float,
    chunk_seconds: float,
) -> list[TranscriptSegment]:
    if chunk_seconds <= 0:
        raise ValueError("--transcription-chunk-seconds must be greater than 0.")

    duration_seconds = probe_video_duration_seconds(url)
    if duration_seconds is None or duration_seconds <= 0:
        raise RuntimeError(
            "Could not determine the YouTube video duration required for chunked transcription."
        )

    combined: list[TranscriptSegment] = []
    with tempfile.TemporaryDirectory(prefix="yt-transcribe-", dir=target_dir) as temp_dir_raw:
        temp_dir = Path(temp_dir_raw)
        chunk_start = 0.0
        section_index = 1

        while chunk_start < duration_seconds:
            chunk_end = min(duration_seconds, chunk_start + chunk_seconds)
            chunk_subtitles, section_index = transcribe_openai_url_range(
                url,
                target_dir=temp_dir,
                start_seconds=chunk_start,
                end_seconds=chunk_end,
                section_index=section_index,
                model=model,
                language=language,
                api_key=api_key,
                timeout_seconds=timeout_seconds,
            )
            combined.extend(chunk_subtitles)
            chunk_start = chunk_end

    return reindex_segments(combined)


def resolve_transcript_from_url(
    url: str,
    *,
    target_dir: Path,
    transcript_source: str,
    transcription_backend: str,
    transcription_model: str,
    transcription_language: str,
    local_transcription_model: str,
    local_transcription_device: str,
    local_transcription_compute_type: str,
    openai_api_key_env: str,
    transcription_timeout_seconds: float,
    transcription_chunk_seconds: float,
    english_output: Path | None,
    english_text_output: Path | None,
) -> tuple[list[TranscriptSegment], Path]:
    video_id = extract_video_id(url)

    if transcript_source in ("auto", "youtube"):
        resolved = resolve_youtube_english_subtitles(url, target_dir)
        if resolved is not None:
            subtitles, subtitle_path = resolved
            if english_text_output is not None:
                write_english_outputs(
                    subtitles,
                    srt_path=english_output.resolve() if english_output else None,
                    text_path=english_text_output.resolve(),
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
    if transcription_backend == "local":
        subtitles = transcribe_audio_with_faster_whisper(
            audio_path,
            model_size=local_transcription_model,
            language=transcription_language,
            device=local_transcription_device,
            compute_type=local_transcription_compute_type,
        )
    elif transcription_backend == "openai":
        api_key = resolve_openai_api_key(openai_api_key_env)
        try:
            subtitles = transcribe_audio_with_openai(
                audio_path,
                model=transcription_model,
                language=transcription_language,
                api_key=api_key,
                timeout_seconds=transcription_timeout_seconds,
            )
        except ValueError as exc:
            if "25 MB transcription limit" not in str(exc):
                raise
            print(
                "Audio exceeded the OpenAI upload limit. Retrying with chunked transcription.",
                flush=True,
            )
            subtitles = transcribe_url_with_openai_chunked(
                url,
                target_dir=target_dir,
                model=transcription_model,
                language=transcription_language,
                api_key=api_key,
                timeout_seconds=transcription_timeout_seconds,
                chunk_seconds=transcription_chunk_seconds,
            )
    else:
        raise ValueError(f"Unsupported transcription backend: {transcription_backend}")

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
