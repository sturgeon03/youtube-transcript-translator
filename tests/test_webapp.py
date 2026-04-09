from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from youtube_transcript_translator.ui.webapp.app import JobRequest, create_app


class WebAppTests(unittest.TestCase):
    def test_index_page_renders(self) -> None:
        client = TestClient(create_app())

        response = client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("YouTube URL", response.text)
        self.assertIn("local_mt", response.text)

    def test_create_job_returns_job_id(self) -> None:
        client = TestClient(create_app())

        with patch("youtube_transcript_translator.ui.webapp.app.run_job", return_value=None):
            response = client.post(
                "/api/jobs",
                json={
                    "url": "https://www.youtube.com/watch?v=uyyBT-MHhLE",
                    "translator": "local_mt",
                    "transcript_source": "auto",
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("job_id", payload)
        self.assertEqual(payload["status"], "queued")

    def test_job_snapshot_includes_progress_fields(self) -> None:
        app = create_app()
        job_store = app.state.job_store
        record = job_store.create(
            JobRequest(
                url="https://www.youtube.com/watch?v=uyyBT-MHhLE",
                translator="local_mt",
                transcript_source="auto",
            )
        )
        job_store.update_progress(
            record.id,
            stage="downloading_model",
            progress=37.5,
            detail="Downloading translation model",
        )

        snapshot = job_store.snapshot(record.id)

        self.assertEqual(snapshot["phase"], "downloading_model")
        self.assertEqual(snapshot["progress_percent"], 37.5)
        self.assertEqual(snapshot["progress_detail"], "Downloading translation model")


if __name__ == "__main__":
    unittest.main()
