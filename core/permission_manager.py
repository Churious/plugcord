"""Permission management and access control for Plugcord."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from core.exceptions import PermissionDeniedError
from core.models.command import CommandInfo

if TYPE_CHECKING:
    from core.bot import PlugcordBot


class PermissionManager:
    """Evaluates execution permissions for commands, users, and bot owners."""

    def __init__(self, bot: PlugcordBot) -> None:
        self.bot = bot

    async def is_owner(self, user: discord.User | discord.Member) -> bool:
        """Determines if the user is designated as a bot owner via config or app owner."""
        if user.id in self.bot.config.discord.owners:
            return True
        try:
            return await self.bot.is_owner(user)
        except Exception:
            return False

    async def is_admin(self, ctx: commands.Context) -> bool:
        """Checks if the context author has administrator privileges or is bot owner."""
        if await self.is_owner(ctx.author):
            return True

        if ctx.guild is not None and isinstance(ctx.author, discord.Member):
            return ctx.author.guild_permissions.administrator
        return False

    async def has_permission(self, ctx: commands.Context, required_permission: str) -> bool:
        """Checks if the author has a specific Discord permission name."""
        if await self.is_owner(ctx.author):
            return True

        perm = required_permission.lower().strip()
        if perm == "owner":
            return await self.is_owner(ctx.author)

        if ctx.guild is None or not isinstance(ctx.author, discord.Member):
            return False

        if ctx.author.guild_permissions.administrator:
            return True

        if hasattr(ctx.author.guild_permissions, perm):
            return bool(getattr(ctx.author.guild_permissions, perm))

        return False

    async def can_run_command(self, ctx: commands.Context, command_info: CommandInfo) -> bool:
        """Evaluates whether the context author meets all permissions defined in CommandInfo."""
        if command_info.hidden and not await self.is_owner(ctx.author):
            return False

        if not command_info.permissions:
            return True

        for perm in command_info.permissions:
            if not await self.has_permission(ctx, perm):
                return False

        return True


def require_owner():
    """Discord command check requiring bot owner status."""

    async def predicate(ctx: commands.Context) -> bool:
        bot: PlugcordBot = ctx.bot  # type: ignore
        if not await bot.permissions.is_owner(ctx.author):
            raise PermissionDeniedError("Only bot owners can execute this command.")
        return True

    return commands.check(predicate)


def require_admin():
    """Discord command check requiring administrator privileges or bot owner."""

    async def predicate(ctx: commands.Context) -> bool:
        bot: PlugcordBot = ctx.bot  # type: ignore
        if not await bot.permissions.is_admin(ctx):
            raise PermissionDeniedError("Administrator permissions are required to execute this command.")
        return True

    return commands.check(predicate)
