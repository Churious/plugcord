"""High-level Module Manager for discovery, lifecycle coordination, and persistence."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from core.exceptions import (
    InvalidManifestError,
    ModuleAlreadyDisabledError,
    ModuleAlreadyEnabledError,
    ModuleLoadError,
    ModuleReloadError,
    ModuleUnloadError,
    PlugcordModuleNotFoundError,
)
from core.models.module import ModuleManifest, ModuleRecord, ModuleState

if TYPE_CHECKING:
    from core.bot import PlugcordBot

logger = logging.getLogger("plugcord.module_manager")


class ModuleManager:
    """Manages module discovery, lifecycle transitions, state persistence, and error isolation."""

    def __init__(self, bot: PlugcordBot, modules_dir: str | Path = "modules") -> None:
        self.bot = bot
        self.modules_dir = Path(modules_dir)
        self._modules: dict[str, ModuleRecord] = {}

    def get_module(self, module_id: str) -> ModuleRecord | None:
        """Retrieves a module record by ID."""
        return self._modules.get(module_id)

    def list_modules(self) -> list[ModuleRecord]:
        """Returns a list of all discovered module records sorted by ID."""
        return sorted(self._modules.values(), key=lambda m: m.id)

    async def discover(self) -> dict[str, ModuleRecord]:
        """Scans the modules directory and discovers all valid and invalid modules.

        Guaranteed isolation: Failures in individual modules will not halt discovery.
        """
        if not self.modules_dir.exists():
            logger.warning(f"Modules directory '{self.modules_dir}' does not exist. Creating it.")
            self.modules_dir.mkdir(parents=True, exist_ok=True)
            return {}

        discovered: dict[str, ModuleRecord] = {}

        for item in self.modules_dir.iterdir():
            if not item.is_dir() or item.name.startswith((".", "_")):
                continue

            module_id = item.name
            manifest_file = item / "manifest.json"
            record = ModuleRecord(id=module_id, path=item, state=ModuleState.INSTALLED)

            if not manifest_file.is_file():
                err_msg = f"manifest.json missing in '{item}'"
                logger.error(f"Module discovery error: {err_msg}")
                record.state = ModuleState.ERROR
                record.error_message = err_msg
                discovered[module_id] = record
                continue

            try:
                with open(manifest_file, encoding="utf-8") as f:
                    raw_data = json.load(f)
            except json.JSONDecodeError as json_err:
                err_msg = f"JSON syntax error in manifest.json: {json_err}"
                logger.error(f"[{module_id}] {err_msg}")
                record.state = ModuleState.ERROR
                record.error_message = err_msg
                discovered[module_id] = record
                continue
            except Exception as e:
                err_msg = f"Failed to read manifest.json: {e}"
                logger.error(f"[{module_id}] {err_msg}")
                record.state = ModuleState.ERROR
                record.error_message = err_msg
                discovered[module_id] = record
                continue

            try:
                manifest = ModuleManifest.from_dict(raw_data, module_dir_name=module_id)
                record.manifest = manifest
                cog_path = item / "cog.py"
                if not cog_path.is_file():
                    err_msg = f"Entrypoint cog.py missing in '{item}'"
                    logger.error(f"[{module_id}] {err_msg}")
                    record.state = ModuleState.ERROR
                    record.error_message = err_msg
                else:
                    record.state = ModuleState.INSTALLED
            except InvalidManifestError as manifest_err:
                logger.error(f"[{module_id}] Manifest validation failed: {manifest_err.details}")
                record.state = ModuleState.ERROR
                record.error_message = manifest_err.details
            except Exception as e:
                logger.error(f"[{module_id}] Unexpected manifest error: {e}")
                record.state = ModuleState.ERROR
                record.error_message = str(e)

            discovered[module_id] = record
            logger.info(f"Discovered module '{module_id}' (State: {record.state})")

        self._modules = discovered
        return discovered

    async def restore_states(self) -> None:
        """Restores previously enabled modules from the SQLite database."""
        if not self.bot.config.modules.auto_restore:
            logger.info("Module auto-restore is disabled by configuration.")
            return

        stored_modules = await self.bot.database.get_all_modules()
        logger.info(f"Restoring module states from database: found {len(stored_modules)} stored records.")

        for mod_id, data in stored_modules.items():
            was_enabled = data.get("enabled", False)
            if not was_enabled:
                if mod_id in self._modules:
                    self._modules[mod_id].state = ModuleState.DISABLED
                continue

            if mod_id not in self._modules:
                logger.warning(
                    f"Module '{mod_id}' was enabled in database, but is not present on filesystem. "
                    "Skipping restore safely."
                )
                continue

            record = self._modules[mod_id]
            if record.state == ModuleState.ERROR:
                logger.warning(
                    f"Module '{mod_id}' was enabled in database, but has filesystem/manifest errors. "
                    f"Skipping auto-enable. (Error: {record.error_message})"
                )
                continue

            try:
                logger.info(f"Auto-restoring module: '{mod_id}'...")
                await self.enable(mod_id, save_state=False)
            except Exception as e:
                logger.error(f"Failed to auto-restore module '{mod_id}': {e}", exc_info=True)

    async def enable(self, module_id: str, save_state: bool = True) -> list[str]:
        """Enables a module, loads its extension, and persists state.

        Returns:
            List of registered command names.
        """
        record = self._modules.get(module_id)
        if record is None:
            raise PlugcordModuleNotFoundError(module_id)

        if record.state == ModuleState.ENABLED:
            raise ModuleAlreadyEnabledError(module_id)

        if record.manifest is None:
            raise InvalidManifestError(module_id, record.error_message or "Manifest is invalid or missing.")

        modules_dir_name = self.modules_dir.name
        try:
            registered_cmds = await self.bot.module_loader.load_module(
                module_id, record.path, modules_dir=modules_dir_name
            )
            record.state = ModuleState.ENABLED
            record.error_message = None
            record.loaded_commands = registered_cmds

            if save_state:
                await self.bot.database.set_module_state(module_id, enabled=True, last_status="enabled")

            logger.info(f"Module '{module_id}' enabled successfully.")
            return registered_cmds

        except Exception as e:
            record.state = ModuleState.ERROR
            record.error_message = str(e)
            record.loaded_commands = []
            if save_state:
                await self.bot.database.set_module_state(module_id, enabled=False, last_status="error")
            logger.error(f"Failed to enable module '{module_id}': {e}")
            if not isinstance(e, ModuleLoadError):
                raise ModuleLoadError(module_id, str(e)) from e
            raise

    async def disable(self, module_id: str, save_state: bool = True) -> list[str]:
        """Disables an active module, unloads its extension, and persists state."""
        record = self._modules.get(module_id)
        if record is None:
            raise PlugcordModuleNotFoundError(module_id)

        if record.state == ModuleState.DISABLED:
            raise ModuleAlreadyDisabledError(module_id)

        modules_dir_name = self.modules_dir.name
        try:
            removed_cmds = await self.bot.module_loader.unload_module(module_id, modules_dir=modules_dir_name)
            record.state = ModuleState.DISABLED
            record.loaded_commands = []
            record.error_message = None

            if save_state:
                await self.bot.database.set_module_state(module_id, enabled=False, last_status="disabled")

            logger.info(f"Module '{module_id}' disabled successfully.")
            return removed_cmds

        except Exception as e:
            record.state = ModuleState.ERROR
            record.error_message = str(e)
            if save_state:
                await self.bot.database.set_module_state(module_id, enabled=False, last_status="error")
            logger.error(f"Failed to disable module '{module_id}': {e}")
            if not isinstance(e, ModuleUnloadError):
                raise ModuleUnloadError(module_id, str(e)) from e
            raise

    async def reload(self, module_id: str) -> list[str]:
        """Reloads a module transactionally.

        If the module was enabled, unloads it and loads it anew.
        If loading fails during reload, the module transitions to ERROR and state is persisted.
        """
        record = self._modules.get(module_id)
        if record is None:
            raise PlugcordModuleNotFoundError(module_id)

        was_enabled = record.state == ModuleState.ENABLED

        manifest_file = record.path / "manifest.json"
        if manifest_file.is_file():
            try:
                with open(manifest_file, encoding="utf-8") as f:
                    data = json.load(f)
                record.manifest = ModuleManifest.from_dict(data, module_dir_name=module_id)
            except Exception as err:
                record.state = ModuleState.ERROR
                record.error_message = f"Manifest reload failed: {err}"
                await self.bot.database.set_module_state(module_id, enabled=False, last_status="error")
                raise ModuleReloadError(module_id, str(err)) from err

        if was_enabled:
            await self.disable(module_id, save_state=False)

        try:
            registered_cmds = await self.enable(module_id, save_state=True)
            logger.info(f"Module '{module_id}' reloaded successfully.")
            return registered_cmds
        except Exception as e:
            logger.error(f"Reload failed for module '{module_id}': {e}")
            raise ModuleReloadError(module_id, str(e)) from e
