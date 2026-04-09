from __future__ import annotations

import uvicorn

from youtube_transcript_translator.ui.webapp.app import create_app


def main() -> None:
    app = create_app(open_browser=True)
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")


if __name__ == "__main__":
    main()
