from __future__ import annotations

import argparse
from pathlib import Path

from ..glossary.loader import list_glossary_profiles
from .config import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_LOCAL_TRANSCRIPTION_COMPUTE_TYPE,
    DEFAULT_LOCAL_TRANSCRIPTION_DEVICE,
    DEFAULT_LOCAL_TRANSCRIPTION_MODEL,
    DEFAULT_LOCAL_TRANSLATION_DEVICE,
    DEFAULT_LOCAL_TRANSLATION_MAX_INPUT_LENGTH,
    DEFAULT_LOCAL_TRANSLATION_MAX_NEW_TOKENS,
    DEFAULT_LOCAL_TRANSLATION_MODEL,
    DEFAULT_LOCAL_TRANSLATION_NUM_BEAMS,
    DEFAULT_LOCAL_TRANSLATION_SOURCE_LANG,
    DEFAULT_LOCAL_TRANSLATION_TARGET_LANG,
    DEFAULT_MAX_GAP_SECONDS,
    DEFAULT_MAX_GROUP_SECONDS,
    DEFAULT_MAX_GROUP_WORDS,
    DEFAULT_TRANSCRIPT_SOURCE,
    DEFAULT_TRANSCRIPTION_LANGUAGE,
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
            "Generate English lecture transcripts from YouTube or local subtitle files, "
            "translate them into Korean with local or free backends, and write subtitle artifacts."
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
    parser.add_argument("--transcription-language", default=DEFAULT_TRANSCRIPTION_LANGUAGE)
    parser.add_argument("--local-transcription-model", default=DEFAULT_LOCAL_TRANSCRIPTION_MODEL)
    parser.add_argument("--local-transcription-device", default=DEFAULT_LOCAL_TRANSCRIPTION_DEVICE)
    parser.add_argument("--local-transcription-compute-type", default=DEFAULT_LOCAL_TRANSCRIPTION_COMPUTE_TYPE)
    parser.add_argument("--english-output", type=Path)
    parser.add_argument("--english-text-output", type=Path)
    parser.add_argument(
        "--translator",
        choices=("local_mt", "google"),
        default=DEFAULT_TRANSLATOR,
        help="Translation backend. 'local_mt' is the recommended quality path. 'google' is quick draft mode.",
    )
    parser.add_argument("--glossary", type=Path, help="Direct glossary file path.")
    parser.add_argument(
        "--glossary-profile",
        help="Named glossary profile from glossaries/registry.json, for example 'underactuated'.",
    )
    parser.add_argument(
        "--glossary-registry",
        type=Path,
        help="Optional custom glossary registry JSON path.",
    )
    parser.add_argument(
        "--list-glossary-profiles",
        action="store_true",
        help="List available glossary profiles and exit.",
    )
    parser.add_argument(
        "--local-translation-model",
        default=DEFAULT_LOCAL_TRANSLATION_MODEL,
        help="Local seq2seq translation model identifier, such as facebook/nllb-200-distilled-600M.",
    )
    parser.add_argument("--local-translation-device", default=DEFAULT_LOCAL_TRANSLATION_DEVICE)
    parser.add_argument("--local-translation-source-lang", default=DEFAULT_LOCAL_TRANSLATION_SOURCE_LANG)
    parser.add_argument("--local-translation-target-lang", default=DEFAULT_LOCAL_TRANSLATION_TARGET_LANG)
    parser.add_argument("--local-translation-max-input-length", type=int, default=DEFAULT_LOCAL_TRANSLATION_MAX_INPUT_LENGTH)
    parser.add_argument("--local-translation-max-new-tokens", type=int, default=DEFAULT_LOCAL_TRANSLATION_MAX_NEW_TOKENS)
    parser.add_argument("--local-translation-num-beams", type=int, default=DEFAULT_LOCAL_TRANSLATION_NUM_BEAMS)
    parser.add_argument("--extension-root", type=Path)
    parser.add_argument("--video-id")
    parser.add_argument("--overlay-label")
    args = parser.parse_args()
    if args.glossary and args.glossary_profile:
        parser.error("Use either --glossary or --glossary-profile, not both.")
    if not args.list_glossary_profiles and not args.url and not args.input_path:
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
            language=args.transcription_language,
            local_model=args.local_transcription_model,
            local_device=args.local_transcription_device,
            local_compute_type=args.local_transcription_compute_type,
        ),
        translation=TranslationConfig(
            backend=args.translator,
            batch_size=args.batch_size,
            wrap_width=args.wrap_width,
            glossary_path=args.glossary,
            glossary_profile=args.glossary_profile,
            glossary_registry_path=args.glossary_registry,
            local_model=args.local_translation_model,
            local_device=args.local_translation_device,
            local_source_lang=args.local_translation_source_lang,
            local_target_lang=args.local_translation_target_lang,
            local_max_input_length=args.local_translation_max_input_length,
            local_max_new_tokens=args.local_translation_max_new_tokens,
            local_num_beams=args.local_translation_num_beams,
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


def print_glossary_profiles(registry_path: Path | None) -> None:
    profiles = list_glossary_profiles(registry_path)
    if not profiles:
        print("No glossary profiles found.")
        return

    for profile in profiles:
        print(f"{profile.name}: {profile.label}")
        print(f"  file: {profile.path}")
        if profile.description:
            print(f"  description: {profile.description}")


def main() -> None:
    args = parse_args()
    if args.list_glossary_profiles:
        print_glossary_profiles(args.glossary_registry)
        return

    config = build_config(args)
    result = run_pipeline(config)

    print(f"English input: {result.input_reference}")
    print(f"English segments: {result.english_segments_count}")
    print(f"Grouped entries: {result.grouped_segments_count}")
    print(f"Translator: {config.translation.backend}")
    if config.translation.glossary_profile:
        print(f"Glossary profile: {config.translation.glossary_profile}")
    elif config.translation.glossary_path is not None:
        print(f"Glossary file: {config.translation.glossary_path.resolve()}")
    if config.url:
        print(f"Transcript source: {config.transcript.source_mode}")
    print(f"Korean output: {result.korean_output_path}")
    if result.overlay_subtitle_path is not None:
        print(f"Overlay subtitle: {result.overlay_subtitle_path}")
    if result.quality_issue_count:
        print(f"Quality warnings: {result.quality_issue_count}")


if __name__ == "__main__":
    main()
