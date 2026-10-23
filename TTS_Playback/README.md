# TTS_Playback — pre-rendered voice announcements

Every announcement the Moonraker integration can make, pre-rendered with the
`tts.azure_expressive` engine (en-US) and played once over
`media_player.office_speaker` on 2026-10-23. Clips are stored as mp3 so an
announcement can be assembled by **concatenating cached segments** instead of
calling the TTS engine every time.

## Files

- `*.mp3` — 125 audio clips, named semantically (`num_42.mp3`,
  `pfx_print_started.mp3`, `verdict_caution.mp3`, …).
- `manifest.json` — clip name → spoken text + filename (generated on-device).
- `announcements.json` — each announcement → ordered segment list.
- `phrases.json` — full source phrase list used for the build.
- `build/` — the scripts/AppDaemon app used to produce this package
  (regeneration only; not needed at runtime).

## Announcement structure

Three segment kinds appear in `announcements.json`:

- `"clip_name"` — static clip, played as-is.
- `{"value_map": "slot"}` — finite variable; look the value up in
  `values.slot` to get a clip name (e.g. progress marks → `num_25`,
  Klippy states → `klippy_shutdown`, Printcast score → `num_0`..`num_100`,
  verdicts → `verdict_*`).
- `{"dynamic": "slot"}` — unbounded text (filenames, factor details). No
  pre-render is possible; either generate TTS for just the variable, or skip
  it — the static segments still play.

### Example merges

- `print_started` (`Print started: {filename}`):
  `pfx_print_started.mp3` + TTS-or-skip(filename)
- `print_progress` at 75 % (`Print is 75 percent complete`):
  `pfx_progress.mp3` + `num_75.mp3` + `sfx_percent.mp3`
- `printer_fault` (`Printer fault: Klippy reports shutdown`):
  `pfx_printer_fault.mp3` + `klippy_shutdown.mp3`
- `printcast_forecast` (`Printcast 62 out of 100, verdict caution`):
  `pfx_printcast.mp3` + `num_62.mp3` + `sfx_out_of_100.mp3` + `verdict_caution.mp3`

## Playback

Any media player that accepts a playlist or sequential `media_player.play_media`
calls can merge the segments. For a single file, mp3s of the same codec
concatenate cleanly:

```bash
ffmpeg -i "concat:pfx_progress.mp3|num_75.mp3|sfx_percent.mp3" -c copy out.mp3
```

To reuse these on the HA host, copy the mp3s into a media folder
(e.g. `/config/media/tts_playback/`) and serve via `media-source://media_source/local/…`.

## Regenerating

The `build/` folder contains `tts_cache.py` (AppDaemon app) and
`phrases.json`. Drop both into an AppDaemon `apps/` dir, register
`tts_cache:` in `apps.yaml`, and it plays each phrase through the configured
speaker while copying the resulting `/config/tts/` cache entries out under
semantic names.
