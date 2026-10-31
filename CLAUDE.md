# Short-Form Content Synthesizer

Turns Instagram Reels, TikToks and YouTube Shorts into rows in `shorts.xlsx`.

- `synth.py fetch` downloads each URL in `urls.txt`, transcribes it, and writes `data/items/<platform>_<id>.json`.
- **You** fill in the summary fields of those JSON files (see below).
- `synth.py render` rebuilds `shorts.xlsx` from every item. Never edit `shorts.xlsx` directly.
- `run.sh` runs all three steps.

## Task: summarize the pending shorts

When asked to summarize pending shorts (or anything similar):

1. Find every file in `data/items/` whose `"summary"` is `""`. Those are pending; leave the rest alone.
2. For each one, read `platform`, `creator_name`, `handle`, `caption` and `transcript`, then fill in:
   - `content_type`: a short label such as tutorial, product review, opinion, news, storytelling, comedy, promo/ad, motivational.
   - `summary`: 2-4 plain sentences on what the video says and its main takeaway.
   - `key_points`: list of strings with the concrete information a viewer learns (facts, steps, numbers, tips, claims, offers), one self-contained sentence each. Usually 3-6, fewer if the video is thin.
   - `topics`: list of 2-6 short topic tags.
3. Edit only those four fields. Don't change other fields, and keep the file valid JSON.

The transcript is automatic speech recognition: it can contain errors, or be empty for music-only videos. Rely on the caption when the transcript is thin, and don't invent details that neither contains.

You don't need to run anything: `run.sh` checks the files and renders the spreadsheet after you finish. When done, reply with one line per file: the file name and its content type.
