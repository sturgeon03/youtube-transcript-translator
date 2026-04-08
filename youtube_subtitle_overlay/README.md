# YouTube Korean Subtitle Overlay

This Chrome extension overlays packaged Korean subtitles on matching YouTube watch pages.

## Load the extension

1. Open `chrome://extensions` or `edge://extensions`.
2. Turn on `Developer mode`.
3. Choose `Load unpacked`.
4. Select this folder:
   - `C:\Users\sym89\Desktop\통번역\youtube_subtitle_overlay`

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
