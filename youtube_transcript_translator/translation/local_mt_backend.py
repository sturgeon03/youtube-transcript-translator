from __future__ import annotations

import copy
from functools import lru_cache
from pathlib import Path
from typing import Any

from ..glossary.protector import prepare_text_for_translation
from ..normalize.text_cleaner import normalize_text
from ..postprocess.restore import restore_translation_text
from ..transcript.models import TranscriptSegment
from .base import ProgressCallback, TranslationBackend, report_progress

try:
    from huggingface_hub import snapshot_download
except Exception:  # pragma: no cover - runtime dependency guard
    snapshot_download = None  # type: ignore[assignment]

try:
    import torch
except Exception as exc:  # pragma: no cover - runtime dependency guard
    torch = None  # type: ignore[assignment]
    _TORCH_IMPORT_ERROR = exc
else:
    _TORCH_IMPORT_ERROR = None

try:
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
except Exception as exc:  # pragma: no cover - runtime dependency guard
    AutoModelForSeq2SeqLM = None  # type: ignore[assignment]
    AutoTokenizer = None  # type: ignore[assignment]
    _TRANSFORMERS_IMPORT_ERROR = exc
else:
    _TRANSFORMERS_IMPORT_ERROR = None

try:
    from tqdm.auto import tqdm as tqdm_base
except Exception:  # pragma: no cover - runtime dependency guard
    tqdm_base = None  # type: ignore[assignment]


def _require_local_mt_dependencies() -> None:
    if torch is None:
        raise ImportError(
            "torch is required for the local translation backend. "
            "Install it with `python -m pip install torch`."
        ) from _TORCH_IMPORT_ERROR
    if AutoModelForSeq2SeqLM is None or AutoTokenizer is None:
        raise ImportError(
            "transformers and sentencepiece are required for the local translation backend. "
            "Install them with `python -m pip install transformers sentencepiece`."
        ) from _TRANSFORMERS_IMPORT_ERROR


def resolve_translation_device(device: str) -> str:
    _require_local_mt_dependencies()
    if device != "auto":
        return device
    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def _format_bytes(size: float) -> str:
    units = ["B", "KB", "MB", "GB"]
    value = float(size)
    for unit in units:
        if value < 1024.0 or unit == units[-1]:
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{value:.1f} TB"


def _make_download_progress_class(progress_callback: ProgressCallback | None) -> type[Any] | None:
    if progress_callback is None or tqdm_base is None:
        return None

    class SnapshotProgressBar(tqdm_base):  # type: ignore[misc, valid-type]
        def __init__(self, *args, **kwargs):
            self._reportable = kwargs.get("unit") == "B" or kwargs.get("name") == "huggingface_hub.snapshot_download"
            kwargs["disable"] = True
            self._last_reported = -1.0
            super().__init__(*args, **kwargs)
            self._emit_progress()

        def update(self, n: int | float = 1) -> bool | None:  # type: ignore[override]
            result = super().update(n)
            self._emit_progress()
            return result

        def refresh(self, *args, **kwargs):  # type: ignore[override]
            result = super().refresh(*args, **kwargs)
            self._emit_progress()
            return result

        def set_description(self, desc=None, refresh=True):  # type: ignore[override]
            result = super().set_description(desc=desc, refresh=refresh)
            self._emit_progress(description_override=desc)
            return result

        def close(self):  # type: ignore[override]
            self._emit_progress()
            return super().close()

        def _emit_progress(self, description_override: str | None = None) -> None:
            if not self._reportable:
                return
            total = float(getattr(self, "total", 0) or 0)
            current = float(getattr(self, "n", 0) or 0)
            raw_percent = 0.0 if total <= 0 else min(100.0, max(0.0, (current / total) * 100.0))
            mapped_percent = 5.0 + raw_percent * 0.5
            if abs(mapped_percent - self._last_reported) < 0.4 and description_override is None:
                return
            self._last_reported = mapped_percent
            label = description_override or getattr(self, "desc", None) or "Downloading translation model"
            detail = label
            if total > 0:
                detail = f"{label}: {_format_bytes(current)} / {_format_bytes(total)}"
            report_progress(
                progress_callback,
                stage="downloading_model",
                progress=mapped_percent,
                detail=detail,
            )

    return SnapshotProgressBar


