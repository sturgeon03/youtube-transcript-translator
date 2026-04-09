# Glossary Profiles

This directory stores reusable glossary profiles for different lecture families.

## Current profiles

- `underactuated`: MIT Underactuated Robotics core glossary

## File layout

- `registry.json`: profile-to-file mapping plus short metadata
- `*.txt` or `*.json`: human-editable glossary files

## How to select a glossary

Use a named profile:

```powershell
python .\translate_youtube_subtitles.py `
  --url "https://www.youtube.com/watch?v=VIDEO_ID" `
  --glossary-profile underactuated
```

Use a direct glossary file:

```powershell
python .\translate_youtube_subtitles.py `
  --url "https://www.youtube.com/watch?v=VIDEO_ID" `
  --glossary ".\robotics_glossary.example.txt"
```

## How to add another glossary profile

1. Add a new glossary file in this directory.
2. Add a new profile entry in `registry.json`.
3. Use `--glossary-profile YOUR_PROFILE_NAME` from the CLI.

Keep entries focused on repeated subtitle-translation decisions, not generic vocabulary.
