from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


DEFAULT_MAX_GROUP_SECONDS = 7.0
DEFAULT_MAX_GROUP_WORDS = 18
DEFAULT_MAX_GAP_SECONDS = 0.75
DEFAULT_WRAP_WIDTH = 24
DEFAULT_BATCH_SIZE = 40
DEFAULT_TRANSLATOR = "google"
DEFAULT_OPENAI_MODEL = "gpt-5.4-mini"
DEFAULT_OPENAI_REASONING_EFFORT = "low"
DEFAULT_OPENAI_TIMEOUT_SECONDS = 120.0
DEFAULT_OPENAI_MAX_BATCH_SIZE = 12
DEFAULT_TRANSCRIPT_SOURCE = "auto"
DEFAULT_TRANSCRIPTION_BACKEND = "local"
DEFAULT_TRANSCRIPTION_MODEL = "gpt-4o-transcribe-diarize"
DEFAULT_TRANSCRIPTION_LANGUAGE = "en"
DEFAULT_TRANSCRIPTION_TIMEOUT_SECONDS = 900.0
DEFAULT_LOCAL_TRANSCRIPTION_MODEL = "small.en"
DEFAULT_LOCAL_TRANSCRIPTION_DEVICE = "auto"
DEFAULT_LOCAL_TRANSCRIPTION_COMPUTE_TYPE = "default"
DEFAULT_TRANSCRIPTION_CHUNK_SECONDS = 600.0
MAX_AUDIO_UPLOAD_BYTES = 25 * 1024 * 1024


@dataclass
class TranscriptConfig:
    source_mode: str
    backend: str
    openai_model: str
    language: str
    local_model: str
    local_device: str
    local_compute_type: str
    timeout_seconds: float
    chunk_seconds: float
    openai_api_key_env: str


@dataclass
class TranslationConfig:
    backend: str
    batch_size: int
    wrap_width: int
    glossary_path: Path | None
    glossary_profile: str | None
    glossary_registry_path: Path | None
    openai_model: str
    openai_reasoning_effort: str
    openai_api_key_env: str
    openai_timeout_seconds: float


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
