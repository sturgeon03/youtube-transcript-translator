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
            "youtube_transcript_translator.translation.local_mt_backend.translate_batch_local_model",
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
