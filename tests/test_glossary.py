from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from youtube_transcript_translator.glossary.loader import list_glossary_profiles, load_glossary
from youtube_transcript_translator.glossary.protector import prepare_text_for_translation, restore_placeholders


class GlossaryTests(unittest.TestCase):
    def test_direct_glossary_file_still_loads(self) -> None:
        with TemporaryDirectory() as temp_dir_raw:
            temp_dir = Path(temp_dir_raw)
            glossary_path = temp_dir / "custom.txt"
            glossary_path.write_text(
                "state feedback => STATE_FEEDBACK_KO\ncontroller.py => controller.py\n",
                encoding="utf-8",
            )

            glossary = load_glossary(glossary_path)

        self.assertEqual(glossary["state feedback"], "STATE_FEEDBACK_KO")
        self.assertEqual(glossary["controller.py"], "controller.py")

    def test_glossary_profile_loads_from_registry(self) -> None:
        with TemporaryDirectory() as temp_dir_raw:
            temp_dir = Path(temp_dir_raw)
            glossary_dir = temp_dir / "glossaries"
            glossary_dir.mkdir()
            glossary_path = glossary_dir / "sample.txt"
            glossary_path.write_text("trajectory optimization => TRAJECTORY_OPTIMIZATION_KO\n", encoding="utf-8")
            registry_path = glossary_dir / "registry.json"
            registry_path.write_text(
                json.dumps(
                    {
                        "profiles": {
                            "sample": {
                                "file": "sample.txt",
                                "label": "Sample glossary",
                                "description": "Sample profile",
                            }
                        }
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            glossary = load_glossary(
                glossary_profile="sample",
                registry_path=registry_path,
            )
            profiles = list_glossary_profiles(registry_path)

        self.assertEqual(glossary["trajectory optimization"], "TRAJECTORY_OPTIMIZATION_KO")
        self.assertEqual([profile.name for profile in profiles], ["sample"])
        self.assertEqual(profiles[0].label, "Sample glossary")

    def test_glossary_and_url_are_preserved(self) -> None:
        text = "Use state feedback at https://example.com in controller.py"
        glossary = {"state feedback": "STATE_FEEDBACK_KO"}

        masked, replacements = prepare_text_for_translation(text, glossary)

        self.assertNotIn("state feedback", masked.lower())
        self.assertNotIn("https://example.com", masked)
        restored = restore_placeholders(masked, replacements)
        self.assertIn("STATE_FEEDBACK_KO", restored)
        self.assertIn("https://example.com", restored)


if __name__ == "__main__":
    unittest.main()
