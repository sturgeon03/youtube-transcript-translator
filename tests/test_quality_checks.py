from __future__ import annotations

import unittest
from datetime import timedelta

from youtube_transcript_translator.postprocess.quality_checks import (
    collect_translation_quality_issues,
    extract_protected_tokens,
)
from youtube_transcript_translator.transcript.models import TranscriptSegment


class QualityCheckTests(unittest.TestCase):
    def test_extract_protected_tokens_finds_urls_and_filenames(self) -> None:
        tokens = extract_protected_tokens("Use https://example.com with controller.py and x_dot = A x.")
        self.assertIn("https://example.com", tokens)
        self.assertIn("controller.py", tokens)

    def test_quality_checks_flag_missing_glossary_and_token_restoration(self) -> None:
        english_segments = [
            TranscriptSegment(
                index=1,
                start=timedelta(seconds=0),
                end=timedelta(seconds=3),
                text="Use state feedback in controller.py where x_dot = A x.",
            )
        ]
        translated_segments = [
            TranscriptSegment(
                index=1,
                start=timedelta(seconds=0),
                end=timedelta(seconds=3),
                text="제어기를 사용하고 선형 모델을 생각합시다.",
            )
        ]

        issues = collect_translation_quality_issues(
            english_segments,
            translated_segments,
            glossary={"state feedback": "상태 피드백"},
            wrap_width=24,
        )

        categories = {issue.category for issue in issues}
        self.assertIn("glossary_target", categories)
        self.assertIn("protected_token", categories)
        self.assertIn("symbol_preservation", categories)
