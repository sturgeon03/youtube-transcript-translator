# YouTube Transcript Translator

Generate English transcripts from YouTube videos, translate them into Korean subtitles, and optionally load those subtitles into a Chrome extension overlay.

## What it does

- Pull English auto subtitles from YouTube when available
- Fall back to OpenAI speech-to-text when subtitles are missing
- Translate grouped subtitle chunks into Korean
- Save English transcript files and Korean `.srt` output
- Package generated Korean subtitles into the included Chrome extension

## Project structure

- `translate_youtube_subtitles.py`: transcript, translation, and subtitle generation pipeline
- `robotics_glossary.example.txt`: example glossary for technical terms
- `youtube_subtitle_overlay/`: Chrome extension that overlays packaged Korean subtitles on YouTube

## Install

```powershell
python -m pip install -r requirements.txt
```

## Basic usage

Use YouTube auto subtitles when possible:

```powershell
python .\translate_youtube_subtitles.py `
  --url "https://www.youtube.com/watch?v=VIDEO_ID" `
  --transcript-source auto `
  --translator google `
  --output ".\VIDEO_ID.ko.grouped.srt"
```

Use OpenAI translation with a glossary:

```powershell
$env:OPENAI_API_KEY="YOUR_KEY_HERE"

python .\translate_youtube_subtitles.py `
  --url "https://www.youtube.com/watch?v=VIDEO_ID" `
  --transcript-source auto `
  --translator openai `
  --openai-model gpt-5.4-mini `
  --glossary ".\robotics_glossary.example.txt" `
  --output ".\VIDEO_ID.ko.grouped.srt"
```

Force OpenAI speech-to-text when YouTube subtitles are unavailable:

```powershell
$env:OPENAI_API_KEY="YOUR_KEY_HERE"

python .\translate_youtube_subtitles.py `
  --url "https://www.youtube.com/watch?v=VIDEO_ID" `
  --transcript-source transcribe `
  --transcription-model gpt-4o-transcribe-diarize `
  --translator openai `
  --openai-model gpt-5.4-mini `
  --english-output ".\VIDEO_ID.en.transcribed.srt" `
  --english-text-output ".\VIDEO_ID.en.transcribed.txt" `
  --output ".\VIDEO_ID.ko.grouped.srt"
```

## Chrome extension

See `youtube_subtitle_overlay/README.md` for loading and usage.
