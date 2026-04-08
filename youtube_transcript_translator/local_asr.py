"""Local speech-to-text helpers for YouTube lecture processing.

This module is intentionally small and import-safe: it only depends on
``faster-whisper`` at runtime, and raises a clear error if the package is not
installed. It does not shell out to ffmpeg or any other external command.
"""

from __future__ import annotations

from datetime import timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

import srt

try:
    from faster_whisper import WhisperModel
except Exception as exc:  # pragma: no cover - handled explicitly at runtime
    WhisperModel = None  # type: ignore[assignment]
    _FASTER_WHISPER_IMPORT_ERROR = exc
else:
    _FASTER_WHISPER_IMPORT_ERROR = None


def _require_faster_whisper() -> None:
    if WhisperModel is None:
        raise ImportError(
            "faster-whisper is required for local transcription. "
            "Install it with `python -m pip install faster-whisper`."
        ) from _FASTER_WHISPER_IMPORT_ERROR


@lru_cache(maxsize=8)
def _load_model(model_size: str, device: str, compute_type: str) -> Any:
    _require_faster_whisper()
    return WhisperModel(model_size, device=device, compute_type=compute_type)


def _segment_to_subtitle(index: int, start_seconds: float, end_seconds: float, text: str) -> srt.Subtitle:
    start_seconds = max(0.0, start_seconds)
    end_seconds = max(end_seconds, start_seconds + 0.01)
    return srt.Subtitle(
        index=index,
        start=timedelta(seconds=start_seconds),
        end=timedelta(seconds=end_seconds),
        content=text.strip(),
    )


def transcribe_audio_with_faster_whisper(
    audio_path: Path,
    *,
    model_size: str,
    language: str,
    device: str,
    compute_type: str,
    vad_filter: bool = True,
) -> list[srt.Subtitle]:
    """Transcribe an audio file into timestamped SRT cues.

    The caller is responsible for providing a local file path. The function
    loads the Whisper model lazily and returns stable 1-based subtitle indices.
    """

    _require_faster_whisper()

    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file does not exist: {audio_path}")
    if not audio_path.is_file():
        raise IsADirectoryError(f"Expected an audio file, got a directory: {audio_path}")

    model = _load_model(model_size, device, compute_type)
    segments, _info = model.transcribe(
        str(audio_path),
        language=language,
        vad_filter=vad_filter,
    )

    subtitles: list[srt.Subtitle] = []
    for segment in segments:
        text = segment.text.strip()
        if not text:
            continue
        subtitles.append(
            _segment_to_subtitle(
                len(subtitles) + 1,
                float(segment.start),
                float(segment.end),
                text,
            )
        )

    return subtitles
