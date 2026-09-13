"""Tests for the webx module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio

from core.bot import PlugcordBot
from core.database import Database
from modules.webx.cog import WebxCog
from modules.webx.extractor import is_processable_url, normalize_url
from modules.webx.models import ArticleAnalysis, Section, ToolInfo
from modules.webx.notion import _build_blocks, _build_properties


@pytest_asyncio.fixture
async def webx_cog(mock_bot: PlugcordBot, test_db: Database):
    """Provides a WebxCog instance wired to a temporary database."""
    mock_bot.database = test_db
    cog = WebxCog(mock_bot)
    await cog.cog_load()
    yield cog


# --------------------------------------------------------------------------- #
# URL normalization
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://www.example.com/post/", "https://example.com/post"),
        ("https://example.com/post?utm_source=x&id=1", "https://example.com/post?id=1"),
        ("https://example.com/post#section", "https://example.com/post"),
        ("HTTPS://WWW.Example.COM/Path/", "https://example.com/Path"),
        ("https://example.com/", "https://example.com/"),
        ("ftp://example.com", None),
        ("not a url", None),
        ("", None),
    ],
)
def test_normalize_url(url: str, expected: str | None):
    assert normalize_url(url) == expected


@pytest.mark.parametrize(
    "url,processable",
    [
        ("https://blog.example.com/article", True),
        ("https://www.youtube.com/watch?v=abc", False),
        ("https://youtu.be/abc", False),
        ("https://discord.gg/abc", False),
        ("https://example.com/image.png", False),
        ("https://example.com/doc.pdf", False),
        ("https://example.com/", True),
    ],
)
def test_is_processable_url(url: str, processable: bool):
    assert (is_processable_url(url) is not None) is processable


# --------------------------------------------------------------------------- #
# Guild settings CRUD
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_webx_settings_crud(webx_cog: WebxCog):
    guild_id = 987654321
    assert await webx_cog._get_settings(guild_id) is None

    await webx_cog._upsert_settings(guild_id, channel_id=111, notion_database_id="db-1", enabled=1)
    settings = await webx_cog._get_settings(guild_id)
    assert settings is not None
    assert settings["channel_id"] == 111
    assert settings["notion_database_id"] == "db-1"
    assert settings["enabled"] is True

    await webx_cog._upsert_settings(guild_id, channel_id=222)
    settings = await webx_cog._get_settings(guild_id)
    assert settings["channel_id"] == 222
    assert settings["notion_database_id"] == "db-1"


# --------------------------------------------------------------------------- #
# Duplicate detection
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_webx_page_duplicate(webx_cog: WebxCog):
    guild_id = 100
    url_key = "https://example.com/post"

    assert await webx_cog._get_page_record(guild_id, url_key) is None

    await webx_cog._insert_page(guild_id, url_key, "https://example.com/post?utm_source=x")
    record = await webx_cog._get_page_record(guild_id, url_key)
    assert record is not None
    assert record["status"] == "processing"

    await webx_cog._update_page_status(
        guild_id, url_key, "completed", notion_page_id="page-1", notion_page_url="https://notion.so/page-1"
    )
    record = await webx_cog._get_page_record(guild_id, url_key)
    assert record["status"] == "completed"
    assert record["notion_page_url"] == "https://notion.so/page-1"


# --------------------------------------------------------------------------- #
# Gemini structured validation (mock)
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_analyze_article_mock():
    fake_response = MagicMock()
    fake_response.parsed = ArticleAnalysis(
        title="Test Article",
        summary="A test summary.",
        key_points=["Point A", "Point B"],
        tools=[ToolInfo(name="pytest", description="Testing framework", url="https://pytest.org")],
        sections=[Section(heading="Intro", summary="Introduction section")],
        tags=["python", "testing"],
    )

    with patch("modules.webx.analyzer.genai.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = fake_response
        mock_client_cls.return_value = mock_client

        with patch.dict("os.environ", {"GEMINI_API_KEY": "fake-key"}):
            from modules.webx.analyzer import analyze_article
            result = await analyze_article({"title": "T", "text": "body"})

    assert result.title == "Test Article"
    assert result.tags == ["python", "testing"]
    assert result.tools[0].url == "https://pytest.org"


# --------------------------------------------------------------------------- #
# Notion block/property generation
# --------------------------------------------------------------------------- #

def test_build_blocks_structure():
    analysis = ArticleAnalysis(
        title="Demo",
        summary="Summary text",
        key_points=["Point 1"],
        tools=[ToolInfo(name="ToolA", description="Desc", url="https://a.com")],
        sections=[Section(heading="Sec", summary="Section summary")],
        tags=["tag1", "tag2"],
    )
    blocks = _build_blocks(analysis, "https://example.com/post")
    types_found = [b["type"] for b in blocks]
    assert "heading_1" in types_found
    assert "bulleted_list_item" in types_found
    assert any(
        b["type"] == "paragraph"
        and any(t.get("text", {}).get("link") for t in b["paragraph"]["rich_text"])
        for b in blocks
    )


def test_build_properties():
    analysis = ArticleAnalysis(
        title="Demo",
        summary="S",
        key_points=[],
        tools=[],
        sections=[],
        tags=["ai", "cloud"],
    )
    article = {
        "canonical_url": "https://example.com/post",
        "site": "Example",
        "author": "Jane",
        "published": "2024-01-15",
    }
    schema = {"Name": {"type": "title"}, "Web URL": {"type": "url"}}
    props = _build_properties(analysis, article, schema)
    assert "Name" in props
    assert props["Web URL"]["url"] == "https://example.com/post"
    assert props["Site"]["rich_text"][0]["text"]["content"] == "Example"
    assert props["Published"]["date"]["start"] == "2024-01-15"
    assert any(opt["name"] == "ai" for opt in props["Tags"]["multi_select"])


# --------------------------------------------------------------------------- #
# Permission checks
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_webx_setup_requires_admin(mock_bot: PlugcordBot):
    cog = WebxCog(mock_bot)
    cmd = cog.webx_setup
    checks = getattr(cmd, "checks", [])
    check_names = [getattr(c, "__name__", str(c)) for c in checks]
    assert any("require_admin" in name or "predicate" in name for name in check_names)
