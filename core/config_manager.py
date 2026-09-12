"""Configuration manager for Plugcord."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from core.exceptions import ConfigurationError


@dataclass
class DiscordConfig:
    prefix: str = "!"
    owners: list[int] = field(default_factory=list)


@dataclass
class ModulesConfig:
    auto_restore: bool = True
    directory: str = "modules"


@dataclass
class HelpConfig:
    hide_unavailable_commands: bool = True


@dataclass
class LoggingConfig:
    level: str = "INFO"
    file: str = "logs/plugcord.log"
    max_bytes: int = 10 * 1024 * 1024
    backup_count: int = 5


@dataclass
class DatabaseConfig:
    path: str = "data/plugcord.db"


@dataclass
class Config:
    discord: DiscordConfig = field(default_factory=DiscordConfig)
    modules: ModulesConfig = field(default_factory=ModulesConfig)
    help: HelpConfig = field(default_factory=HelpConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    token: str = ""


class ConfigManager:
    """Loads and validates configuration from YAML and environment variables."""

    def __init__(
        self,
        config_path: str | Path = "config/config.yaml",
        env_path: str | Path = ".env",
    ) -> None:
        self.config_path = Path(config_path)
        self.env_path = Path(env_path)
        self._config: Config | None = None

    @property
    def config(self) -> Config:
        if self._config is None:
            self._config = self.load()
        return self._config

    def load(self) -> Config:
        """Loads configuration from YAML file and .env file."""
        token = ""
        if self.env_path.is_file():
            load_dotenv(dotenv_path=self.env_path, override=True)
            token = os.environ.get("DISCORD_TOKEN", "").strip()
        elif "DISCORD_TOKEN" in os.environ:
            token = os.environ.get("DISCORD_TOKEN", "").strip()

        data: dict[str, Any] = {}
        if self.config_path.is_file():
            try:
                with open(self.config_path, encoding="utf-8") as f:
                    loaded = yaml.safe_load(f)
                    if isinstance(loaded, dict):
                        data = loaded
            except Exception as e:
                raise ConfigurationError(f"Failed to parse config file '{self.config_path}': {e}") from e

        discord_data = data.get("discord", {}) or {}
        prefix = str(discord_data.get("prefix", "!"))
        owners_raw = discord_data.get("owners", []) or []
        owners: list[int] = []
        for o in owners_raw:
            try:
                owners.append(int(o))
            except (ValueError, TypeError):
                pass

        if "PLUGCORD_PREFIX" in os.environ:
            prefix = os.environ["PLUGCORD_PREFIX"]

        discord_cfg = DiscordConfig(prefix=prefix, owners=owners)

        mod_data = data.get("modules", {}) or {}
        mod_cfg = ModulesConfig(
            auto_restore=bool(mod_data.get("auto_restore", True)),
            directory=str(mod_data.get("directory", "modules")),
        )

        help_data = data.get("help", {}) or {}
        help_cfg = HelpConfig(
            hide_unavailable_commands=bool(help_data.get("hide_unavailable_commands", True)),
        )

        log_data = data.get("logging", {}) or {}
        log_cfg = LoggingConfig(
            level=str(log_data.get("level", "INFO")),
            file=str(log_data.get("file", "logs/plugcord.log")),
            max_bytes=int(log_data.get("max_bytes", 10 * 1024 * 1024)),
            backup_count=int(log_data.get("backup_count", 5)),
        )

        db_data = data.get("database", {}) or {}
        db_cfg = DatabaseConfig(
            path=str(db_data.get("path", "data/plugcord.db")),
        )

        # Token was loaded above from env_path or os.environ

        self._config = Config(
            discord=discord_cfg,
            modules=mod_cfg,
            help=help_cfg,
            logging=log_cfg,
            database=db_cfg,
            token=token,
        )
        return self._config
