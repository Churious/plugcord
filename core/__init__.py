"""Plugcord - Modular Discord Bot Framework Core Package."""

from core.bot import PlugcordBot
from core.command_registry import CommandRegistry
from core.config_manager import Config, ConfigManager
from core.database import Database
from core.exceptions import (
    CommandConflictError,
    ConfigurationError,
    DatabaseError,
    InvalidManifestError,
    ModuleAlreadyDisabledError,
    ModuleAlreadyEnabledError,
    ModuleError,
    ModuleLoadError,
    ModuleNotFoundError,
    ModuleReloadError,
    ModuleUnloadError,
    PermissionDeniedError,
    PlugcordError,
    PlugcordModuleNotFoundError,
)
from core.help_manager import HelpManager
from core.logger import setup_logger
from core.models.command import CommandInfo, command_meta, plugcord_command
from core.models.module import ModuleManifest, ModuleRecord, ModuleState
from core.module_loader import ModuleLoader
from core.module_manager import ModuleManager
from core.permission_manager import PermissionManager

__all__ = [
    "CommandConflictError",
    "CommandInfo",
    "CommandRegistry",
    "Config",
    "ConfigManager",
    "ConfigurationError",
    "Database",
    "DatabaseError",
    "HelpManager",
    "InvalidManifestError",
    "ModuleAlreadyDisabledError",
    "ModuleAlreadyEnabledError",
    "ModuleError",
    "ModuleLoadError",
    "ModuleLoader",
    "ModuleManager",
    "ModuleManifest",
    "ModuleNotFoundError",
    "ModuleRecord",
    "ModuleReloadError",
    "ModuleState",
    "ModuleUnloadError",
    "PermissionDeniedError",
    "PermissionManager",
    "PlugcordBot",
    "PlugcordError",
    "PlugcordModuleNotFoundError",
    "command_meta",
    "plugcord_command",
    "setup_logger",
]
