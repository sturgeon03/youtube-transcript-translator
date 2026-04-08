# YouTube Transcript Translator

Generate English transcripts from YouTube videos, translate them into Korean subtitles, and optionally load those subtitles into a Chrome extension overlay.

## What it does

- Pull English auto subtitles from YouTube when available
- Fall back to local `faster-whisper` transcription when subtitles are missing
- Optionally use OpenAI transcription, with chunked retries for long videos
- Translate grouped subtitle chunks into Korean
- Save English transcript files and Korean `.srt` output
- Package generated Korean subtitles into the included Chrome extension automatically

## Project structure

- `translate_youtube_subtitles.py`: thin CLI entrypoint
- `youtube_transcript_translator/`: main Python package
- `overlay_registry.py`: thin CLI entrypoint for extension registration
- `artifacts/`: local generated transcripts and subtitles
- `robotics_glossary.example.txt`: example glossary for technical terms
- `youtube_transcript_translator/ui/chrome_overlay/`: Chrome extension that overlays packaged Korean subtitles on YouTube

## Pipeline architecture

The repository is structured as a non-realtime batch pipeline:

1. `app/`: CLI entrypoint, config objects, and pipeline orchestration
2. `sources/`: YouTube downloads, local file loading, and raw source access
3. `transcript/`: transcript segment models and transcript providers
4. `normalize/`: cleanup, overlap handling, regrouping, and display-friendly splitting
5. `glossary/`: glossary loading and placeholder/token protection
6. `translation/`: replaceable translation backends and backend dispatch
7. `postprocess/`: restoration, consistency checks, and quality checks
8. `render/`: SRT/TXT/review/JSON artifact generation
9. `ui/`: downstream viewer layer only

## Target folder layout

```text
youtube_transcript_translator/
  app/
  sources/
  transcript/
  normalize/
  glossary/
  translation/
  postprocess/
  render/
  ui/chrome_overlay/
tests/
```

## Install

```powershell
python -m pip install -r requirements.txt
```

## Basic usage

Use YouTube auto subtitles when possible, then fall back to local transcription:

```powershell
python .\translate_youtube_subtitles.py `
  --url "https://www.youtube.com/watch?v=VIDEO_ID" `
  --transcript-source auto `
  --transcription-backend local `
  --translator google `
  --english-output ".\artifacts\VIDEO_ID.en.srt" `
  --english-text-output ".\artifacts\VIDEO_ID.en.txt" `
  --output ".\artifacts\VIDEO_ID.ko.grouped.srt"
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
  --output ".\artifacts\VIDEO_ID.ko.grouped.srt"
```

Force OpenAI speech-to-text when YouTube subtitles are unavailable:

```powershell
$env:OPENAI_API_KEY="YOUR_KEY_HERE"

python .\translate_youtube_subtitles.py `
  --url "https://www.youtube.com/watch?v=VIDEO_ID" `
  --transcript-source transcribe `
  --transcription-backend openai `
  --transcription-model gpt-4o-transcribe-diarize `
  --translator openai `
  --openai-model gpt-5.4-mini `
  --english-output ".\artifacts\VIDEO_ID.en.transcribed.srt" `
  --english-text-output ".\artifacts\VIDEO_ID.en.transcribed.txt" `
  --output ".\artifacts\VIDEO_ID.ko.grouped.srt"
```

Register the generated Korean subtitle in the bundled extension automatically:

```powershell
python .\translate_youtube_subtitles.py `
  --url "https://www.youtube.com/watch?v=VIDEO_ID" `
  --transcript-source auto `
  --transcription-backend local `
  --translator google `
  --extension-root ".\youtube_transcript_translator\ui\chrome_overlay" `
  --overlay-label "Optional title" `
  --output ".\artifacts\VIDEO_ID.ko.grouped.srt"
```

## Chrome extension

See `youtube_transcript_translator/ui/chrome_overlay/README.md` for loading and usage.
