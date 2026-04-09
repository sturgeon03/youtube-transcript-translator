from __future__ import annotations

from pathlib import Path

from ..render.srt_writer import write_srt
from ..render.txt_writer import write_plain_text
from ..sources.youtube import download_audio_for_transcription, extract_video_id
from .local_asr import transcribe_audio_with_faster_whisper
from .models import TranscriptSegment
from .youtube_subtitles import resolve_youtube_english_subtitles


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


def transcribe_audio_locally(
    audio_path: Path,
    *,
    language: str,
    local_transcription_model: str,
    local_transcription_device: str,
    local_transcription_compute_type: str,
) -> list[TranscriptSegment]:
    return transcribe_audio_with_faster_whisper(
        audio_path,
        model_size=local_transcription_model,
        language=language,
        device=local_transcription_device,
        compute_type=local_transcription_compute_type,
    )


def resolve_transcript_from_url(
    url: str,
    *,
    target_dir: Path,
    transcript_source: str,
    transcription_language: str,
    local_transcription_model: str,
    local_transcription_device: str,
    local_transcription_compute_type: str,
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
    subtitles = transcribe_audio_locally(
        audio_path,
        language=transcription_language,
        local_transcription_model=local_transcription_model,
        local_transcription_device=local_transcription_device,
        local_transcription_compute_type=local_transcription_compute_type,
    )

    english_srt_path = (
        english_output.resolve()
        if english_output
        else default_transcribed_english_srt_path(video_id, target_dir)
    )
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
