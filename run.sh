#!/usr/bin/env bash
# Fetch new shorts, have Claude Code summarize them, then re-render shorts.xlsx.
#
#   ./run.sh                     # process new URLs in urls.txt
#   ./run.sh <url> [<url> ...]   # process these URLs too
#
# Env overrides:
#   COOKIES_BROWSER  browser whose Instagram login yt-dlp borrows (default: chrome; "" to disable)
#   CLAUDE_MODEL     model for summaries (default: opus)
cd "$(dirname "$0")" || exit 1

# launchd/cron start with a minimal PATH; make uv and claude findable.
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

COOKIES_BROWSER="${COOKIES_BROWSER-chrome}"
CLAUDE_MODEL="${CLAUDE_MODEL:-opus}"

echo "== 1/3 Fetch + transcribe"
fetch_args=(fetch "$@" -f urls.txt)
[ -n "$COOKIES_BROWSER" ] && fetch_args+=(--cookies-from-browser "$COOKIES_BROWSER")
uv run synth.py "${fetch_args[@]}" || echo "Some URLs failed (see above); continuing with the rest."

echo "== 2/3 Summarize with Claude Code"
if [ -n "$(uv run synth.py pending)" ]; then
  # Instructions for this task live in CLAUDE.md.
  claude -p "Summarize the pending shorts." \
    --model "$CLAUDE_MODEL" \
    --allowedTools "Read,Edit,Glob,Grep" --permission-mode dontAsk
else
  echo "Nothing pending."
fi

echo "== 3/3 Render"
uv run synth.py render
left=$(uv run synth.py pending | wc -l | tr -d ' ')
[ "$left" -gt 0 ] && echo "$left item(s) still unsummarized; they'll be retried next run."
exit 0
