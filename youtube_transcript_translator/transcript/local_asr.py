"""Local speech-to-text helpers for YouTube lecture processing."""

from __future__ import annotations

from datetime import timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

from ..transcript.models import TranscriptSegment

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


def transcribe_audio_with_faster_whisper(
    audio_path: Path,
    *,
    model_size: str,
    language: str,
    device: str,
    compute_type: str,
    vad_filter: bool = True,
) -> list[TranscriptSegment]:
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

    subtitles: list[TranscriptSegment] = []
    for segment in segments:
        text = segment.text.strip()
        if not text:
            continue
        subtitles.append(
            TranscriptSegment(
                index=len(subtitles) + 1,
                start=timedelta(seconds=max(0.0, float(segment.start))),
                end=timedelta(seconds=max(float(segment.end), float(segment.start) + 0.01)),
                text=text,
                source="local_asr",
            )
        )

    return subtitles
