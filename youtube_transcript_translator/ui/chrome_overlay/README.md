# YouTube Korean Subtitle Overlay

This Chrome extension overlays packaged Korean subtitles on matching YouTube watch pages.

## Load the extension

1. Open `chrome://extensions` or `edge://extensions`.
2. Turn on `Developer mode`.
3. Choose `Load unpacked`.
4. Select this folder:
   - `youtube_transcript_translator/ui/chrome_overlay`

## Use it

1. Register a video id and subtitle file in `subtitles/index.json`.
2. Put the generated Korean `.srt` file in `subtitles/`.
3. Open the matching YouTube video.
4. The extension overlays the packaged Korean subtitles automatically.
5. Use the player buttons to adjust readability:
   - `KO`: hide or show the overlay
   - `S` / `M` / `L`: cycle subtitle size
   - `B` / `T`: move subtitles to bottom or top
   - `BG` / `HD` / `OL`: cycle soft background, solid background, or outline mode

## Example subtitle registration

```json
{
  "videos": {
    "VIDEO_ID": {
      "label": "Optional title",
      "file": "subtitles/VIDEO_ID.ko.grouped.srt"
    }
  }
}
```

## Register a generated subtitle file

From the repo root, copy a Korean SRT into the extension and update `index.json` with:

```powershell
python .\overlay_registry.py `
  --video-id "VIDEO_ID" `
  --subtitle ".\VIDEO_ID.ko.grouped.srt" `
  --label "Optional title"
```

This writes `youtube_transcript_translator\ui\chrome_overlay\subtitles\VIDEO_ID.ko.grouped.srt` and preserves existing registry entries.
