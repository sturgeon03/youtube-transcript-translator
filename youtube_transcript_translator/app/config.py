from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


DEFAULT_MAX_GROUP_SECONDS = 7.0
DEFAULT_MAX_GROUP_WORDS = 18
DEFAULT_MAX_GAP_SECONDS = 0.75
DEFAULT_WRAP_WIDTH = 24
DEFAULT_BATCH_SIZE = 8
DEFAULT_TRANSLATOR = "local_mt"
DEFAULT_TRANSCRIPT_SOURCE = "auto"
DEFAULT_TRANSCRIPTION_LANGUAGE = "en"
DEFAULT_LOCAL_TRANSCRIPTION_MODEL = "small.en"
DEFAULT_LOCAL_TRANSCRIPTION_DEVICE = "auto"
DEFAULT_LOCAL_TRANSCRIPTION_COMPUTE_TYPE = "default"
DEFAULT_LOCAL_TRANSLATION_MODEL = "facebook/nllb-200-distilled-600M"
DEFAULT_LOCAL_TRANSLATION_DEVICE = "auto"
DEFAULT_LOCAL_TRANSLATION_SOURCE_LANG = "eng_Latn"
DEFAULT_LOCAL_TRANSLATION_TARGET_LANG = "kor_Hang"
DEFAULT_LOCAL_TRANSLATION_MAX_INPUT_LENGTH = 512
DEFAULT_LOCAL_TRANSLATION_MAX_NEW_TOKENS = 256
DEFAULT_LOCAL_TRANSLATION_NUM_BEAMS = 4


@dataclass
class TranscriptConfig:
    source_mode: str
    language: str
    local_model: str
    local_device: str
    local_compute_type: str


@dataclass
class TranslationConfig:
    backend: str
    batch_size: int
    wrap_width: int
    glossary_path: Path | None
    glossary_profile: str | None
    glossary_registry_path: Path | None
    local_model: str
    local_device: str
    local_source_lang: str
    local_target_lang: str
    local_max_input_length: int
    local_max_new_tokens: int
    local_num_beams: int


@dataclass
class OutputConfig:
    output_path: Path | None
    english_output: Path | None
    english_text_output: Path | None
    extension_root: Path | None
    video_id: str | None
    overlay_label: str | None
    review_output: Path | None = None
    json_output: Path | None = None


@dataclass
class PipelineConfig:
    url: str | None
    input_path: Path | None
    max_group_seconds: float
    max_group_words: int
    max_gap_seconds: float
    transcript: TranscriptConfig
    translation: TranslationConfig
    output: OutputConfig
