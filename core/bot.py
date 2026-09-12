"""Plugcord central Discord Bot implementation."""

from __future__ import annotations

import logging
from typing import Any

import discord
from discord.ext import commands

from core.command_registry import CommandRegistry
from core.config_manager import Config
from core.database import Database
from core.exceptions import (
    PermissionDeniedError,
    PlugcordError,
    PlugcordModuleNotFoundError,
)
from core.help_manager import HelpManager
from core.models.command import CommandInfo
from core.module_loader import ModuleLoader
from core.module_manager import ModuleManager
from core.permission_manager import PermissionManager, require_admin

logger = logging.getLogger("plugcord.bot")


class PlugcordBot(commands.Bot):
    """Core Plugcord Discord Bot."""

    def __init__(self, config: Config, **options: Any) -> None:
        self.config = config

        intents = discord.Intents.default()
        intents.message_content = True

        super().__init__(
            command_prefix=config.discord.prefix,
            intents=intents,
            help_command=None,
            **options,
        )

        self.database = Database(db_path=config.database.path)
        self.permissions = PermissionManager(self)
        self.command_registry = CommandRegistry()
        self.help_manager = HelpManager(self)
        self.module_loader = ModuleLoader(self)
        self.module_manager = ModuleManager(self, modules_dir=config.modules.directory)

    async def setup_hook(self) -> None:
        """Asynchronous initialization before Discord gateway login."""
        logger.info("Initializing Plugcord core subsystems...")

        await self.database.connect()
        self._register_core_commands()
        await self.module_manager.discover()
        await self.module_manager.restore_states()

        logger.info("Plugcord core subsystems successfully initialized.")

    async def close(self) -> None:
        """Gracefully shuts down modules, database, and Discord connection."""
        logger.info("Initiating graceful shutdown of Plugcord...")

        for record in self.module_manager.list_modules():
            if record.state.value == "enabled":
                try:
                    logger.info(f"Unloading module '{record.id}' on shutdown...")
                    await self.module_loader.unload_module(record.id, modules_dir=self.config.modules.directory)
                except Exception as e:
                    logger.error(f"Error unloading module '{record.id}' during shutdown: {e}")

        await self.database.close()
        await super().close()
        logger.info("Plugcord shutdown complete.")

    async def on_ready(self) -> None:
        """Triggered when Discord bot client has established connection and cache."""
        user = self.user.name if self.user else "Plugcord"
        logger.info(f"Bot logged in as {user} (ID: {self.user.id if self.user else 'Unknown'})")
        logger.info(f"Configured prefix: '{self.config.discord.prefix}'")
        logger.info(f"Total commands in registry: {len(self.command_registry.get_all_commands())}")

    async def on_command_error(self, ctx: commands.Context, error: Exception) -> None:
        """Global error handler preventing raw traceback leak in Discord channels."""
        original = getattr(error, "original", error)

        if isinstance(error, commands.CommandNotFound):
            return

        if isinstance(original, PermissionDeniedError):
            await ctx.send(f"❌ {original}")
            return

        if isinstance(error, (commands.MissingPermissions, commands.NotOwner)):
            await ctx.send("❌ You do not have permission to execute this command.")
            return

        if isinstance(error, commands.MissingRequiredArgument):
            prefix = self.config.discord.prefix
            await ctx.send(
                f"❌ Missing argument: `{error.param.name}`. Use `{prefix}help {ctx.command.name}` for usage."
            )
            return

        if isinstance(error, commands.BadArgument):
            await ctx.send(f"❌ Invalid argument: {error}")
            return

        if isinstance(original, PlugcordError):
            logger.warning(f"Command '{ctx.command}' failed with Plugcord error: {original}")
            await ctx.send(f"❌ {original}")
            return

        logger.error(f"Unhandled exception in command '{ctx.command}': {original}", exc_info=original)
        await ctx.send("❌ An unexpected error occurred while processing the command.")

    def _register_core_commands(self) -> None:
        """Registers built-in Core commands with Discord and CommandRegistry."""

        @self.command(name="help", aliases=["commands"])
        async def help_cmd(ctx: commands.Context, *, target: str | None = None) -> None:
            prefix = self.config.discord.prefix

            if not target:
                grouped = await self.help_manager.get_available_commands(ctx)
                msg = self.help_manager.format_overview(grouped, prefix)
                await ctx.send(msg)
                return

            parts = target.strip().split(maxsplit=1)
            if parts[0].lower() == "search" and len(parts) > 1:
                keyword = parts[1]
                matches = self.help_manager.search_help(keyword)
                if not matches:
                    await ctx.send(f"No commands found matching '{keyword}'.")
                    return
                lines = ["```text", f"Search Results for '{keyword}':", ""]
                for c in matches:
                    lines.append(f"{prefix}{c.name} - {c.description or 'No description'}")
                lines.append("```")
                await ctx.send("\n".join(lines))
                return

            query = target.strip()
            cmd_data = self.help_manager.get_command_help(query)
            if cmd_data:
                await ctx.send(self.help_manager.format_command_detail(cmd_data, prefix))
                return

            mod_data = self.help_manager.get_module_help(query)
            if mod_data:
                await ctx.send(self.help_manager.format_module_detail(mod_data))
                return

            await ctx.send(
                f"Command or module '{query}' not found. Use `{prefix}help` to see available commands."
            )

        self.command_registry.register(
            CommandInfo(
                name="help",
                module="Core",
                description="Displays help information for commands or modules.",
                usage="help [command|module|search <query>]",
                aliases=["commands"],
                examples=["help", "help server", "help monitoring", "help search server"],
                category="Core",
                permissions=[],
                hidden=False,
            ),
            module_id="Core",
        )

        @self.command(name="ping")
        async def ping_cmd(ctx: commands.Context) -> None:
            latency_ms = round(self.latency * 1000)
            await ctx.send(f"Pong! (`{latency_ms}ms`)")

        self.command_registry.register(
            CommandInfo(
                name="ping",
                module="Core",
                description="Checks bot latency.",
                usage="ping",
                aliases=[],
                examples=["ping"],
                category="Core",
                permissions=[],
                hidden=False,
            ),
            module_id="Core",
        )

        @self.group(name="module", aliases=["mod"], invoke_without_command=True)
        @require_admin()
        async def module_cmd(ctx: commands.Context) -> None:
            prefix = self.config.discord.prefix
            await ctx.send(
                f"Usage: `{prefix}module <list|enable|disable|reload|info> [module_id]`\n"
                f"Run `{prefix}module list` to view all modules."
            )

        @module_cmd.command(name="list")
        @require_admin()
        async def module_list(ctx: commands.Context) -> None:
            await self.module_manager.discover()
            modules = self.module_manager.list_modules()

            if not modules:
                await ctx.send("No modules installed in the `modules/` directory.")
                return

            lines = ["```text", "Installed Modules:", ""]
            for m in modules:
                status_str = f"[{m.state.value.upper():<9}]"
                version_str = f"v{m.version}" if m.manifest else "-"
                name_str = m.name
                lines.append(f"{status_str} {m.id:<16} {version_str:<8} {name_str}")
                if m.error_message:
                    lines.append(f"           └ Error: {m.error_message}")
            lines.append("```")
            await ctx.send("\n".join(lines))

        @module_cmd.command(name="enable")
        @require_admin()
        async def module_enable(ctx: commands.Context, module_id: str) -> None:
            try:
                cmds = await self.module_manager.enable(module_id)
                cmd_list = f" (Commands: {', '.join(cmds)})" if cmds else ""
                await ctx.send(f"✅ Module `{module_id}` enabled successfully.{cmd_list}")
            except PlugcordModuleNotFoundError:
                await ctx.send(f"❌ Module `{module_id}` not found. Run `module list` to see installed modules.")
            except Exception as e:
                await ctx.send(f"❌ Failed to enable module `{module_id}`: {e}")

        @module_cmd.command(name="disable")
        @require_admin()
        async def module_disable(ctx: commands.Context, module_id: str) -> None:
            try:
                removed = await self.module_manager.disable(module_id)
                removed_str = f" (Unregistered: {', '.join(removed)})" if removed else ""
                await ctx.send(f"✅ Module `{module_id}` disabled successfully.{removed_str}")
            except PlugcordModuleNotFoundError:
                await ctx.send(f"❌ Module `{module_id}` not found.")
            except Exception as e:
                await ctx.send(f"❌ Failed to disable module `{module_id}`: {e}")

        @module_cmd.command(name="reload")
        @require_admin()
        async def module_reload(ctx: commands.Context, module_id: str) -> None:
            try:
                cmds = await self.module_manager.reload(module_id)
                cmd_list = f" (Commands: {', '.join(cmds)})" if cmds else ""
                await ctx.send(f"✅ Module `{module_id}` reloaded successfully.{cmd_list}")
            except PlugcordModuleNotFoundError:
                await ctx.send(f"❌ Module `{module_id}` not found.")
            except Exception as e:
                await ctx.send(f"❌ Failed to reload module `{module_id}`: {e}")

        @module_cmd.command(name="info")
        @require_admin()
        async def module_info(ctx: commands.Context, module_id: str) -> None:
            mod_data = self.help_manager.get_module_help(module_id)
            if not mod_data:
                await ctx.send(f"❌ Module `{module_id}` not found.")
                return
            await ctx.send(self.help_manager.format_module_detail(mod_data))

        self.command_registry.register(
            CommandInfo(
                name="module",
                module="Core",
                description="Manages Plugcord modules (list, enable, disable, reload, info).",
                usage="module <list|enable|disable|reload|info> [module_id]",
                aliases=["mod"],
                examples=["module list", "module enable docker", "module disable docker", "module reload docker"],
                category="Core",
                permissions=["administrator"],
                hidden=False,
            ),
            module_id="Core",
        )
