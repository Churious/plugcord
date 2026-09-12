"""Unit tests for configuration loading and validation."""

from pathlib import Path

import pytest

from core.config_manager import ConfigManager
from core.exceptions import ConfigurationError


def test_load_default_config_when_no_files(temp_dir: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("DISCORD_TOKEN", raising=False)
    monkeypatch.delenv("PLUGCORD_PREFIX", raising=False)
    non_existent_yaml = temp_dir / "config.yaml"
    non_existent_env = temp_dir / ".env"
    mgr = ConfigManager(config_path=non_existent_yaml, env_path=non_existent_env)
    cfg = mgr.load()

    assert cfg.discord.prefix == "!"
    assert cfg.discord.owners == []
    assert cfg.modules.auto_restore is True
    assert cfg.database.path == "data/plugcord.db"
    assert cfg.token == ""


def test_load_yaml_config_values(temp_dir: Path):
    yaml_file = temp_dir / "config.yaml"
    yaml_file.write_text(
        """
discord:
  prefix: "?"
  owners:
    - 123456789
    - 987654321
modules:
  auto_restore: false
  directory: "custom_modules"
help:
  hide_unavailable_commands: false
logging:
  level: "WARNING"
database:
  path: "custom_data/custom.db"
""",
        encoding="utf-8",
    )

    env_file = temp_dir / ".env"
    env_file.write_text("DISCORD_TOKEN=mock_secret_token_123\n", encoding="utf-8")

    mgr = ConfigManager(config_path=yaml_file, env_path=env_file)
    cfg = mgr.load()

    assert cfg.discord.prefix == "?"
    assert cfg.discord.owners == [123456789, 987654321]
    assert cfg.modules.auto_restore is False
    assert cfg.modules.directory == "custom_modules"
    assert cfg.help.hide_unavailable_commands is False
    assert cfg.logging.level == "WARNING"
    assert cfg.database.path == "custom_data/custom.db"
    assert cfg.token == "mock_secret_token_123"


def test_invalid_yaml_raises_configuration_error(temp_dir: Path):
    yaml_file = temp_dir / "bad_config.yaml"
    yaml_file.write_text("discord: [unclosed list", encoding="utf-8")

    mgr = ConfigManager(config_path=yaml_file, env_path=temp_dir / ".env")
    with pytest.raises(ConfigurationError):
        mgr.load()
