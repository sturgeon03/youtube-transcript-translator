from __future__ import annotations

import unittest
from datetime import timedelta

from youtube_transcript_translator.normalize.regroup import build_display_friendly_subtitles, regroup_subtitles
from youtube_transcript_translator.transcript.models import TranscriptSegment


class NormalizeTests(unittest.TestCase):
    def test_regroup_splits_when_candidate_gets_too_long(self) -> None:
        subtitles = [
            TranscriptSegment(1, timedelta(seconds=0), timedelta(seconds=1), "This is a short introduction."),
            TranscriptSegment(2, timedelta(seconds=1), timedelta(seconds=2), "This sentence pushes the group over the limit."),
            TranscriptSegment(3, timedelta(seconds=4), timedelta(seconds=5), "A separate point."),
        ]

        grouped = regroup_subtitles(
            subtitles,
            max_group_seconds=3.0,
            max_group_words=8,
            max_gap_seconds=0.5,
        )

        self.assertGreaterEqual(len(grouped), 2)

    def test_display_builder_caps_at_two_lines(self) -> None:
        segment = TranscriptSegment(
            1,
            timedelta(seconds=0),
            timedelta(seconds=8),
            "dummy",
        )
        built = build_display_friendly_subtitles(
            segment,
            text=(
                "Today we will briefly cover robot control, optimization, "
                "and the main modeling assumptions behind the lecture."
            ),
            wrap_width=24,
            start_index=1,
        )

        self.assertGreaterEqual(len(built), 1)
        self.assertTrue(all(len([line for line in item.text.splitlines() if line.strip()]) <= 2 for item in built))
