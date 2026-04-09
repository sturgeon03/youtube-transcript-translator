from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse


def extract_video_id(url: str) -> str:
    parsed = urlparse(url)
    if parsed.netloc.endswith("youtu.be"):
        return parsed.path.strip("/")
    if parsed.path == "/watch":
        query = parse_qs(parsed.query)
        if "v" in query and query["v"]:
            return query["v"][0]
    live_match = re.search(r"/live/([A-Za-z0-9_-]{11})", parsed.path)
    if live_match:
        return live_match.group(1)
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", url):
        return url
    raise ValueError(f"Could not extract a YouTube video ID from: {url}")


def format_subprocess_failure(result: subprocess.CompletedProcess[str]) -> str:
    parts = []
    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()
    if stdout:
        parts.append(stdout)
    if stderr:
        parts.append(stderr)
    return "\n".join(parts).strip()


def looks_like_missing_subtitles(message: str) -> bool:
    lowered = message.lower()
    patterns = (
        "no subtitles",
        "there are no subtitles",
        "requested subtitles are not available",
        "requested languages are not available",
        "has no automatic captions",
    )
    return any(pattern in lowered for pattern in patterns)


def find_existing_youtube_subtitle_file(video_id: str, target_dir: Path) -> Path | None:
    candidates = sorted(target_dir.glob(f"{video_id}*.en*.srt"))
    if candidates:
        return candidates[0]
    return None


def try_download_english_auto_subtitles(url: str, target_dir: Path) -> Path | None:
    video_id = extract_video_id(url)
    existing_path = find_existing_youtube_subtitle_file(video_id, target_dir)
    if existing_path is not None:
        return existing_path

    command = [
        sys.executable,
        "-m",
        "yt_dlp",
        "--no-playlist",
        "--skip-download",
        "--write-auto-sub",
        "--sub-lang",
        "en",
        "--sub-format",
        "srt",
        "-o",
        "%(id)s.%(ext)s",
        url,
    ]
    result = subprocess.run(command, cwd=target_dir, capture_output=True, text=True)
    output_path = find_existing_youtube_subtitle_file(video_id, target_dir)
    if output_path is not None:
        return output_path
    if result.returncode == 0:
        return None
    failure_output = format_subprocess_failure(result)
    if looks_like_missing_subtitles(failure_output):
        return None
    raise RuntimeError(
        "yt-dlp failed while downloading English auto subtitles.\n"
        f"URL: {url}\n"
        f"Details:\n{failure_output or f'Exit code {result.returncode}'}"
    )


def find_downloaded_audio_file(video_id: str, target_dir: Path) -> Path | None:
    candidates = sorted(target_dir.glob(f"{video_id}.audio.*"))
    if candidates:
        return candidates[0]
    return None


def download_audio_for_transcription(url: str, target_dir: Path) -> Path:
    video_id = extract_video_id(url)
    existing_path = find_downloaded_audio_file(video_id, target_dir)
    if existing_path is not None:
        return existing_path

    command = [
        sys.executable,
        "-m",
        "yt_dlp",
        "--no-playlist",
        "-f",
        "ba[ext=m4a]/ba[ext=webm]/bestaudio/best",
        "-S",
        "+abr,+size",
        "-o",
        "%(id)s.audio.%(ext)s",
        url,
    ]
    result = subprocess.run(command, cwd=target_dir, capture_output=True, text=True)
    if result.returncode != 0:
        failure_output = format_subprocess_failure(result)
        raise RuntimeError(
            "yt-dlp failed while downloading audio for transcription.\n"
            f"URL: {url}\n"
            f"Details:\n{failure_output or f'Exit code {result.returncode}'}"
        )
    output_path = find_downloaded_audio_file(video_id, target_dir)
    if output_path is None:
        raise FileNotFoundError(f"Expected audio file was not created for: {url}")
    return output_path
