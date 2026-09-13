"""YouTube metadata and transcript extraction utilities.

Strategy:
1. Try youtube-transcript-api for subtitles (no API key, fast).
2. Fall back to yt-dlp for metadata only (no subtitle download).
3. Return metadata + transcript for Gemini analysis.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from modules.vidx.exceptions import VideoExtractionError

logger = logging.getLogger("plugcord.vidx.youtube")

# Patterns to extract an 11-character YouTube video ID
_YOUTUBE_PATTERNS = [
    re.compile(r"youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})"),
    re.compile(r"youtu\.be/([a-zA-Z0-9_-]{11})"),
    re.compile(r"youtube\.com/shorts/([a-zA-Z0-9_-]{11})"),
    re.compile(r"youtube\.com/embed/([a-zA-Z0-9_-]{11})"),
]


def extract_video_id(url: str) -> str | None:
    """Extract the 11-character video ID from a YouTube URL."""
    for pattern in _YOUTUBE_PATTERNS:
        match = pattern.search(url)
        if match:
            return match.group(1)
    return None


def normalize_video_id(url: str) -> str | None:
    """Alias for extract_video_id."""
    return extract_video_id(url)


def _fetch_transcript_sync(video_id: str) -> str:
    """Blocking call to youtube-transcript-api."""
    from youtube_transcript_api import YouTubeTranscriptApi

    # Try English first, then Korean, then whatever is available
    for lang in (["en", "ko"], ["en"], ["ko"], None):
        try:
            if lang:
                transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=lang)
            else:
                transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
            return " ".join(item["text"] for item in transcript_list)
        except Exception:
            continue
    return ""


def _fetch_metadata_ytdlp(video_id: str) -> dict[str, Any]:
    """Blocking call to yt-dlp for metadata only (no subtitle download)."""
    import yt_dlp

    ydl_opts: dict[str, Any] = {
        "quiet": True,
        "skip_download": True,
        "writesubtitles": False,
        "writeautomaticsub": False,
    }
    url = f"https://www.youtube.com/watch?v={video_id}"
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    if info is None:
        raise VideoExtractionError(f"yt-dlp returned no info for video {video_id}")

    return {
        "video_id": video_id,
        "title": info.get("title") or "",
        "channel": info.get("channel") or info.get("uploader") or "",
        "description": info.get("description") or "",
        "duration": info.get("duration") or 0,
        "published": info.get("upload_date") or "",
        "thumbnail": info.get("thumbnail") or "",
        "canonical_url": info.get("webpage_url") or f"https://www.youtube.com/watch?v={video_id}",
    }


async def fetch_video_data(video_id: str) -> dict[str, Any]:
    """Fetch YouTube metadata and transcript asynchronously.

    Returns metadata dict with at minimum:
        video_id, title, channel, description, duration, published,
        thumbnail, canonical_url, transcript
    """
    # 1. Fetch metadata via yt-dlp (lightweight, no download)
    try:
        metadata = await asyncio.to_thread(_fetch_metadata_ytdlp, video_id)
    except Exception as exc:
        logger.error(f"yt-dlp metadata fetch failed for {video_id}: {exc}")
        # Bare minimum fallback
        metadata = {
            "video_id": video_id,
            "title": "",
            "channel": "",
            "description": "",
            "duration": 0,
            "published": "",
            "thumbnail": "",
            "canonical_url": f"https://www.youtube.com/watch?v={video_id}",
        }

    # 2. Try transcript via youtube-transcript-api
    transcript = ""
    try:
        transcript = await asyncio.to_thread(_fetch_transcript_sync, video_id)
        if transcript:
            logger.info(f"Loaded transcript for {video_id} ({len(transcript)} chars)")
    except Exception as exc:
        logger.warning(f"Transcript fetch failed for {video_id}: {exc}")

    metadata["transcript"] = transcript
    return metadata
