"""Short-Form Content Synthesizer.

Turns Instagram Reels, TikToks and YouTube Shorts into rows in a spreadsheet:
creator, followers, engagement, caption, full transcript, and an AI summary.

Each video is stored as one JSON file in data/items/. The summary fields are
filled in by run.sh (via headless Claude Code), then `render` rebuilds the
spreadsheet from every item.

Usage:
    uv run synth.py fetch <url> [<url> ...] [--cookies-from-browser chrome]
    uv run synth.py fetch -f urls.txt
    uv run synth.py pending        # item files still missing a summary
    uv run synth.py render         # rebuild shorts.xlsx from data/items/
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tempfile
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

import yt_dlp
from faster_whisper import WhisperModel
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from rich.console import Console
from rich.table import Table

console = Console(stderr=True)

ROOT = Path(__file__).resolve().parent
ITEMS_DIR = ROOT / "data" / "items"

COLUMNS = [
    ("Processed", 18),
    ("Platform", 11),
    ("URL", 40),
    ("Handle", 20),
    ("Creator Name", 22),
    ("Followers", 12),
    ("Posted", 12),
    ("Duration (s)", 11),
    ("Views", 12),
    ("Likes", 12),
    ("Comments", 11),
    ("Caption", 50),
    ("Content Type", 16),
    ("Summary", 60),
    ("Key Points", 60),
    ("Topics", 30),
    ("Transcript", 80),
]


@dataclass
class ShortInfo:
    url: str
    source_url: str = ""
    video_id: str = ""
    processed: str = ""
    platform: str = ""
    handle: str = ""
    creator_name: str = ""
    followers: int | None = None
    posted: str = ""
    duration: float | None = None
    views: int | None = None
    likes: int | None = None
    comments: int | None = None
    caption: str = ""
    transcript: str = ""
    content_type: str = ""
    summary: str = ""
    key_points: list[str] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)


def load_items() -> list[tuple[Path, ShortInfo]]:
    items = []
    for path in sorted(ITEMS_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            console.print(f"[red]Skipping {path.name}: invalid JSON ({exc})[/]")
            continue
        known = {f for f in ShortInfo.__dataclass_fields__}
        items.append((path, ShortInfo(**{k: v for k, v in data.items() if k in known})))
    items.sort(key=lambda pair: pair[1].processed)
    return items


# ---------------------------------------------------------------- download


def _platform(info: dict) -> str:
    key = (info.get("extractor_key") or info.get("extractor") or "").lower()
    if "instagram" in key:
        return "Instagram"
    if "tiktok" in key:
        return "TikTok"
    if "youtube" in key:
        return "YouTube"
    return info.get("extractor_key") or "Unknown"


def _creator(info: dict, platform: str) -> tuple[str, str]:
    """Return (handle, display name). Each extractor names these fields differently."""
    if platform == "Instagram":
        handle = info.get("channel") or info.get("uploader_id") or ""
        name = info.get("uploader") or ""
    elif platform == "TikTok":
        handle = info.get("uploader") or ""
        name = info.get("channel") or ""
    else:
        handle = info.get("uploader_id") or info.get("channel_id") or ""
        name = info.get("channel") or info.get("uploader") or ""
    if handle and not handle.startswith("@") and not handle.isdigit():
        handle = "@" + handle
    return handle, name


def _instagram_followers(handle: str) -> int | None:
    """yt-dlp doesn't expose Instagram follower counts; try instaloader instead."""
    try:
        import instaloader

        loader = instaloader.Instaloader(quiet=True)
        return instaloader.Profile.from_username(loader.context, handle.lstrip("@")).followers
    except Exception as exc:  # rate limits / login walls are common
        console.print(f"  [yellow]Could not fetch Instagram follower count: {exc}[/]")
        return None


