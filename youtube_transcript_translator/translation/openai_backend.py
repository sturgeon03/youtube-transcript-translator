from __future__ import annotations

import json
import os
import time
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

from ..app.config import DEFAULT_OPENAI_MAX_BATCH_SIZE
from ..glossary.protector import prepare_text_for_translation
from ..normalize.regroup import build_display_friendly_subtitles
from ..normalize.text_cleaner import normalize_text
from ..postprocess.restore import restore_translation_text
from ..transcript.models import TranscriptSegment
from .base import TranslationBackend


def build_openai_translation_instructions(glossary: dict[str, str]) -> str:
    lines = [
        "You translate English lecture subtitles into accurate, concise Korean subtitles.",
        "Return only JSON that matches the requested schema.",
        "Translate every segment independently without dropping or merging meaning.",
        "Preserve equations, symbols, variable names, code identifiers, filenames, and URLs exactly.",
        "Use natural spoken Korean suitable for technical lecture subtitles.",
        "Keep robotics, control, optimization, and math terminology consistent across the batch.",
        "Do not add commentary, speaker labels, or explanations.",
    ]
    if glossary:
        lines.append("Use the following glossary entries exactly when the source term appears:")
        for source, target in sorted(glossary.items()):
            lines.append(f"- {source} => {target}")
    return "\n".join(lines)


def build_openai_translation_schema(expected_count: int) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "translations": {
                "type": "array",
                "minItems": expected_count,
                "maxItems": expected_count,
                "items": {
                    "type": "object",
                    "properties": {
                        "index": {"type": "integer", "minimum": 0},
                        "translation": {"type": "string", "minLength": 1},
                    },
                    "required": ["index", "translation"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["translations"],
        "additionalProperties": False,
    }


def extract_openai_output_text(response_data: dict[str, Any]) -> str:
    direct_text = response_data.get("output_text")
    if isinstance(direct_text, str) and direct_text.strip():
        return direct_text.strip()

    parts: list[str] = []
    for item in response_data.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            content_text = content.get("text")
            if isinstance(content_text, str) and content_text.strip():
                parts.append(content_text.strip())
    return "\n".join(parts).strip()


def openai_responses_create(
    *,
    api_key: str,
    model: str,
    instructions: str,
    input_text: str,
    reasoning_effort: str,
    timeout_seconds: float,
    schema: dict[str, Any],
) -> dict[str, Any]:
    request_body = {
        "model": model,
        "instructions": instructions,
        "input": input_text,
        "reasoning": {"effort": reasoning_effort},
        "text": {
            "format": {
                "type": "json_schema",
                "name": "subtitle_batch_translation",
                "strict": True,
                "schema": schema,
            }
        },
        "store": False,
    }

    request = urllib_request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(request_body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib_request.urlopen(request, timeout=timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib_error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI API request failed with status {exc.code}: {body}") from exc
    except urllib_error.URLError as exc:
        raise RuntimeError(f"OpenAI API request failed: {exc}") from exc


def resolve_openai_api_key(env_name: str) -> str:
    api_key = os.environ.get(env_name, "").strip()
    if not api_key:
        raise ValueError(f"OpenAI API use requires environment variable {env_name} to be set.")
    return api_key


def translate_batch_openai_once(
    batch: list[TranscriptSegment],
    *,
    glossary: dict[str, str],
    model: str,
    reasoning_effort: str,
    api_key: str,
    timeout_seconds: float,
) -> list[str]:
    indexed_segments = []
    replacements_per_index: dict[int, dict[str, str]] = {}
    for index, group in enumerate(batch):
        prepared_text, replacements = prepare_text_for_translation(group.text, glossary)
        replacements_per_index[index] = replacements
        indexed_segments.append(
            {
                "index": index,
                "text": normalize_text(prepared_text),
            }
        )
    schema = build_openai_translation_schema(len(indexed_segments))
    response_data = openai_responses_create(
        api_key=api_key,
        model=model,
        instructions=build_openai_translation_instructions(glossary),
        input_text=json.dumps({"segments": indexed_segments}, ensure_ascii=False),
        reasoning_effort=reasoning_effort,
        timeout_seconds=timeout_seconds,
        schema=schema,
    )

    response_text = extract_openai_output_text(response_data)
    if not response_text:
        raise RuntimeError("OpenAI API returned an empty translation payload.")

    payload = json.loads(response_text)
    translations = payload.get("translations")
    if not isinstance(translations, list):
        raise ValueError("OpenAI translation payload did not contain a translations list.")

    mapped: dict[int, str] = {}
    for entry in translations:
        if not isinstance(entry, dict):
            continue
        index = entry.get("index")
        translation = entry.get("translation")
        if not isinstance(index, int) or not isinstance(translation, str):
            continue
        restored_translation = restore_translation_text(translation, replacements_per_index.get(index, {}))
        clean_translation = normalize_text(restored_translation)
        if clean_translation:
            mapped[index] = clean_translation

    ordered = []
    for index in range(len(indexed_segments)):
        if index not in mapped:
            raise ValueError(f"OpenAI translation payload was missing segment index {index}.")
        ordered.append(mapped[index])
    return ordered


def translate_batch_openai(
    batch: list[TranscriptSegment],
    *,
    glossary: dict[str, str],
    model: str,
    reasoning_effort: str,
    api_key: str,
    timeout_seconds: float,
    depth: int = 0,
) -> list[str]:
    try:
        return translate_batch_openai_once(
            batch,
            glossary=glossary,
            model=model,
            reasoning_effort=reasoning_effort,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
        )
    except Exception:
        if len(batch) <= 1 or depth >= 4:
            raise
        midpoint = len(batch) // 2
        left = translate_batch_openai(
            batch[:midpoint],
            glossary=glossary,
            model=model,
            reasoning_effort=reasoning_effort,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            depth=depth + 1,
        )
        right = translate_batch_openai(
            batch[midpoint:],
            glossary=glossary,
            model=model,
            reasoning_effort=reasoning_effort,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            depth=depth + 1,
        )
        return left + right


class OpenAITranslationBackend(TranslationBackend):
    name = "openai"

    def __init__(
        self,
        *,
        model: str,
        reasoning_effort: str,
        api_key_env: str,
        timeout_seconds: float,
    ) -> None:
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.api_key_env = api_key_env
        self.timeout_seconds = timeout_seconds

    def translate_segments(
        self,
        segments: list[TranscriptSegment],
        *,
        wrap_width: int,
        batch_size: int,
        glossary: dict[str, str],
    ) -> list[TranscriptSegment]:
        api_key = resolve_openai_api_key(self.api_key_env)
        translated: list[TranscriptSegment] = []
        next_index = 1
        effective_batch_size = min(batch_size, DEFAULT_OPENAI_MAX_BATCH_SIZE)

        for offset in range(0, len(segments), effective_batch_size):
            batch = segments[offset : offset + effective_batch_size]
            translated_texts = translate_batch_openai(
                batch,
                glossary=glossary,
                model=self.model,
                reasoning_effort=self.reasoning_effort,
                api_key=api_key,
                timeout_seconds=self.timeout_seconds,
            )
            for segment, text in zip(batch, translated_texts):
                built_subtitles = build_display_friendly_subtitles(
                    segment,
                    text=text,
                    wrap_width=wrap_width,
                    start_index=next_index,
                )
                translated.extend(built_subtitles)
                next_index += len(built_subtitles)
            print(
                f"Translated {min(offset + effective_batch_size, len(segments))}/{len(segments)} groups",
                flush=True,
            )
            time.sleep(0.4)
        return translated