def resolve_model_source(
    model_name: str,
    *,
    progress_callback: ProgressCallback | None = None,
) -> str:
    if snapshot_download is None:
        report_progress(
            progress_callback,
            stage="loading_model",
            progress=55.0,
            detail=f"Preparing translation model {model_name}",
        )
        return model_name

    report_progress(
        progress_callback,
        stage="downloading_model",
        progress=5.0,
        detail=f"Checking local cache for {model_name}",
    )
    try:
        local_path = snapshot_download(
            model_name,
            tqdm_class=_make_download_progress_class(progress_callback),
        )
        report_progress(
            progress_callback,
            stage="downloading_model",
            progress=55.0,
            detail=f"Translation model snapshot ready: {model_name}",
        )
        return local_path
    except Exception as exc:  # pragma: no cover - network/runtime fallback
        report_progress(
            progress_callback,
            stage="loading_model",
            progress=55.0,
            detail=f"Falling back to direct transformers load for {model_name} ({exc.__class__.__name__})",
        )
        return model_name


@lru_cache(maxsize=4)
def _load_model_bundle(model_source: str, device: str) -> tuple[Any, Any]:
    _require_local_mt_dependencies()
    load_kwargs: dict[str, Any] = {}
    if Path(model_source).exists():
        load_kwargs["local_files_only"] = True
    tokenizer = AutoTokenizer.from_pretrained(model_source, **load_kwargs)
    model = AutoModelForSeq2SeqLM.from_pretrained(model_source, **load_kwargs)
    model.to(device)
    model.eval()
    return tokenizer, model


def load_local_translation_bundle(
    *,
    model_name: str,
    device: str,
    progress_callback: ProgressCallback | None = None,
) -> tuple[Any, Any, str]:
    resolved_device = resolve_translation_device(device)
    model_source = resolve_model_source(
        model_name,
        progress_callback=progress_callback,
    )
    report_progress(
        progress_callback,
        stage="loading_model",
        progress=60.0,
        detail=f"Loading local translation model on {resolved_device}",
    )
    tokenizer, model = _load_model_bundle(model_source, resolved_device)
    report_progress(
        progress_callback,
        stage="loading_model",
        progress=72.0,
        detail=f"Translation model ready on {resolved_device}",
    )
    return tokenizer, model, resolved_device


def _generation_kwargs(
    tokenizer: Any,
    *,
    target_lang: str,
    max_new_tokens: int,
    num_beams: int,
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "max_new_tokens": max_new_tokens,
        "num_beams": max(1, num_beams),
    }
    lang_code_to_id = getattr(tokenizer, "lang_code_to_id", None)
    if isinstance(lang_code_to_id, dict) and target_lang in lang_code_to_id:
        kwargs["forced_bos_token_id"] = lang_code_to_id[target_lang]
        return kwargs

    if hasattr(tokenizer, "convert_tokens_to_ids"):
        token_id = tokenizer.convert_tokens_to_ids(target_lang)
        if isinstance(token_id, int) and token_id >= 0:
            kwargs["forced_bos_token_id"] = token_id
    return kwargs


def translate_batch_with_bundle(
    tokenizer: Any,
    model: Any,
    texts: list[str],
    *,
    device: str,
    source_lang: str,
    target_lang: str,
    max_input_length: int,
    max_new_tokens: int,
    num_beams: int,
) -> list[str]:
    _require_local_mt_dependencies()
    if hasattr(tokenizer, "src_lang"):
        tokenizer.src_lang = source_lang

    encoded = tokenizer(
        texts,
        return_tensors="pt",
        padding=True,
        truncation=True,
        max_length=max_input_length,
    )
    encoded = {key: value.to(device) for key, value in encoded.items()}
    generation_kwargs = _generation_kwargs(
        tokenizer,
        target_lang=target_lang,
        max_new_tokens=max_new_tokens,
        num_beams=num_beams,
    )
    generation_config = getattr(model, "generation_config", None)
    if generation_config is not None:
        generation_config = copy.deepcopy(generation_config)
        generation_config.max_length = None
        generation_kwargs["generation_config"] = generation_config

    with torch.inference_mode():
        generated = model.generate(**encoded, **generation_kwargs)

    return [
        normalize_text(text)
        for text in tokenizer.batch_decode(generated, skip_special_tokens=True)
    ]


