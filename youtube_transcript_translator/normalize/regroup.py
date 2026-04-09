from __future__ import annotations

import re
import textwrap

from ..transcript.models import TranscriptSegment
from .overlap import append_with_overlap
from .text_cleaner import normalize_text, seconds_to_timedelta, words


DEFAULT_MAX_DISPLAY_LINES = 2
DEFAULT_MIN_SPLIT_SECONDS = 1.4
SENTENCE_BOUNDARY_PATTERN = re.compile(r'[.!?]["\')\]]*$')
SOFT_BOUNDARY_PATTERN = re.compile(r'[:;]["\')\]]*$')


def should_split_group(
    current_text: str,
    incoming_text: str,
    current_start: float,
    previous_end: float,
    next_start: float,
    max_group_seconds: float,
    max_group_words: int,
    max_gap_seconds: float,
) -> bool:
    if previous_end and next_start - previous_end > max_gap_seconds:
        return True
    if next_start - current_start > max_group_seconds:
        return True
    candidate_text = append_with_overlap(current_text, incoming_text)
    candidate_word_count = len(words(candidate_text))
    if candidate_word_count < max_group_words:
        return False

    current_word_count = len(words(current_text))
    relaxed_limit = max(max_group_words + 8, int(max_group_words * 1.4))
    has_strong_boundary = bool(SENTENCE_BOUNDARY_PATTERN.search(current_text))
    has_soft_boundary = bool(SOFT_BOUNDARY_PATTERN.search(current_text))

    if has_strong_boundary:
        return True
    if has_soft_boundary and current_word_count >= max(6, int(max_group_words * 0.6)):
        return True
    if candidate_word_count >= relaxed_limit:
        return True
    return False


def regroup_subtitles(
    subtitles: list[TranscriptSegment],
    *,
    max_group_seconds: float,
    max_group_words: int,
    max_gap_seconds: float,
) -> list[TranscriptSegment]:
    grouped: list[TranscriptSegment] = []
    current_index = 1
    current_start = None
    current_end = None
    current_text = ""

    for subtitle in subtitles:
        text = normalize_text(subtitle.text)
        if not text:
            continue
        start_seconds = subtitle.start.total_seconds()
        if current_start is None:
            current_start = subtitle.start
            current_end = subtitle.end
            current_text = text
            continue

        candidate_text = append_with_overlap(current_text, text)
        if subtitle.end <= current_end and candidate_text == current_text:
            continue

        if should_split_group(
            current_text=current_text,
            incoming_text=text,
            current_start=current_start.total_seconds(),
            previous_end=current_end.total_seconds(),
            next_start=start_seconds,
            max_group_seconds=max_group_seconds,
            max_group_words=max_group_words,
            max_gap_seconds=max_gap_seconds,
        ):
            grouped.append(
                TranscriptSegment(
                    index=current_index,
                    start=current_start,
                    end=current_end,
                    text=current_text,
                    source="normalized_group",
                )
            )
            current_index += 1
            current_start = max(subtitle.start, current_end)
            if subtitle.end <= current_start:
                current_start = None
                current_end = None
                current_text = ""
                continue
            current_end = subtitle.end
            current_text = text
            continue

        current_end = max(current_end, subtitle.end)
        current_text = candidate_text

    if current_start is not None:
        grouped.append(
            TranscriptSegment(
                index=current_index,
                start=current_start,
                end=current_end,
                text=current_text,
                source="normalized_group",
            )
        )
    return grouped


def wrap_korean_text(text: str, width: int) -> str:
    normalized = normalize_text(text)
    if len(normalized) <= width:
        return normalized

    word_parts = words(normalized)
    if len(word_parts) >= 4:
        best_split = None
        best_score = None
        for index in range(1, len(word_parts)):
            left = " ".join(word_parts[:index]).strip()
            right = " ".join(word_parts[index:]).strip()
            if not left or not right:
                continue
            max_length = max(len(left), len(right))
            overflow_penalty = max(0, max_length - width) * 3
            score = abs(len(left) - len(right)) + overflow_penalty
            if best_score is None or score < best_score:
                best_score = score
                best_split = (left, right)
        if best_split is not None and max(len(best_split[0]), len(best_split[1])) <= width + 6:
            return f"{best_split[0]}\n{best_split[1]}"

    return textwrap.fill(
        normalized,
        width=width,
        break_long_words=False,
        break_on_hyphens=False,
    )


def wrapped_lines(text: str, width: int) -> list[str]:
    normalized = normalize_text(text)
    if not normalized:
        return []
    wrapped = wrap_korean_text(normalized, width)
    return [line.strip() for line in wrapped.splitlines() if line.strip()]


