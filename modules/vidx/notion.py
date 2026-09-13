"""Notion integration for creating structured pages from video analysis."""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import UTC, datetime
from typing import Any

import aiohttp

from modules.vidx.exceptions import NotionError
from modules.vidx.models import TimelineItem, ToolInfo, VideoAnalysis

logger = logging.getLogger("plugcord.vidx.notion")

_NOTION_VERSION = "2022-06-28"
_NOTION_BASE = "https://api.notion.com/v1"


def _headers() -> dict[str, str]:
    token = os.environ.get("NOTION_TOKEN", "").strip()
    if not token:
        raise NotionError("NOTION_TOKEN environment variable is not set.")
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": _NOTION_VERSION,
        "Content-Type": "application/json",
    }


async def _request(
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    url = f"{_NOTION_BASE}{path}"
    async with aiohttp.ClientSession(headers=_headers()) as session:
        async with session.request(method, url, json=payload) as resp:
            body = await resp.json()
            if resp.status >= 400:
                logger.error(f"Notion API error {resp.status}: {body}")
                msg = body.get("message", "Unknown Notion API error")
                raise NotionError(f"Notion API {resp.status}: {msg}")
            return body


async def _get_database_schema(database_id: str) -> dict[str, Any]:
    """Fetch database schema and return property definitions."""
    try:
        db = await _request("GET", f"/databases/{database_id}")
    except NotionError:
        raise
    except Exception as exc:
        raise NotionError(f"Failed to fetch database schema: {exc}") from exc
    return db.get("properties", {})


def _find_title_property_name(properties: dict[str, Any]) -> str:
    """Find the database property whose type is 'title'."""
    for name, prop in properties.items():
        if prop.get("type") == "title":
            return name
    raise NotionError(
        "Notion database has no 'title' property. "
        "Please ensure the database has a title column (usually called 'Name')."
    )


async def ensure_database_properties(database_id: str) -> dict[str, Any]:
    """Check database schema, safely add missing properties, return schema."""
    existing = await _get_database_schema(database_id)

    desired: dict[str, dict[str, Any]] = {
        "Video URL": {"url": {}},
        "Video ID": {"rich_text": {}},
        "Channel": {"rich_text": {}},
        "Published": {"date": {}},
        "Tools": {"multi_select": {"options": []}},
        "Processed At": {"date": {}},
    }

    missing = {k: v for k, v in desired.items() if k not in existing}
    if not missing:
        return existing

    try:
        await _request("PATCH", f"/databases/{database_id}", {"properties": missing})
        logger.info(f"Added missing properties to Notion database {database_id}: {list(missing.keys())}")
    except Exception as exc:
        logger.warning(f"Could not add missing properties to Notion database: {exc}")
        raise NotionError(
            f"Notion database is missing required properties: {list(missing.keys())}. "
            "Please add them manually or ensure the integration has edit permissions."
        ) from exc

    # Re-fetch to get updated schema
    return await _get_database_schema(database_id)


def _build_blocks(analysis: VideoAnalysis, canonical_url: str) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = [
        {"object": "block", "type": "heading_1", "heading_1": {"rich_text": [{"type": "text", "text": {"content": "요약"}}]}},
        {"object": "block", "type": "paragraph", "paragraph": {"rich_text": [{"type": "text", "text": {"content": analysis.summary}}]}},
        {"object": "block", "type": "heading_1", "heading_1": {"rich_text": [{"type": "text", "text": {"content": "핵심 내용"}}]}},
    ]
    for point in analysis.key_points:
        blocks.append({
            "object": "block",
            "type": "bulleted_list_item",
            "bulleted_list_item": {"rich_text": [{"type": "text", "text": {"content": point}}]},
        })

    blocks.append({
        "object": "block",
        "type": "heading_1",
        "heading_1": {"rich_text": [{"type": "text", "text": {"content": "도구 및 리소스"}}]},
    })
    for tool in analysis.tools:
        blocks.append({
            "object": "block",
            "type": "heading_2",
            "heading_2": {"rich_text": [{"type": "text", "text": {"content": tool.name}}]},
        })
        blocks.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {"rich_text": [{"type": "text", "text": {"content": f"설명: {tool.description}"}}]},
        })
        if tool.url:
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {"type": "text", "text": {"content": "URL: "}},
                        {"type": "text", "text": {"content": tool.url, "link": {"url": tool.url}}},
                    ]
                },
            })
        if tool.timestamp:
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": [{"type": "text", "text": {"content": f"타임스탬프: {tool.timestamp}"}}]},
            })

    blocks.append({
        "object": "block",
        "type": "heading_1",
        "heading_1": {"rich_text": [{"type": "text", "text": {"content": "타임라인"}}]},
    })
    for item in analysis.timeline:
        blocks.append({
            "object": "block",
            "type": "bulleted_list_item",
            "bulleted_list_item": {"rich_text": [{"type": "text", "text": {"content": f"{item.timestamp} — {item.title}"}}]},
        })

    blocks.append({
        "object": "block",
        "type": "heading_1",
        "heading_1": {"rich_text": [{"type": "text", "text": {"content": "출처"}}]},
    })
    blocks.append({
        "object": "block",
        "type": "paragraph",
        "paragraph": {
            "rich_text": [
                {"type": "text", "text": {"content": "YouTube: "}},
                {"type": "text", "text": {"content": canonical_url, "link": {"url": canonical_url}}},
            ]
        },
    })

    return blocks


def _build_properties(
    analysis: VideoAnalysis,
    metadata: dict[str, Any],
    schema: dict[str, Any],
) -> dict[str, Any]:
    published = metadata.get("published", "")
    # Convert yt-dlp upload_date (YYYYMMDD) to ISO date if possible
    if isinstance(published, str) and len(published) == 8:
        published = f"{published[:4]}-{published[4:6]}-{published[6:]}"
    elif not published:
        published = None

    tool_names = [t.name for t in analysis.tools]
    multi_select = [{"name": name} for name in tool_names]

    title_name = _find_title_property_name(schema)

    props: dict[str, Any] = {
        title_name: {"title": [{"type": "text", "text": {"content": analysis.title}}]},
        "Video URL": {"url": metadata.get("canonical_url", "")},
        "Video ID": {"rich_text": [{"type": "text", "text": {"content": metadata.get("video_id", "")}}]},
        "Channel": {"rich_text": [{"type": "text", "text": {"content": metadata.get("channel", "")}}]},
    }
    if published:
        props["Published"] = {"date": {"start": published}}
    if multi_select:
        props["Tools"] = {"multi_select": multi_select}
    props["Processed At"] = {"date": {"start": datetime.now(UTC).isoformat()}}
    return props


async def create_page(
    database_id: str,
    analysis: VideoAnalysis,
    metadata: dict[str, Any],
) -> tuple[str, str]:
    """Create a Notion page and return (page_id, page_url)."""
    schema = await ensure_database_properties(database_id)

    payload = {
        "parent": {"database_id": database_id},
        "properties": _build_properties(analysis, metadata, schema),
        "children": _build_blocks(analysis, metadata.get("canonical_url", "")),
    }

    try:
        result = await _request("POST", "/pages", payload)
    except Exception as exc:
        raise NotionError(f"Failed to create Notion page: {exc}") from exc

    page_id = result.get("id", "")
    page_url = result.get("url", "")
    if not page_id:
        raise NotionError("Notion response did not contain a page ID.")
    if not page_url:
        # Fallback to canonical URL construction if API omits it
        page_url = f"https://www.notion.so/{page_id.replace('-', '')}"
    return page_id, page_url