def _tiktok_followers(handle: str) -> int | None:
    """yt-dlp's TikTok video extractor omits follower counts; read it off the profile page."""
    try:
        req = urllib.request.Request(
            f"https://www.tiktok.com/{handle}",
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Safari/537.36"},
        )
        html = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", "ignore")
        match = re.search(r'"followerCount":(\d+)', html)
        return int(match.group(1)) if match else None
    except Exception as exc:
        console.print(f"  [yellow]Could not fetch TikTok follower count: {exc}[/]")
        return None


def download(url: str, workdir: Path, ydl_extra: dict) -> tuple[ShortInfo, Path | None]:
    opts = {
        "quiet": True,
        "noprogress": True,
        "no_warnings": True,
        "noplaylist": True,
        # Audio-only is enough for transcription; faster-whisper decodes it via PyAV,
        # so no ffmpeg post-processing is needed.
        "format": "bestaudio/best",
        "outtmpl": str(workdir / "%(id)s.%(ext)s"),
        **ydl_extra,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        media = Path(ydl.prepare_filename(info))

    platform = _platform(info)
    handle, name = _creator(info, platform)
    upload_date = info.get("upload_date") or ""
    short = ShortInfo(
        url=info.get("webpage_url") or url,
        source_url=url,
        video_id=str(info.get("id") or ""),
        processed=datetime.now().strftime("%Y-%m-%d %H:%M"),
        platform=platform,
        handle=handle,
        creator_name=name,
        followers=info.get("channel_follower_count"),
        posted=f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:]}" if len(upload_date) == 8 else "",
        duration=info.get("duration"),
        views=info.get("view_count"),
        likes=info.get("like_count"),
        comments=info.get("comment_count"),
        caption=(info.get("description") or info.get("title") or "").strip(),
    )
    if short.followers is None and platform == "Instagram" and handle:
        short.followers = _instagram_followers(handle)
    if short.followers is None and platform == "TikTok" and handle:
        short.followers = _tiktok_followers(handle)
    return short, media if media.exists() else None


# ------------------------------------------------------------- transcribe

_whisper: WhisperModel | None = None


def transcribe(media: Path, model_size: str) -> str:
    global _whisper
    if _whisper is None:
        console.print(f"  Loading Whisper model '{model_size}' (first run downloads it)...")
        _whisper = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, _ = _whisper.transcribe(str(media), vad_filter=True)
    return " ".join(seg.text.strip() for seg in segments).strip()


# ------------------------------------------------------------------ render


def _row(short: ShortInfo) -> list:
    return [
        short.processed,
        short.platform,
        short.url,
        short.handle,
        short.creator_name,
        short.followers,
        short.posted,
        round(short.duration) if short.duration else None,
        short.views,
        short.likes,
        short.comments,
        short.caption,
        short.content_type,
        short.summary,
        "\n".join(f"• {p}" for p in short.key_points),
        ", ".join(short.topics),
        short.transcript,
    ]


def render_xlsx(path: Path, shorts: list[ShortInfo]) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Shorts"
    ws.append([name for name, _ in COLUMNS])
    for i, (_, width) in enumerate(COLUMNS, start=1):
        cell = ws.cell(row=1, column=i)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1F2937")
        ws.column_dimensions[cell.column_letter].width = width
    ws.freeze_panes = "A2"

    for short in shorts:
        ws.append(_row(short))
        for cell in ws[ws.max_row]:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    ws.auto_filter.ref = ws.dimensions

    # Write then rename, so a file open in Excel/Numbers is never left half-written.
    tmp = path.with_name(f".{path.name}.tmp")
    wb.save(tmp)
    tmp.replace(path)


def _fmt(n: int | None) -> str:
    if n is None:
        return "—"
    for div, suffix in ((1_000_000_000, "B"), (1_000_000, "M"), (1_000, "K")):
        if n >= div:
            return f"{n / div:.1f}{suffix}"
    return str(n)