def split_text_by_words(text: str, max_chars: int) -> list[str]:
    word_parts = words(text)
    if not word_parts:
        return []

    chunks: list[str] = []
    current_words: list[str] = []

    for word in word_parts:
        candidate_words = current_words + [word]
        candidate_text = " ".join(candidate_words).strip()
        if current_words and len(candidate_text) > max_chars:
            chunks.append(" ".join(current_words).strip())
            current_words = [word]
            continue
        current_words = candidate_words
        if len(candidate_text) >= int(max_chars * 0.6) and re.search(r"[.!?,:;)]$", word):
            chunks.append(candidate_text)
            current_words = []

    if current_words:
        chunks.append(" ".join(current_words).strip())
    return [chunk for chunk in chunks if chunk]


def split_text_by_char_limit(text: str, max_chars: int) -> list[str]:
    normalized = normalize_text(text)
    if not normalized:
        return []
    if " " in normalized:
        return split_text_by_words(normalized, max_chars)

    parts = textwrap.wrap(
        normalized,
        width=max_chars,
        break_long_words=True,
        break_on_hyphens=False,
    )
    return [part.strip() for part in parts if part.strip()]


def split_text_for_display(
    text: str,
    *,
    wrap_width: int,
    max_lines: int = DEFAULT_MAX_DISPLAY_LINES,
) -> list[str]:
    normalized = normalize_text(text)
    if not normalized:
        return []

    if len(wrapped_lines(normalized, wrap_width)) <= max_lines:
        return [normalized]

    max_chars = max(wrap_width * max_lines - 2, wrap_width + 8)
    chunks = split_text_by_words(normalized, max_chars)
    if not chunks:
        chunks = [normalized]

    refined: list[str] = []
    for chunk in chunks:
        if len(wrapped_lines(chunk, wrap_width)) <= max_lines:
            refined.append(chunk)
            continue
        refined.extend(split_text_by_char_limit(chunk, max(wrap_width + 2, max_chars // 2)))

    return [chunk for chunk in refined if chunk]


def merge_text_segments(parts: list[str], target_count: int = 2) -> list[str]:
    if len(parts) <= target_count:
        return parts

    total_length = sum(len(part) for part in parts)
    target_length = max(total_length / target_count, 1)
    merged: list[str] = []
    current = ""

    for part in parts:
        candidate = f"{current} {part}".strip() if current else part
        if current and len(candidate) > target_length and len(merged) < target_count - 1:
            merged.append(current)
            current = part
            continue
        current = candidate

    if current:
        merged.append(current)
    return merged


def reduce_chunk_count_to_fit_duration(
    chunks: list[str],
    *,
    duration_seconds: float,
    min_split_seconds: float = DEFAULT_MIN_SPLIT_SECONDS,
) -> list[str]:
    if len(chunks) <= 1:
        return chunks
    max_chunk_count = max(1, int(duration_seconds // min_split_seconds))
    if max_chunk_count >= len(chunks):
        return chunks
    return merge_text_segments(chunks, max_chunk_count)


def allocate_subtitle_durations(chunks: list[str], total_duration: float) -> list[float]:
    if not chunks:
        return []
    if len(chunks) == 1:
        return [max(total_duration, 0.01)]

    weights = [max(len(re.sub(r"\s+", "", chunk)), 1) for chunk in chunks]
    remaining_duration = max(total_duration, 0.01)
    remaining_weight = sum(weights)
    allocated: list[float] = []

    for index, weight in enumerate(weights):
        remaining_chunks = len(weights) - index
        if remaining_chunks == 1:
            allocated.append(remaining_duration)
            break

        min_remaining = 0.7 * (remaining_chunks - 1)
        raw_duration = remaining_duration * (weight / remaining_weight)
        duration = max(0.7, raw_duration)
        duration = min(duration, remaining_duration - min_remaining)
        allocated.append(duration)
        remaining_duration -= duration
        remaining_weight -= weight

    return allocated


def build_display_friendly_subtitles(
    subtitle: TranscriptSegment,
    *,
    text: str,
    wrap_width: int,
    start_index: int,
) -> list[TranscriptSegment]:
    normalized = normalize_text(text)
    if not normalized:
        return []

    total_duration = max((subtitle.end - subtitle.start).total_seconds(), 0.01)
    chunks = split_text_for_display(normalized, wrap_width=wrap_width)
    chunks = reduce_chunk_count_to_fit_duration(chunks, duration_seconds=total_duration)
    durations = allocate_subtitle_durations(chunks, total_duration)

    built: list[TranscriptSegment] = []
    current_start = subtitle.start
    for offset, (chunk, duration_seconds) in enumerate(zip(chunks, durations), start=0):
        if offset == len(chunks) - 1:
            current_end = subtitle.end
        else:
            current_end = current_start + seconds_to_timedelta(duration_seconds)
        built.append(
            TranscriptSegment(
                index=start_index + offset,
                start=current_start,
                end=max(current_end, current_start + seconds_to_timedelta(0.01)),
                text=wrap_korean_text(chunk, wrap_width),
                source="display_segment",
            )
        )
        current_start = current_end
    return built
