from __future__ import annotations

import argparse
from pathlib import Path

from .config import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_LOCAL_TRANSCRIPTION_COMPUTE_TYPE,
    DEFAULT_LOCAL_TRANSCRIPTION_DEVICE,
    DEFAULT_LOCAL_TRANSCRIPTION_MODEL,
    DEFAULT_MAX_GAP_SECONDS,
    DEFAULT_MAX_GROUP_SECONDS,
    DEFAULT_MAX_GROUP_WORDS,
    DEFAULT_OPENAI_MODEL,
    DEFAULT_OPENAI_REASONING_EFFORT,
    DEFAULT_OPENAI_TIMEOUT_SECONDS,
    DEFAULT_TRANSCRIPT_SOURCE,
    DEFAULT_TRANSCRIPTION_BACKEND,
    DEFAULT_TRANSCRIPTION_CHUNK_SECONDS,
    DEFAULT_TRANSCRIPTION_LANGUAGE,
    DEFAULT_TRANSCRIPTION_MODEL,
    DEFAULT_TRANSCRIPTION_TIMEOUT_SECONDS,
    DEFAULT_TRANSLATOR,
    DEFAULT_WRAP_WIDTH,
    OutputConfig,
    PipelineConfig,
    TranscriptConfig,
    TranslationConfig,
)
from .pipeline import run_pipeline


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
    parser.add_argument("--output", type=Path, help="Output Korean SRT path.")
    parser.add_argument("--review-output", type=Path, help="Optional bilingual EN/KR review markdown path.")
    parser.add_argument("--json-output", type=Path, help="Optional machine-readable JSON artifact path.")
    parser.add_argument("--max-group-seconds", type=float, default=DEFAULT_MAX_GROUP_SECONDS)
    parser.add_argument("--max-group-words", type=int, default=DEFAULT_MAX_GROUP_WORDS)
    parser.add_argument("--max-gap-seconds", type=float, default=DEFAULT_MAX_GAP_SECONDS)
    parser.add_argument("--wrap-width", type=int, default=DEFAULT_WRAP_WIDTH)
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument(
        "--transcript-source",
        choices=("auto", "youtube", "transcribe"),
        default=DEFAULT_TRANSCRIPT_SOURCE,
    )
    parser.add_argument(
        "--transcription-backend",
        choices=("local", "openai"),
        default=DEFAULT_TRANSCRIPTION_BACKEND,
    )
    parser.add_argument(
        "--transcription-model",
        choices=("gpt-4o-transcribe-diarize", "whisper-1"),
        default=DEFAULT_TRANSCRIPTION_MODEL,
    )
    parser.add_argument("--transcription-language", default=DEFAULT_TRANSCRIPTION_LANGUAGE)
    parser.add_argument("--local-transcription-model", default=DEFAULT_LOCAL_TRANSCRIPTION_MODEL)
    parser.add_argument("--local-transcription-device", default=DEFAULT_LOCAL_TRANSCRIPTION_DEVICE)
    parser.add_argument("--local-transcription-compute-type", default=DEFAULT_LOCAL_TRANSCRIPTION_COMPUTE_TYPE)
    parser.add_argument("--transcription-timeout-seconds", type=float, default=DEFAULT_TRANSCRIPTION_TIMEOUT_SECONDS)
    parser.add_argument("--transcription-chunk-seconds", type=float, default=DEFAULT_TRANSCRIPTION_CHUNK_SECONDS)
    parser.add_argument("--english-output", type=Path)
    parser.add_argument("--english-text-output", type=Path)
    parser.add_argument("--translator", choices=("google", "openai"), default=DEFAULT_TRANSLATOR)
    parser.add_argument("--glossary", type=Path)
    parser.add_argument("--openai-model", default=DEFAULT_OPENAI_MODEL)
    parser.add_argument(
        "--openai-reasoning-effort",
        choices=("none", "low", "medium", "high", "xhigh"),
        default=DEFAULT_OPENAI_REASONING_EFFORT,
    )
    parser.add_argument("--openai-api-key-env", default="OPENAI_API_KEY")
    parser.add_argument("--openai-timeout-seconds", type=float, default=DEFAULT_OPENAI_TIMEOUT_SECONDS)
    parser.add_argument("--extension-root", type=Path)
    parser.add_argument("--video-id")
    parser.add_argument("--overlay-label")
    args = parser.parse_args()
    if not args.url and not args.input_path:
        parser.error("Provide either --url or --input.")
    return args


def build_config(args: argparse.Namespace) -> PipelineConfig:
    return PipelineConfig(
        url=args.url,
        input_path=args.input_path,
        max_group_seconds=args.max_group_seconds,
        max_group_words=args.max_group_words,
        max_gap_seconds=args.max_gap_seconds,
        transcript=TranscriptConfig(
            source_mode=args.transcript_source,
            backend=args.transcription_backend,
            openai_model=args.transcription_model,
            language=args.transcription_language,
            local_model=args.local_transcription_model,
            local_device=args.local_transcription_device,
            local_compute_type=args.local_transcription_compute_type,
            timeout_seconds=args.transcription_timeout_seconds,
            chunk_seconds=args.transcription_chunk_seconds,
            openai_api_key_env=args.openai_api_key_env,
        ),
        translation=TranslationConfig(
            backend=args.translator,
            batch_size=args.batch_size,
            wrap_width=args.wrap_width,
            glossary_path=args.glossary,
            openai_model=args.openai_model,
            openai_reasoning_effort=args.openai_reasoning_effort,
            openai_api_key_env=args.openai_api_key_env,
            openai_timeout_seconds=args.openai_timeout_seconds,
        ),
        output=OutputConfig(
            output_path=args.output,
            english_output=args.english_output,
            english_text_output=args.english_text_output,
            extension_root=args.extension_root,
            video_id=args.video_id,
            overlay_label=args.overlay_label,
            review_output=args.review_output,
            json_output=args.json_output,
        ),
    )


def main() -> None:
    args = parse_args()
    config = build_config(args)
    result = run_pipeline(config)

    print(f"English input: {result.input_reference}")
    print(f"English segments: {result.english_segments_count}")
    print(f"Grouped entries: {result.grouped_segments_count}")
    print(f"Translator: {config.translation.backend}")
    if config.url:
        print(f"Transcript source: {config.transcript.source_mode}")
    print(f"Korean output: {result.korean_output_path}")
    if result.overlay_subtitle_path is not None:
        print(f"Overlay subtitle: {result.overlay_subtitle_path}")


if __name__ == "__main__":
    main()
