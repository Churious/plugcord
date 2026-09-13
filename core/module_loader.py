"""Module loader for dynamic extension loading, unloading, and reloading."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from dotenv import load_dotenv

from core.exceptions import CommandConflictError, ModuleLoadError, ModuleUnloadError
from core.models.command import CommandInfo

if TYPE_CHECKING:
    from core.bot import PlugcordBot

logger = logging.getLogger("plugcord.loader")


class ModuleLoader:
    """Manages the low-level import, extension loading, and cleanup of module cogs."""

    def __init__(self, bot: PlugcordBot) -> None:
        self.bot = bot

    def _get_extension_name(self, module_id: str, modules_dir: str = "modules") -> str:
        """Returns the Python dotted import path for the module's cog entrypoint."""
        return f"{modules_dir}.{module_id}.cog"

    async def load_module(self, module_id: str, module_path: Path, modules_dir: str = "modules") -> list[str]:
        """Loads a module extension into the bot and registers its commands.

        Raises:
            ModuleLoadError: If loading fails.
            CommandConflictError: If a command conflicts with an existing command.
        """
        cog_file = module_path / "cog.py"
        if not cog_file.is_file():
            raise ModuleLoadError(module_id, f"Entrypoint cog.py not found in {module_path}")

        extension_name = self._get_extension_name(module_id, modules_dir)

        env_path = module_path / ".env"
        if env_path.is_file():
            load_dotenv(dotenv_path=env_path, override=True)
            logger.info(f"Loaded module-specific environment: {env_path}")

        pre_cogs = set(self.bot.cogs.keys())

        try:
            await self.bot.load_extension(extension_name)
        except Exception as e:
            logger.error(f"Failed to load extension '{extension_name}': {e}", exc_info=True)
            self._purge_sys_modules(extension_name)
            raise ModuleLoadError(module_id, str(e)) from e

        post_cogs = set(self.bot.cogs.keys())
        added_cogs = [self.bot.cogs[name] for name in (post_cogs - pre_cogs)]

        registered_commands: list[str] = []
        try:
            for cog in added_cogs:
                for cmd in cog.get_commands():
                    cmd_info = getattr(cmd, "__command_info__", None)
                    if cmd_info is None:
                        cmd_info = CommandInfo(
                            name=cmd.name,
                            module=module_id,
                            description=cmd.help or cmd.description or "",
                            usage=cmd.usage or cmd.name,
                            aliases=list(cmd.aliases),
                            category=cog.qualified_name or "General",
                            hidden=cmd.hidden,
                        )
                    else:
                        cmd_info.module = module_id
                        if not cmd_info.category or cmd_info.category == "General":
                            cmd_info.category = cog.qualified_name or "General"

                    self.bot.command_registry.register(cmd_info, module_id=module_id)
                    registered_commands.append(cmd_info.name)

        except CommandConflictError as conflict_err:
            logger.error(f"Command conflict when registering module '{module_id}': {conflict_err}")
            self.bot.command_registry.unregister_module(module_id)
            try:
                await self.bot.unload_extension(extension_name)
            except Exception:
                pass
            self._purge_sys_modules(extension_name)
            raise conflict_err
        except Exception as err:
            logger.error(f"Unexpected error registering commands for '{module_id}': {err}")
            self.bot.command_registry.unregister_module(module_id)
            try:
                await self.bot.unload_extension(extension_name)
            except Exception:
                pass
            self._purge_sys_modules(extension_name)
            raise ModuleLoadError(module_id, f"Command registration failed: {err}") from err

        logger.info(f"Successfully loaded module '{module_id}' with commands: {registered_commands}")
        return registered_commands

    async def unload_module(self, module_id: str, modules_dir: str = "modules") -> list[str]:
        """Unregisters commands, unloads extension, and purges module cache."""
        extension_name = self._get_extension_name(module_id, modules_dir)

        removed_commands = self.bot.command_registry.unregister_module(module_id)

        if extension_name in self.bot.extensions:
            try:
                await self.bot.unload_extension(extension_name)
            except Exception as e:
                logger.error(f"Error while unloading extension '{extension_name}': {e}", exc_info=True)
                raise ModuleUnloadError(module_id, str(e)) from e

        self._purge_sys_modules(extension_name)

        logger.info(f"Successfully unloaded module '{module_id}'")
        return removed_commands

    def _purge_sys_modules(self, extension_prefix: str) -> None:
        """Purges cached modules from sys.modules matching the extension path."""
        base_prefix = extension_prefix.rsplit(".", 1)[0]
        to_delete = [
            mod_name
            for mod_name in sys.modules
            if mod_name == base_prefix or mod_name.startswith(f"{base_prefix}.")
        ]
        for mod_name in to_delete:
            sys.modules.pop(mod_name, None)
            logger.debug(f"Purged '{mod_name}' from sys.modules")
