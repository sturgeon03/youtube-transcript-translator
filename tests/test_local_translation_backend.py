from __future__ import annotations

import unittest
from datetime import timedelta
from unittest.mock import patch

from youtube_transcript_translator.translation.local_mt_backend import LocalMTTranslationBackend
from youtube_transcript_translator.transcript.models import TranscriptSegment


class LocalTranslationBackendTests(unittest.TestCase):
    def test_local_backend_restores_glossary_and_protected_tokens(self) -> None:
        backend = LocalMTTranslationBackend(
            model_name="dummy-model",
            device="cpu",
            source_lang="eng_Latn",
            target_lang="kor_Hang",
            max_input_length=128,
            max_new_tokens=64,
            num_beams=2,
        )
        segments = [
            TranscriptSegment(
                index=1,
                start=timedelta(seconds=0),
                end=timedelta(seconds=2),
                text="Use state feedback in controller.py",
            )
        ]

        with patch(
            "youtube_transcript_translator.translation.local_mt_backend.load_local_translation_bundle",
            return_value=("tokenizer", "model", "cpu"),
        ), patch(
            "youtube_transcript_translator.translation.local_mt_backend.translate_batch_with_bundle",
            return_value=["ZXQTERM0ZXQ ZXQPROTECT0ZXQ"],
        ):
            translated = backend.translate_segments(
                segments,
                batch_size=1,
                glossary={"state feedback": "상태 피드백"},
            )

        self.assertEqual(len(translated), 1)
        self.assertIn("상태 피드백", translated[0].text)
        self.assertIn("controller.py", translated[0].text)

    def test_local_backend_reports_progress(self) -> None:
        backend = LocalMTTranslationBackend(
            model_name="dummy-model",
            device="cpu",
            source_lang="eng_Latn",
            target_lang="kor_Hang",
            max_input_length=128,
            max_new_tokens=64,
            num_beams=2,
        )
        segments = [
            TranscriptSegment(
                index=1,
                start=timedelta(seconds=0),
                end=timedelta(seconds=2),
                text="state feedback",
            ),
            TranscriptSegment(
                index=2,
                start=timedelta(seconds=2),
                end=timedelta(seconds=4),
                text="state feedback again",
            ),
        ]
        events: list[tuple[str, float | None, str | None]] = []

        def capture_progress(*, stage: str, progress: float | None = None, detail: str | None = None) -> None:
            events.append((stage, progress, detail))

        with patch(
            "youtube_transcript_translator.translation.local_mt_backend.load_local_translation_bundle",
            return_value=("tokenizer", "model", "cpu"),
        ), patch(
            "youtube_transcript_translator.translation.local_mt_backend.translate_batch_with_bundle",
            return_value=["ZXQTERM0ZXQ", "ZXQTERM0ZXQ"],
        ):
            translated = backend.translate_segments(
                segments,
                batch_size=1,
                glossary={"state feedback": "상태 피드백"},
                progress_callback=capture_progress,
            )

        self.assertEqual(len(translated), 2)
        self.assertTrue(any(stage == "loading_model" for stage, _, _ in events))
        self.assertTrue(any(stage == "translating" for stage, _, _ in events))
        self.assertTrue(any(progress == 100.0 for stage, progress, _ in events if stage == "translating"))
