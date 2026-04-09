from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from youtube_transcript_translator.app.config import OutputConfig, PipelineConfig, TranscriptConfig, TranslationConfig
from youtube_transcript_translator.app.pipeline import run_pipeline
from youtube_transcript_translator.transcript.models import TranscriptSegment


class TranslationPipelineTests(unittest.TestCase):
    def test_pipeline_renders_outputs_with_mocked_translation(self) -> None:
        with TemporaryDirectory() as temp_dir_raw:
            temp_dir = Path(temp_dir_raw)
            input_path = temp_dir / "sample.en.srt"
            input_path.write_text(
                "1\n00:00:00,000 --> 00:00:02,000\nHello robotics class.\n",
                encoding="utf-8-sig",
            )
            output_path = temp_dir / "sample.ko.grouped.srt"
            review_path = temp_dir / "sample.review.md"

            def fake_translate(segments, *, config, glossary, progress_callback=None):
                return [
                    TranscriptSegment(
                        index=1,
                        start=segments[0].start,
                        end=segments[0].end,
                        text="translated robotics class",
                        source="test",
                    )
                ]

            with patch("youtube_transcript_translator.app.pipeline.translate_segments", side_effect=fake_translate):
                result = run_pipeline(
                    PipelineConfig(
                        url=None,
                        input_path=input_path,
                        max_group_seconds=7.0,
                        max_group_words=18,
                        max_gap_seconds=0.75,
                        transcript=TranscriptConfig(
                            source_mode="auto",
                            language="en",
                            local_model="small.en",
                            local_device="cpu",
                            local_compute_type="int8",
                        ),
                        translation=TranslationConfig(
                            backend="local_mt",
                            batch_size=8,
                            wrap_width=24,
                            glossary_path=None,
                            glossary_profile=None,
                            glossary_registry_path=None,
                            local_model="facebook/nllb-200-distilled-600M",
                            local_device="cpu",
                            local_source_lang="eng_Latn",
                            local_target_lang="kor_Hang",
                            local_max_input_length=512,
                            local_max_new_tokens=256,
                            local_num_beams=4,
                        ),
                        output=OutputConfig(
                            output_path=output_path,
                            english_output=None,
                            english_text_output=None,
                            extension_root=None,
                            video_id=None,
                            overlay_label=None,
                            review_output=review_path,
                        ),
                    ),
                    target_dir=temp_dir,
                )

            self.assertTrue(result.korean_output_path.exists())
            self.assertTrue(review_path.exists())
            self.assertEqual(result.quality_issue_count, 0)
            self.assertIn("translated robotics", output_path.read_text(encoding="utf-8-sig"))
            self.assertIn("translated robotics class", review_path.read_text(encoding="utf-8-sig"))
            self.assertIn("Hello robotics class.", review_path.read_text(encoding="utf-8-sig"))


if __name__ == "__main__":
    unittest.main()
