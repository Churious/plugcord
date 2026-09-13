"""Notion integration for creating structured pages from web article analysis."""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from typing import Any

import aiohttp

from modules.webx.exceptions import NotionError
from modules.webx.models import ArticleAnalysis

logger = logging.getLogger("plugcord.webx.notion")

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
    try:
        db = await _request("GET", f"/databases/{database_id}")
    except NotionError:
        raise
    except Exception as exc:
        raise NotionError(f"Failed to fetch database schema: {exc}") from exc
    return db.get("properties", {})


def _find_title_property_name(properties: dict[str, Any]) -> str:
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
        "Web URL": {"url": {}},
        "Site": {"rich_text": {}},
        "Author": {"rich_text": {}},
        "Published": {"date": {}},
        "Tags": {"multi_select": {"options": []}},
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

    return await _get_database_schema(database_id)


def _text(content: str) -> dict[str, Any]:
    return {"type": "text", "text": {"content": content}}


def _build_blocks(analysis: ArticleAnalysis, canonical_url: str) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = [
        {"object": "block", "type": "heading_1", "heading_1": {"rich_text": [_text("요약")]}},
        {"object": "block", "type": "paragraph", "paragraph": {"rich_text": [_text(analysis.summary)]}},
        {"object": "block", "type": "heading_1", "heading_1": {"rich_text": [_text("핵심 내용")]}},
    ]
    for point in analysis.key_points:
        blocks.append({
            "object": "block",
            "type": "bulleted_list_item",
            "bulleted_list_item": {"rich_text": [_text(point)]},
        })

    blocks.append({
        "object": "block",
        "type": "heading_1",
        "heading_1": {"rich_text": [_text("도구 및 리소스")]},
    })
    if analysis.tools:
        for tool in analysis.tools:
            blocks.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {"rich_text": [_text(tool.name)]},
            })
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": [_text(f"설명: {tool.description}")]},
            })
            if tool.url:
                blocks.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [
                            _text("URL: "),
                            {"type": "text", "text": {"content": tool.url, "link": {"url": tool.url}}},
                        ]
                    },
                })
    else:
        blocks.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {"rich_text": [_text("없음")]},
        })

    if analysis.sections:
        blocks.append({
            "object": "block",
            "type": "heading_1",
            "heading_1": {"rich_text": [_text("섹션별 정리")]},
        })
        for section in analysis.sections:
            blocks.append({
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {"rich_text": [_text(f"{section.heading} — {section.summary}")]},
            })

    if analysis.tags:
        blocks.append({
            "object": "block",
            "type": "heading_1",
            "heading_1": {"rich_text": [_text("태그")]},
        })
        blocks.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {"rich_text": [_text(", ".join(analysis.tags))]},
        })

    blocks.append({
        "object": "block",
        "type": "heading_1",
        "heading_1": {"rich_text": [_text("출처")]},
    })
    blocks.append({
        "object": "block",
        "type": "paragraph",
        "paragraph": {
            "rich_text": [
                _text("URL: "),
                {"type": "text", "text": {"content": canonical_url, "link": {"url": canonical_url}}},
            ]
        },
    })

    return blocks


def _build_properties(
    analysis: ArticleAnalysis,
    article: dict[str, Any],
    schema: dict[str, Any],
) -> dict[str, Any]:
    published = article.get("published", "")
    if not published:
        published = None

    title_name = _find_title_property_name(schema)

    props: dict[str, Any] = {
        title_name: {"title": [_text(analysis.title)]},
        "Web URL": {"url": article.get("canonical_url", "")},
        "Site": {"rich_text": [_text(article.get("site", ""))]},
        "Author": {"rich_text": [_text(article.get("author", ""))]},
    }
    if published:
        props["Published"] = {"date": {"start": published}}
    if analysis.tags:
        props["Tags"] = {"multi_select": [{"name": tag} for tag in analysis.tags]}
    props["Processed At"] = {"date": {"start": datetime.now(UTC).isoformat()}}
    return props


async def create_page(
    database_id: str,
    analysis: ArticleAnalysis,
    article: dict[str, Any],
) -> tuple[str, str]:
    """Create a Notion page and return (page_id, page_url)."""
    schema = await ensure_database_properties(database_id)

    payload = {
        "parent": {"database_id": database_id},
        "properties": _build_properties(analysis, article, schema),
        "children": _build_blocks(analysis, article.get("canonical_url", "")),
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
        page_url = f"https://www.notion.so/{page_id.replace('-', '')}"
    return page_id, page_url