def translate_batch_local_model(
    texts: list[str],
    *,
    model_name: str,
    device: str,
    source_lang: str,
    target_lang: str,
    max_input_length: int,
    max_new_tokens: int,
    num_beams: int,
    progress_callback: ProgressCallback | None = None,
) -> list[str]:
    tokenizer, model, resolved_device = load_local_translation_bundle(
        model_name=model_name,
        device=device,
        progress_callback=progress_callback,
    )
    return translate_batch_with_bundle(
        tokenizer,
        model,
        texts,
        device=resolved_device,
        source_lang=source_lang,
        target_lang=target_lang,
        max_input_length=max_input_length,
        max_new_tokens=max_new_tokens,
        num_beams=num_beams,
    )


class LocalMTTranslationBackend(TranslationBackend):
    name = "local_mt"

    def __init__(
        self,
        *,
        model_name: str,
        device: str,
        source_lang: str,
        target_lang: str,
        max_input_length: int,
        max_new_tokens: int,
        num_beams: int,
    ) -> None:
        self.model_name = model_name
        self.device = device
        self.source_lang = source_lang
        self.target_lang = target_lang
        self.max_input_length = max_input_length
        self.max_new_tokens = max_new_tokens
        self.num_beams = num_beams

    def translate_segments(
        self,
        segments: list[TranscriptSegment],
        *,
        batch_size: int,
        glossary: dict[str, str],
        progress_callback: ProgressCallback | None = None,
    ) -> list[TranscriptSegment]:
        effective_batch_size = max(1, batch_size)
        translated: list[TranscriptSegment] = []
        total_segments = len(segments)

        if not segments:
            report_progress(
                progress_callback,
                stage="translating",
                progress=100.0,
                detail="No subtitle groups were queued for translation.",
            )
            return translated

        report_progress(
            progress_callback,
            stage="loading_model",
            progress=0.0,
            detail=f"Preparing local translation model {self.model_name}",
        )
        tokenizer, model, resolved_device = load_local_translation_bundle(
            model_name=self.model_name,
            device=self.device,
            progress_callback=progress_callback,
        )
        total_batches = max(1, (total_segments + effective_batch_size - 1) // effective_batch_size)

        for batch_index, offset in enumerate(range(0, len(segments), effective_batch_size), start=1):
            batch = segments[offset : offset + effective_batch_size]
            report_progress(
                progress_callback,
                stage="translating",
                progress=75.0 + ((batch_index - 1) / total_batches) * 25.0,
                detail=f"Translating batch {batch_index}/{total_batches}",
            )
            prepared_texts = []
            replacements_per_text = []
            for segment in batch:
                prepared_text, replacements = prepare_text_for_translation(segment.text, glossary)
                prepared_texts.append(prepared_text)
                replacements_per_text.append(replacements)

            translated_texts = translate_batch_with_bundle(
                tokenizer,
                model,
                prepared_texts,
                device=resolved_device,
                source_lang=self.source_lang,
                target_lang=self.target_lang,
                max_input_length=self.max_input_length,
                max_new_tokens=self.max_new_tokens,
                num_beams=self.num_beams,
            )

            for segment, translated_text, replacements in zip(batch, translated_texts, replacements_per_text):
                restored = restore_translation_text(translated_text, replacements)
                translated.append(
                    TranscriptSegment(
                        index=segment.index,
                        start=segment.start,
                        end=segment.end,
                        text=normalize_text(restored),
                        source="local_mt_translation",
                        metadata={
                            "backend": "local_mt",
                            "model": self.model_name,
                        },
                    )
                )

            print(
                f"Translated {min(offset + effective_batch_size, total_segments)}/{total_segments} groups with local_mt",
                flush=True,
            )
            report_progress(
                progress_callback,
                stage="translating",
                progress=75.0 + (batch_index / total_batches) * 25.0,
                detail=f"Translated {min(offset + effective_batch_size, total_segments)}/{total_segments} groups with local_mt",
            )

        return translated
