"""Local speech-to-text helpers for YouTube lecture processing."""

from __future__ import annotations

import threading
import time
from datetime import timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

from ..transcript.models import TranscriptSegment
from ..translation.base import ProgressCallback, report_progress

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
    progress_callback: ProgressCallback | None = None,
) -> list[TranscriptSegment]:
    _require_faster_whisper()

    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file does not exist: {audio_path}")
    if not audio_path.is_file():
        raise IsADirectoryError(f"Expected an audio file, got a directory: {audio_path}")

    report_progress(
        progress_callback,
        stage="loading_asr_model",
        progress=45.0,
        detail=f"Loading local ASR model {model_size}",
    )
    print(
        f"[asr] Loading local ASR model {model_size} on {device} "
        f"(first run may take a few minutes while faster-whisper downloads the model)",
        flush=True,
    )

    stop_heartbeat = threading.Event()
    load_started_at = time.monotonic()

    def emit_loading_heartbeat() -> None:
        while not stop_heartbeat.wait(5.0):
            elapsed = int(time.monotonic() - load_started_at)
            # Keep the loading stage visibly alive without claiming completion.
            heartbeat_progress = min(57.0, 45.0 + min(12.0, elapsed / 5.0))
            report_progress(
                progress_callback,
                stage="loading_asr_model",
                progress=heartbeat_progress,
                detail=f"Loading local ASR model {model_size} ({elapsed}s elapsed)",
            )
            print(
                f"[asr] Still loading local ASR model {model_size} ({elapsed}s elapsed)",
                flush=True,
            )

    heartbeat_thread = threading.Thread(
        target=emit_loading_heartbeat,
        daemon=True,
        name=f"asr-load-{model_size}",
    )
    heartbeat_thread.start()
    try:
        model = _load_model(model_size, device, compute_type)
    finally:
        stop_heartbeat.set()
    report_progress(
        progress_callback,
        stage="loading_asr_model",
        progress=58.0,
        detail=f"Local ASR model ready on {device}",
    )
    elapsed = int(time.monotonic() - load_started_at)
    print(
        f"[asr] Local ASR model {model_size} ready on {device} after {elapsed}s",
        flush=True,
    )
    segments, _info = model.transcribe(
        str(audio_path),
        language=language,
        vad_filter=vad_filter,
    )
    total_duration = float(getattr(_info, "duration", 0.0) or 0.0)
    report_progress(
        progress_callback,
        stage="transcribing_audio",
        progress=60.0,
        detail="Transcribing audio with faster-whisper",
    )

    subtitles: list[TranscriptSegment] = []
    for segment in segments:
        text = segment.text.strip()
        if not text:
            continue
        if total_duration > 0:
            segment_end = max(0.0, float(segment.end))
            mapped_progress = 60.0 + min(40.0, (segment_end / total_duration) * 40.0)
            report_progress(
                progress_callback,
                stage="transcribing_audio",
                progress=mapped_progress,
                detail=f"Transcribed audio up to {segment_end:.1f}s / {total_duration:.1f}s",
            )
        subtitles.append(
            TranscriptSegment(
                index=len(subtitles) + 1,
                start=timedelta(seconds=max(0.0, float(segment.start))),
                end=timedelta(seconds=max(float(segment.end), float(segment.start) + 0.01)),
                text=text,
                source="local_asr",
            )
        )

    report_progress(
        progress_callback,
        stage="transcribing_audio",
        progress=100.0,
        detail=f"Finished local transcription with {len(subtitles)} subtitle segments",
    )
    return subtitles
