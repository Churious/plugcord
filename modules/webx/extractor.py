"""Web page fetching and article content extraction utilities."""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import httpx
import trafilatura

from modules.webx.exceptions import ExtractionError

logger = logging.getLogger("plugcord.webx.extractor")

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "ko,en-US;q=0.9,en;q=0.8",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}

# Query parameters that should not affect page identity.
_TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_id",
    "fbclid",
    "gclid",
    "gclsrc",
    "dclid",
    "msclkid",
    "mc_cid",
    "mc_eid",
    "igshid",
    "spm",
    "ref",
    "ref_src",
    "source",
}

_SKIP_HOSTS = (
    "youtube.com",
    "youtu.be",
    "discord.com",
    "discord.gg",
    "twitter.com",
    "x.com",
    "instagram.com",
    "facebook.com",
)

_SKIP_EXTENSIONS = (
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".svg",
    ".ico",
    ".mp4",
    ".mov",
    ".mp3",
    ".wav",
    ".pdf",
    ".zip",
    ".tar",
    ".gz",
    ".exe",
    ".dmg",
)


def normalize_url(url: str) -> str | None:
    """Return a canonical form of a URL used as a de-duplication key.

    - keeps only http/https
    - lowercases scheme and host and strips a leading 'www.'
    - drops fragments and tracking query parameters
    - sorts remaining query parameters
    - strips a trailing slash from the path
    """
    if not url:
        return None
    raw = url.strip().strip("<>")
    try:
        parsed = urlparse(raw)
    except Exception:
        return None

    if parsed.scheme.lower() not in ("http", "https"):
        return None
    if not parsed.netloc:
        return None

    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    if netloc.endswith(":80") and scheme == "http":
        netloc = netloc[:-3]
    if netloc.endswith(":443") and scheme == "https":
        netloc = netloc[:-4]

    path = parsed.path.rstrip("/") or "/"

    query_pairs = [
        (k, v)
        for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        if k.lower() not in _TRACKING_PARAMS
    ]
    query = urlencode(sorted(query_pairs))

    return urlunparse((scheme, netloc, path, "", query, ""))


def is_processable_url(url: str) -> str | None:
    """Return the normalized URL if it is a supported article URL, else None."""
    normalized = normalize_url(url)
    if normalized is None:
        return None

    parsed = urlparse(normalized)
    host = parsed.netloc
    for skip in _SKIP_HOSTS:
        if host == skip or host.endswith(f".{skip}"):
            return None

    path = parsed.path.lower()
    if path.endswith(_SKIP_EXTENSIONS):
        return None

    return normalized


def _extract_content_sync(html: str, url: str) -> dict[str, Any]:
    """Blocking extraction of article text and metadata via trafilatura."""
    text = trafilatura.extract(
        html,
        url=url,
        include_comments=False,
        include_tables=True,
        favor_recall=True,
    ) or ""

    meta = trafilatura.extract_metadata(html, default_url=url)

    def _get(attr: str) -> str:
        if meta is None:
            return ""
        value = getattr(meta, attr, None)
        return str(value) if value else ""

    return {
        "title": _get("title"),
        "author": _get("author"),
        "site": _get("sitename"),
        "published": _get("date"),
        "description": _get("description"),
        "text": text,
    }


async def _fallback_fetch(url: str) -> str | None:
    """Fallback fetch using trafilatura's own downloader (handles some bot-blocked sites)."""
    try:
        result = await asyncio.to_thread(trafilatura.fetch_url, url)
        return result or None
    except Exception as exc:
        logger.debug(f"trafilatura fallback failed for {url}: {exc}")
        return None


async def fetch_article(url: str) -> dict[str, Any]:
    """Fetch a web page and extract its main article text and metadata."""
    normalized = is_processable_url(url)
    if normalized is None:
        raise ExtractionError("지원하지 않는 URL입니다.")

    html: str | None = None
    final_url = normalized
    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=httpx.Timeout(30.0),
            headers=_BROWSER_HEADERS,
        ) as client:
            response = await client.get(normalized)
            response.raise_for_status()
            html = response.text
            final_url = str(response.url)
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        logger.warning(f"httpx fetch failed for {normalized} (HTTP {status}); trying trafilatura fallback")
        html = await _fallback_fetch(normalized)
        if not html:
            raise ExtractionError(f"페이지 요청 실패 (HTTP {status})") from exc
    except httpx.HTTPError as exc:
        logger.warning(f"httpx fetch error for {normalized}: {exc}; trying trafilatura fallback")
        html = await _fallback_fetch(normalized)
        if not html:
            raise ExtractionError(f"페이지를 불러올 수 없습니다: {exc}") from exc

    if not html:
        raise ExtractionError("페이지를 불러올 수 없습니다.")

    try:
        content = await asyncio.to_thread(_extract_content_sync, html, final_url)
    except Exception as exc:
        logger.error(f"Content extraction failed for {final_url}: {exc}", exc_info=True)
        raise ExtractionError(f"본문 추출에 실패했습니다: {exc}") from exc

    text = content.get("text", "").strip()
    description = content.get("description", "").strip()
    if len(text) < 200 and not description:
        raise ExtractionError("본문을 추출할 수 없습니다. (자바스크립트 기반 페이지일 수 있습니다)")

    return {
        "url": url,
        "canonical_url": final_url or normalized,
        "url_key": normalized,
        "title": content.get("title", "") or "",
        "author": content.get("author", "") or "",
        "site": content.get("site", "") or "",
        "published": content.get("published", "") or "",
        "description": description,
        "text": text,
    }
