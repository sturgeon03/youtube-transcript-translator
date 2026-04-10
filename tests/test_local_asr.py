from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from youtube_transcript_translator.transcript.local_asr import transcribe_audio_with_faster_whisper


class LocalAsrTests(unittest.TestCase):
    def test_local_asr_reports_progress(self) -> None:
        events: list[tuple[str, float | None, str | None]] = []

        def capture_progress(*, stage: str, progress: float | None = None, detail: str | None = None) -> None:
            events.append((stage, progress, detail))

        class FakeModel:
            def transcribe(self, *_args, **_kwargs):
                info = SimpleNamespace(duration=10.0)
                segments = iter(
                    [
                        SimpleNamespace(start=0.0, end=2.0, text="hello"),
                        SimpleNamespace(start=2.0, end=5.0, text="robotics"),
                        SimpleNamespace(start=5.0, end=10.0, text="control"),
                    ]
                )
                return segments, info

        with TemporaryDirectory() as temp_dir_raw:
            audio_path = Path(temp_dir_raw) / "sample.wav"
            audio_path.write_bytes(b"fake-audio")

            with patch("youtube_transcript_translator.transcript.local_asr._require_faster_whisper"), patch(
                "youtube_transcript_translator.transcript.local_asr._load_model",
                return_value=FakeModel(),
            ):
                subtitles = transcribe_audio_with_faster_whisper(
                    audio_path,
                    model_size="medium.en",
                    language="en",
                    device="cuda",
                    compute_type="float16",
                    progress_callback=capture_progress,
                )

        self.assertEqual(len(subtitles), 3)
        self.assertTrue(any(stage == "loading_asr_model" for stage, _, _ in events))
        self.assertTrue(any(stage == "transcribing_audio" for stage, _, _ in events))
        self.assertTrue(any(progress == 100.0 for stage, progress, _ in events if stage == "transcribing_audio"))


if __name__ == "__main__":
    unittest.main()
