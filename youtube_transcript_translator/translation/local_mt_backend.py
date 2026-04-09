from __future__ import annotations

from functools import lru_cache
from typing import Any

from ..glossary.protector import prepare_text_for_translation
from ..normalize.text_cleaner import normalize_text
from ..postprocess.restore import restore_translation_text
from ..transcript.models import TranscriptSegment
from .base import TranslationBackend

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


@lru_cache(maxsize=4)
def _load_model_bundle(model_name: str, device: str) -> tuple[Any, Any]:
    _require_local_mt_dependencies()
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForSeq2SeqLM.from_pretrained(model_name)
    model.to(device)
    model.eval()
    return tokenizer, model


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
) -> list[str]:
    _require_local_mt_dependencies()
    resolved_device = resolve_translation_device(device)
    tokenizer, model = _load_model_bundle(model_name, resolved_device)

    if hasattr(tokenizer, "src_lang"):
        tokenizer.src_lang = source_lang

    encoded = tokenizer(
        texts,
        return_tensors="pt",
        padding=True,
        truncation=True,
        max_length=max_input_length,
    )
    encoded = {key: value.to(resolved_device) for key, value in encoded.items()}
    generation_kwargs = _generation_kwargs(
        tokenizer,
        target_lang=target_lang,
        max_new_tokens=max_new_tokens,
        num_beams=num_beams,
    )

    with torch.inference_mode():
        generated = model.generate(**encoded, **generation_kwargs)

    return [
        normalize_text(text)
        for text in tokenizer.batch_decode(generated, skip_special_tokens=True)
    ]


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
    ) -> list[TranscriptSegment]:
        effective_batch_size = max(1, batch_size)
        translated: list[TranscriptSegment] = []

        for offset in range(0, len(segments), effective_batch_size):
            batch = segments[offset : offset + effective_batch_size]
            prepared_texts = []
            replacements_per_text = []
            for segment in batch:
                prepared_text, replacements = prepare_text_for_translation(segment.text, glossary)
                prepared_texts.append(prepared_text)
                replacements_per_text.append(replacements)

            translated_texts = translate_batch_local_model(
                prepared_texts,
                model_name=self.model_name,
                device=self.device,
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
                f"Translated {min(offset + effective_batch_size, len(segments))}/{len(segments)} groups with local_mt",
                flush=True,
            )

        return translated
