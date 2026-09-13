"""Tests for the vidx module."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
import pytest_asyncio

from core.bot import PlugcordBot
from core.database import Database
from modules.vidx.cog import VidxCog
from modules.vidx.models import TimelineItem, ToolInfo, VideoAnalysis
from modules.vidx.notion import _build_blocks, _build_properties
from modules.vidx.youtube import extract_video_id, normalize_video_id


@pytest_asyncio.fixture
async def vidx_cog(mock_bot: PlugcordBot, test_db: Database):
    """Provides a VidxCog instance wired to a temporary database."""
    mock_bot.database = test_db
    cog = VidxCog(mock_bot)
    await cog.cog_load()
    yield cog
    # No explicit teardown needed; test_db handles cleanup


# --------------------------------------------------------------------------- #
# URL parsing
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/embed/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://example.com", None),
        ("", None),
    ],
)
def test_extract_video_id(url: str, expected: str | None):
    assert extract_video_id(url) == expected
    assert normalize_video_id(url) == expected


# --------------------------------------------------------------------------- #
# Guild settings CRUD
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_vidx_settings_crud(vidx_cog: VidxCog):
    guild_id = 123456789
    # Initially empty
    assert await vidx_cog._get_settings(guild_id) is None

    # Insert
    await vidx_cog._upsert_settings(guild_id, channel_id=111, notion_database_id="db-1", enabled=1)
    settings = await vidx_cog._get_settings(guild_id)
    assert settings is not None
    assert settings["channel_id"] == 111
    assert settings["notion_database_id"] == "db-1"
    assert settings["enabled"] is True

    # Update
    await vidx_cog._upsert_settings(guild_id, channel_id=222)
    settings = await vidx_cog._get_settings(guild_id)
    assert settings["channel_id"] == 222
    assert settings["notion_database_id"] == "db-1"  # unchanged


# --------------------------------------------------------------------------- #
# Duplicate detection
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_vidx_video_duplicate(vidx_cog: VidxCog):
    guild_id = 100
    video_id = "ABC12345678"

    # No record initially
    assert await vidx_cog._get_video_record(guild_id, video_id) is None

    # Insert processing
    await vidx_cog._insert_video(guild_id, video_id, "https://youtu.be/ABC12345678")
    record = await vidx_cog._get_video_record(guild_id, video_id)
    assert record is not None
    assert record["status"] == "processing"

    # Update to completed
    await vidx_cog._update_video_status(guild_id, video_id, "completed", notion_page_id="page-1")
    record = await vidx_cog._get_video_record(guild_id, video_id)
    assert record["status"] == "completed"
    assert record["notion_page_id"] == "page-1"


# --------------------------------------------------------------------------- #
# Gemini structured validation (mock)
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_analyze_video_mock():
    fake_response = MagicMock()
    fake_response.parsed = VideoAnalysis(
        title="Test Video",
        summary="A test summary.",
        key_points=["Point A", "Point B"],
        tools=[
            ToolInfo(name="pytest", description="Testing framework", url="https://pytest.org", timestamp="01:23"),
        ],
        timeline=[TimelineItem(timestamp="00:00", title="Intro")],
    )

    with patch("modules.vidx.analyzer.genai.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = fake_response
        mock_client_cls.return_value = mock_client

        with patch.dict("os.environ", {"GEMINI_API_KEY": "fake-key"}):
            from modules.vidx.analyzer import analyze_video
            result = await analyze_video({"title": "T"}, "transcript text")

    assert result.title == "Test Video"
    assert len(result.tools) == 1
    assert result.tools[0].url == "https://pytest.org"


# --------------------------------------------------------------------------- #
# Notion block generation
# --------------------------------------------------------------------------- #

def test_build_blocks_structure():
    analysis = VideoAnalysis(
        title="Demo",
        summary="Summary text",
        key_points=["Point 1"],
        tools=[ToolInfo(name="ToolA", description="Desc", url="https://a.com", timestamp="02:00")],
        timeline=[TimelineItem(timestamp="00:00", title="Start")],
    )
    blocks = _build_blocks(analysis, "https://youtu.be/123")
    types_found = [b["type"] for b in blocks]
    assert "heading_1" in types_found
    assert "paragraph" in types_found
    assert "bulleted_list_item" in types_found
    # Ensure URL link block exists
    assert any(
        b["type"] == "paragraph" and any(
            t.get("text", {}).get("link") for t in b["paragraph"]["rich_text"]
        )
        for b in blocks
    )


def test_build_properties():
    analysis = VideoAnalysis(
        title="Demo",
        summary="S",
        key_points=[],
        tools=[ToolInfo(name="T1", description="D", url=None, timestamp=None)],
        timeline=[],
    )
    metadata = {
        "video_id": "VID",
        "channel": "C",
        "canonical_url": "https://youtu.be/VID",
        "published": "20240115",
    }
    schema = {
        "Name": {"type": "title"},
        "Video URL": {"type": "url"},
    }
    props = _build_properties(analysis, metadata, schema)
    assert "Name" in props
    assert props["Video URL"]["url"] == "https://youtu.be/VID"
    assert props["Published"]["date"]["start"] == "2024-01-15"
    assert any(opt["name"] == "T1" for opt in props["Tools"]["multi_select"])


# --------------------------------------------------------------------------- #
# Permission checks (integration with Core)
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_vidx_setup_requires_admin(mock_bot: PlugcordBot):
    """Ensure the setup command has the admin check applied."""
    cog = VidxCog(mock_bot)
    # The check is stored on the command callback
    cmd = cog.vidx_setup
    checks = getattr(cmd, "checks", [])
    check_names = [getattr(c, "__name__", str(c)) for c in checks]
    assert any("require_admin" in name or "predicate" in name for name in check_names)
