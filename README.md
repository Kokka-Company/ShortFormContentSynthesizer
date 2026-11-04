# Short-Form Content Synthesizer

Turns Instagram Reels, TikToks and YouTube Shorts into rows in `shorts.xlsx`:

Processed · Platform · URL · Handle · Creator Name · Followers · Posted · Duration · Views · Likes · Comments · Caption · Content Type · **Summary** · **Key Points** · Topics · Transcript

## How it works

`./run.sh` runs three steps:

1. **Fetch + transcribe** (`synth.py fetch`): yt-dlp gets the creator info, stats and audio, and faster-whisper transcribes the audio on this Mac. Each video is saved as `data/items/<platform>_<id>.json`.
2. **Summarize** (Claude Code): `run.sh` runs `claude -p "Summarize the pending shorts."` in this folder. Claude Code reads the task instructions from `CLAUDE.md` and fills in `content_type`, `summary`, `key_points` and `topics` in every item that has no summary yet. It may only read and edit files; anything else is denied.
3. **Render** (`synth.py render`): rebuilds `shorts.xlsx` from every item.

URLs you've already processed are skipped. An item Claude didn't finish is picked up again on the next run.

You can also do step 2 by hand: `cd` into this folder, run `claude`, and type "summarize the pending shorts". Then run `uv run synth.py render`.

## Setup (Mac mini)

```bash
uv sync                 # Python deps into .venv
claude                  # log in to Claude Code once, then /exit
```

For Instagram, stay logged in to Instagram in Chrome on the Mac mini. yt-dlp borrows that login.

## Usage

```bash
./run.sh                                   # process new URLs in urls.txt
./run.sh https://www.instagram.com/reel/XXXX/ https://www.tiktok.com/@u/video/123
```

| Env var | Default | Purpose |
|---|---|---|
| `COOKIES_BROWSER` | `chrome` | Browser whose login yt-dlp uses (`safari`, `firefox`, `brave`…). Set to `""` to disable |
| `CLAUDE_MODEL` | `opus` | Model for summaries |

To change what the summary contains, edit the task section of `CLAUDE.md`. If you add fields, also add them to `ShortInfo` and `COLUMNS` in `synth.py`.

## Notes

- **Instagram**: Instagram can flag scraping, so consider a secondary account.
- **Follower counts**: YouTube comes from yt-dlp. TikTok is read from the profile page. Instagram uses `instaloader`, which may be rate-limited; the cell stays blank if that fails.
- **Running from launchd/cron**: a scheduled job may not be able to reach the keychain where your Claude Code login lives. Run `claude setup-token` once and export the token as `CLAUDE_CODE_OAUTH_TOKEN` in the job's environment.
- `shorts.xlsx` is rebuilt on every run. Keep your own notes in a separate sheet or file, because edits to it get overwritten.

## License

Copyright (C) 2026 Kokka & Company

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the [GNU General Public License](LICENSE) for more details.
