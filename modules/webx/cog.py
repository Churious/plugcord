"""Webx Discord Cog for automatic web article analysis and Notion integration."""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import UTC, datetime
from typing import Any

import discord
from discord.ext import commands

from core.models.command import CommandInfo, command_meta
from core.permission_manager import require_admin
from modules.webx.analyzer import analyze_article
from modules.webx.exceptions import NotionError, WebxError
from modules.webx.extractor import fetch_article, is_processable_url
from modules.webx.models import ArticleAnalysis
from modules.webx.notion import create_page

logger = logging.getLogger("plugcord.webx.cog")

_URL_PATTERN = re.compile(r"https?://[^\s<>()\[\]{}\"']+")


class WebxCog(commands.Cog):
    """Cog providing webx commands and automatic web article processing."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._locks: dict[tuple[int, str], asyncio.Lock] = {}

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    async def cog_load(self) -> None:
        await self._init_db()
        for cmd in self.webx_group.walk_commands():
            meta = getattr(cmd, "__command_info__", None)
            if meta is None:
                meta = CommandInfo(
                    name=f"{self.webx_group.name} {cmd.name}",
                    module="webx",
                    description=cmd.help or cmd.description or "",
                    usage=f"{self.webx_group.name} {cmd.name} ...",
                    aliases=list(cmd.aliases),
                    category="webx",
                    hidden=cmd.hidden,
                )
            else:
                meta.name = f"{self.webx_group.name} {cmd.name}"
                meta.module = "webx"
            self.bot.command_registry.register(meta, module_id="webx")

    async def _init_db(self) -> None:
        await self.bot.database.execute(
            """
            CREATE TABLE IF NOT EXISTS webx_settings (
                guild_id INTEGER PRIMARY KEY,
                channel_id INTEGER,
                notion_database_id TEXT,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        await self.bot.database.execute(
            """
            CREATE TABLE IF NOT EXISTS webx_pages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url_key TEXT NOT NULL,
                guild_id INTEGER NOT NULL,
                url TEXT NOT NULL,
                notion_page_id TEXT,
                notion_page_url TEXT,
                status TEXT NOT NULL DEFAULT 'processing',
                error_message TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(url_key, guild_id)
            )
            """
        )
        await self.bot.database.commit()

    # ------------------------------------------------------------------ #
    # Database helpers
    # ------------------------------------------------------------------ #

    async def _get_settings(self, guild_id: int) -> dict[str, Any] | None:
        row = await self.bot.database.fetchone(
            "SELECT guild_id, channel_id, notion_database_id, enabled, created_at, updated_at "
            "FROM webx_settings WHERE guild_id = ?",
            (guild_id,),
        )
        if row is None:
            return None
        return {
            "guild_id": row["guild_id"],
            "channel_id": row["channel_id"],
            "notion_database_id": row["notion_database_id"],
            "enabled": bool(row["enabled"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    async def _upsert_settings(self, guild_id: int, **fields: Any) -> None:
        now = datetime.now(UTC).isoformat()
        row = await self.bot.database.fetchone(
            "SELECT guild_id FROM webx_settings WHERE guild_id = ?",
            (guild_id,),
        )
        if row is None:
            cols = ["guild_id", "created_at", "updated_at"] + list(fields.keys())
            vals = [guild_id, now, now] + list(fields.values())
            placeholders = ", ".join("?" for _ in vals)
            await self.bot.database.execute(
                f"INSERT INTO webx_settings ({', '.join(cols)}) VALUES ({placeholders})",
                vals,
            )
        else:
            sets = ", ".join(f"{k} = ?" for k in fields)
            vals = list(fields.values()) + [now, guild_id]
            await self.bot.database.execute(
                f"UPDATE webx_settings SET {sets}, updated_at = ? WHERE guild_id = ?",
                vals,
            )
        await self.bot.database.commit()

    async def _get_page_record(self, guild_id: int, url_key: str) -> dict[str, Any] | None:
        row = await self.bot.database.fetchone(
            "SELECT id, url_key, guild_id, url, notion_page_id, notion_page_url, status, error_message "
            "FROM webx_pages WHERE guild_id = ? AND url_key = ?",
            (guild_id, url_key),
        )
        if row is None:
            return None
        return dict(row)

    async def _insert_page(self, guild_id: int, url_key: str, url: str) -> None:
        now = datetime.now(UTC).isoformat()
        await self.bot.database.execute(
            "INSERT INTO webx_pages (url_key, guild_id, url, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(url_key, guild_id) DO UPDATE SET updated_at = excluded.updated_at",
            (url_key, guild_id, url, "processing", now, now),
        )
        await self.bot.database.commit()

    async def _update_page_status(
        self,
        guild_id: int,
        url_key: str,
        status: str,
        notion_page_id: str | None = None,
        notion_page_url: str | None = None,
        error_message: str | None = None,
    ) -> None:
        now = datetime.now(UTC).isoformat()
        await self.bot.database.execute(
            "UPDATE webx_pages SET status = ?, notion_page_id = ?, notion_page_url = ?, "
            "error_message = ?, updated_at = ? WHERE guild_id = ? AND url_key = ?",
            (status, notion_page_id, notion_page_url, error_message, now, guild_id, url_key),
        )
        await self.bot.database.commit()

    # ------------------------------------------------------------------ #
    # Commands
    # ------------------------------------------------------------------ #

    @commands.group(name="webx", invoke_without_command=True)
    @require_admin()
    @command_meta(
        name="webx",
        module="webx",
        description="webx 모듈 설정 및 상태 확인",
        usage="webx <setup|notion|status>",
        aliases=[],
        examples=["webx setup", "webx notion <database-id>", "webx status"],
        category="webx",
        permissions=["administrator"],
        hidden=False,
    )
    async def webx_group(self, ctx: commands.Context) -> None:
        prefix = self.bot.config.discord.prefix
        await ctx.send(
            f"Usage: `{prefix}webx <setup|notion|status>`\n"
            f"Run `{prefix}help webx` for details."
        )

    @webx_group.command(name="setup")
    @require_admin()
    @command_meta(
        name="setup",
        module="webx",
        description="Set the collection channel for webx.",
        usage="webx setup [channel]",
        aliases=[],
        examples=["webx setup", "webx setup #articles"],
        category="webx",
        permissions=["administrator"],
        hidden=False,
    )
    async def webx_setup(self, ctx: commands.Context, channel: discord.TextChannel | None = None) -> None:
        target = channel or ctx.channel
        if not isinstance(target, discord.TextChannel):
            await ctx.send("❌ Text channel required.")
            return
        await self._upsert_settings(ctx.guild.id, channel_id=target.id, enabled=1)
        await ctx.send(f"✅ webx 수집 채널을 {target.mention}으로 설정했습니다.")

    @webx_group.command(name="notion")
    @require_admin()
    @command_meta(
        name="notion",
        module="webx",
        description="Set the Notion database ID for this guild.",
        usage="webx notion <database-id>",
        aliases=[],
        examples=["webx notion 1234abcd5678efgh"],
        category="webx",
        permissions=["administrator"],
        hidden=False,
    )
    async def webx_notion(self, ctx: commands.Context, database_id: str) -> None:
        await self._upsert_settings(ctx.guild.id, notion_database_id=database_id)
        await ctx.send("✅ Notion Database ID를 설정했습니다.")

    @webx_group.command(name="status")
    @command_meta(
        name="status",
        module="webx",
        description="Show current webx configuration for this guild.",
        usage="webx status",
        aliases=[],
        examples=["webx status"],
        category="webx",
        permissions=[],
        hidden=False,
    )
    async def webx_status(self, ctx: commands.Context) -> None:
        settings = await self._get_settings(ctx.guild.id)
        if not settings:
            await ctx.send("webx가 아직 설정되지 않았습니다.")
            return
        ch = self.bot.get_channel(settings["channel_id"]) if settings["channel_id"] else None
        ch_str = ch.mention if isinstance(ch, discord.TextChannel) else f"({settings['channel_id']})"
        db_id = settings["notion_database_id"] or "미설정"
        enabled = "ON" if settings["enabled"] else "OFF"
        await ctx.send(
            f"```text\n"
            f"webx Status\n"
            f"Channel      : {ch_str}\n"
            f"Notion DB    : {db_id}\n"
            f"Enabled      : {enabled}\n"
            f"```"
        )

    # ------------------------------------------------------------------ #
    # Auto-detection
    # ------------------------------------------------------------------ #

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return
        if not message.guild:
            return
        settings = await self._get_settings(message.guild.id)
        if not settings or not settings.get("enabled") or not settings.get("channel_id"):
            return
        if message.channel.id != settings["channel_id"]:
            return
        urls = self._extract_urls(message.content)
        if not urls:
            return
        for url in urls:
            await self._handle_url(message, url, settings)

    def _extract_urls(self, text: str) -> list[str]:
        return [m.group(0) for m in _URL_PATTERN.finditer(text)]

    async def _handle_url(
        self,
        message: discord.Message,
        url: str,
        settings: dict[str, Any],
    ) -> None:
        url_key = is_processable_url(url)
        if not url_key:
            return

        guild_id = message.guild.id

        existing = await self._get_page_record(guild_id, url_key)
        if existing and existing["status"] == "completed" and existing.get("notion_page_url"):
            await self._send_completion(message, existing["notion_page_url"], cached=True)
            return

        lock = self._locks.setdefault((guild_id, url_key), asyncio.Lock())
        if lock.locked():
            logger.info(f"URL {url_key} is already being processed in guild {guild_id}")
            return

        async with lock:
            try:
                existing = await self._get_page_record(guild_id, url_key)
                if existing and existing["status"] == "completed" and existing.get("notion_page_url"):
                    await self._send_completion(message, existing["notion_page_url"], cached=True)
                    return

                feedback = await message.channel.send("📄 문서 분석 중...")
                try:
                    await self._insert_page(guild_id, url_key, url)
                    article = await fetch_article(url)
                    analysis = await analyze_article(article)
                    page_id, page_url = await self._create_notion_page(settings, analysis, article)
                    await self._update_page_status(
                        guild_id, url_key, "completed", notion_page_id=page_id, notion_page_url=page_url
                    )
                    await self._send_completion(message, page_url, feedback=feedback)
                except WebxError as exc:
                    logger.warning(f"webx processing error for {url_key}: {exc}")
                    await self._update_page_status(guild_id, url_key, "failed", error_message=str(exc))
                    await feedback.edit(content=f"❌ 분석 실패: {exc}")
                except Exception as exc:
                    logger.error(f"Unexpected error processing {url_key}: {exc}", exc_info=True)
                    await self._update_page_status(guild_id, url_key, "failed", error_message=str(exc))
                    await feedback.edit(content="❌ 분석 중 예기치 않은 오류가 발생했습니다.")
            finally:
                self._locks.pop((guild_id, url_key), None)

    async def _create_notion_page(
        self,
        settings: dict[str, Any],
        analysis: ArticleAnalysis,
        article: dict[str, Any],
    ) -> tuple[str, str]:
        db_id = settings.get("notion_database_id")
        if not db_id:
            raise NotionError("Notion Database ID is not configured for this guild.")
        return await create_page(db_id, analysis, article)

    async def _send_completion(
        self,
        message: discord.Message,
        page_url: str,
        cached: bool = False,
        feedback: discord.Message | None = None,
    ) -> None:
        embed = discord.Embed(
            title="✅ 분석 완료" if not cached else "✅ 기존 분석 결과",
            description="문서 분석이 완료되어 Notion에 정리되었습니다.",
            color=discord.Color.blurple(),
        )
        embed.add_field(name="Notion Page", value=page_url, inline=False)
        if feedback is not None:
            await feedback.edit(content=None, embed=embed)
        else:
            await message.channel.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(WebxCog(bot))
