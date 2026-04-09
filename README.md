# YouTube Transcript Translator

Generate English transcripts from YouTube videos, translate them into Korean subtitles, and optionally load those subtitles into a Chrome extension overlay.

## Product direction

This repository is intentionally local-first and free-only.

- English transcript acquisition: YouTube English subtitles when available
- English transcript fallback: local `faster-whisper`
- Recommended translation path: local seq2seq machine translation
- Optional quick draft mode: Google translation
- Output style: non-realtime batch subtitle generation for long technical lectures

Paid API workflows are not part of the supported architecture.

## What it does

- Pull English auto subtitles from YouTube when available
- Fall back to local `faster-whisper` transcription when subtitles are missing
- Translate grouped subtitle chunks into Korean with a local glossary-aware backend
- Preserve glossary terms, URLs, filenames, and equation-like tokens through translation
- Run post-translation quality checks for glossary coverage, protected token restoration, and symbol preservation
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
6. `translation/`: replaceable free/local translation backends
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

Recommended translation model:

- default quality model: `facebook/nllb-200-distilled-600M`
- lighter local alternative: `Helsinki-NLP/opus-mt-en-ko`

The first `local_mt` run downloads the selected open-source model files once and then reuses the local cache.

## Local web UI

For a URL-first workflow, run the local web UI:

```powershell
python .\run_ui.py
```

Then open [http://127.0.0.1:8000](http://127.0.0.1:8000) if the browser does not open automatically.

To run the UI on a separate GPU PC and connect from a laptop browser on the same network:

```powershell
python .\run_ui.py --host 0.0.0.0 --port 8000 --no-browser
```

The server prints both the local URL and the detected LAN URL. Open the `http://GPU_PC_LAN_IP:8000` address from the laptop browser. If Windows prompts for firewall access, allow Python on the chosen network.

The UI currently supports:

- YouTube URL input
- transcript-source selection
- `local_mt` vs `google` translator selection
- glossary profile selection
- optional Chrome overlay registration
- job logs and result artifact links
- a built-in `Watch with Overlay` page for completed jobs, useful when the UI runs on a separate GPU PC

## Basic usage

Recommended local-only workflow:

```powershell
python .\translate_youtube_subtitles.py `
  --url "https://www.youtube.com/watch?v=VIDEO_ID" `
  --transcript-source auto `
  --translator local_mt `
  --local-translation-model "facebook/nllb-200-distilled-600M" `
  --glossary-profile underactuated `
  --english-output ".\artifacts\VIDEO_ID.en.srt" `
  --english-text-output ".\artifacts\VIDEO_ID.en.txt" `
  --review-output ".\artifacts\VIDEO_ID.review.md" `
  --output ".\artifacts\VIDEO_ID.ko.grouped.srt"
```

Use Google only as a quick draft baseline:

```powershell
python .\translate_youtube_subtitles.py `
  --url "https://www.youtube.com/watch?v=VIDEO_ID" `
  --transcript-source auto `
  --translator google `
  --glossary-profile underactuated `
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
  --translator local_mt `
  --glossary ".\robotics_glossary.example.txt" `
  --output ".\artifacts\VIDEO_ID.ko.grouped.srt"
```

Register the generated Korean subtitle in the bundled extension automatically:

```powershell
python .\translate_youtube_subtitles.py `
  --url "https://www.youtube.com/watch?v=VIDEO_ID" `
  --transcript-source auto `
  --translator local_mt `
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