def print_table(shorts: list[ShortInfo]) -> None:
    table = Table(show_lines=True)
    for col in ("Platform", "Creator", "Followers", "Views", "Summary"):
        table.add_column(col, overflow="fold")
    for s in shorts:
        table.add_row(s.platform, f"{s.creator_name}\n{s.handle}", _fmt(s.followers), _fmt(s.views), s.summary or "[yellow]pending[/]")
    console.print(table)


# ---------------------------------------------------------------- commands


def cmd_fetch(args: argparse.Namespace) -> int:
    urls = list(args.urls)
    if args.file and args.file.exists():
        urls += [line.strip() for line in args.file.read_text().splitlines() if line.strip() and not line.startswith("#")]

    seen = {s.source_url for _, s in load_items()} | {s.url for _, s in load_items()}
    todo = [u for u in dict.fromkeys(urls) if u not in seen]
    if not todo:
        console.print("No new URLs to fetch.")
        return 0

    ydl_extra: dict = {}
    if args.cookies_from_browser:
        ydl_extra["cookiesfrombrowser"] = (args.cookies_from_browser,)
    if args.cookies:
        ydl_extra["cookiefile"] = str(args.cookies)

    ITEMS_DIR.mkdir(parents=True, exist_ok=True)
    failures = 0
    with tempfile.TemporaryDirectory() as tmp:
        for i, url in enumerate(todo, start=1):
            console.rule(f"[{i}/{len(todo)}] {url}")
            try:
                console.print("  Fetching video and creator info...")
                short, media = download(url, Path(tmp), ydl_extra)
            except yt_dlp.utils.DownloadError as exc:
                failures += 1
                console.print(f"  [red]Download failed:[/] {exc}")
                if "instagram" in url and not (args.cookies_from_browser or args.cookies):
                    console.print("  [yellow]Tip: Instagram usually needs --cookies-from-browser chrome[/]")
                continue

            if media:
                console.print("  Transcribing...")
                short.transcript = transcribe(media, args.whisper_model)
                media.unlink(missing_ok=True)

            out = ITEMS_DIR / f"{short.platform.lower()}_{short.video_id or hashlib.sha1(url.encode()).hexdigest()[:12]}.json"
            out.write_text(json.dumps(asdict(short), indent=2, ensure_ascii=False))
            console.print(f"  Saved {out.relative_to(ROOT)}")
    return 1 if failures else 0


def cmd_pending(args: argparse.Namespace) -> int:
    for path, short in load_items():
        if not short.summary:
            print(path)
    return 0


def cmd_render(args: argparse.Namespace) -> int:
    shorts = [s for _, s in load_items()]
    render_xlsx(args.output, shorts)
    print_table(shorts)
    console.print(f"\nRendered {len(shorts)} row(s) to [bold]{args.output}[/]")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    fetch = sub.add_parser("fetch", help="Download + transcribe new URLs into data/items/")
    fetch.add_argument("urls", nargs="*", help="Reel / TikTok / Short URLs")
    fetch.add_argument("-f", "--file", type=Path, help="Text file with one URL per line")
    fetch.add_argument("--cookies-from-browser", metavar="BROWSER", help="Use a logged-in browser's cookies (chrome, safari, firefox...). Usually needed for Instagram.")
    fetch.add_argument("--cookies", type=Path, help="Netscape-format cookies.txt file")
    fetch.add_argument("--whisper-model", default="small", help="tiny, base, small, medium, large-v3 (default: small)")
    fetch.set_defaults(func=cmd_fetch)

    pending = sub.add_parser("pending", help="Print item files that still need a summary")
    pending.set_defaults(func=cmd_pending)

    render = sub.add_parser("render", help="Rebuild the spreadsheet from data/items/")
    render.add_argument("-o", "--output", type=Path, default=ROOT / "shorts.xlsx", help="Spreadsheet path (default: shorts.xlsx)")
    render.set_defaults(func=cmd_render)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
