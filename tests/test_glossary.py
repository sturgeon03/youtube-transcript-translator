from __future__ import annotations

import unittest

from youtube_transcript_translator.glossary.protector import prepare_text_for_translation, restore_placeholders


class GlossaryProtectionTests(unittest.TestCase):
    def test_glossary_and_url_are_preserved(self) -> None:
        text = "Use state feedback at https://example.com in controller.py"
        glossary = {"state feedback": "상태 피드백"}

        masked, replacements = prepare_text_for_translation(text, glossary)

        self.assertNotIn("state feedback", masked.lower())
        self.assertNotIn("https://example.com", masked)
        restored = restore_placeholders(masked, replacements)
        self.assertIn("상태 피드백", restored)
        self.assertIn("https://example.com", restored)


if __name__ == "__main__":
    unittest.main()
