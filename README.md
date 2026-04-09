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
- `glossaries/`: reusable glossary profiles and registry metadata
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
glossaries/
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
  --glossary-profile underactuated `
  --english-output ".\artifacts\VIDEO_ID.en.srt" `
  --english-text-output ".\artifacts\VIDEO_ID.en.txt" `
  --output ".\artifacts\VIDEO_ID.ko.grouped.srt"
```

List the built-in glossary profiles:

```powershell
python .\translate_youtube_subtitles.py --list-glossary-profiles
```

Use a direct glossary file instead of a named profile:

```powershell
python .\translate_youtube_subtitles.py `
  --url "https://www.youtube.com/watch?v=VIDEO_ID" `
  --transcript-source auto `
  --translator google `
  --glossary ".\robotics_glossary.example.txt" `
  --output ".\artifacts\VIDEO_ID.ko.grouped.srt"
```

Register the generated Korean subtitle in the bundled extension automatically:

```powershell
python .\translate_youtube_subtitles.py `
  --url "https://www.youtube.com/watch?v=VIDEO_ID" `
  --transcript-source auto `
  --transcription-backend local `
  --translator google `
  --glossary-profile underactuated `
  --extension-root ".\youtube_transcript_translator\ui\chrome_overlay" `
  --overlay-label "Optional title" `
  --output ".\artifacts\VIDEO_ID.ko.grouped.srt"
```

## Glossary profiles

The glossary subsystem supports two selection modes:

- `--glossary-profile NAME`: pick a named profile from `glossaries/registry.json`
- `--glossary PATH`: use a direct glossary file

Only one real profile is included right now:

- `underactuated`: a core terminology set for the MIT Underactuated Robotics notes

The Underactuated glossary was curated from the main course index and the note pages that repeatedly cover underactuated systems, feedback linearization, limit cycles, legged locomotion, dynamic programming, LQR, Lyapunov analysis, trajectory optimization, motion planning, robust and stochastic control, and policy search.

Primary source pages:

- [Underactuated Robotics index](https://underactuated.csail.mit.edu/index.html)
- [Acrobot and feedback linearization notes](https://underactuated.csail.mit.edu/acrobot.html)
- [Limit cycles notes](https://underactuated.csail.mit.edu/limit_cycles.html)
- [Humanoids notes](https://underactuated.csail.mit.edu/humanoids.html)
- [Dynamic programming notes](https://underactuated.csail.mit.edu/dp.html)
- [LQR notes](https://underactuated.csail.mit.edu/lqr.html)
- [Lyapunov notes](https://underactuated.csail.mit.edu/lyapunov.html)
- [Trajectory optimization notes](https://underactuated.csail.mit.edu/trajopt.html)
- [Motion planning notes](https://underactuated.csail.mit.edu/planning.html)
- [Robust control notes](https://underactuated.csail.mit.edu/robust.html)
- [Stochastic control notes](https://underactuated.csail.mit.edu/stochastic.html)
- [Policy search notes](https://underactuated.csail.mit.edu/policy_search.html)

To add a future glossary:

1. Add a new `.txt` or `.json` glossary file under `glossaries/`.
2. Add a new profile entry in `glossaries/registry.json`.
3. Run the CLI with `--glossary-profile YOUR_PROFILE_NAME`.

## Chrome extension

See `youtube_transcript_translator/ui/chrome_overlay/README.md` for loading and usage.
