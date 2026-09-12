"""Integration tests for ModuleManager, discovery, lifecycle, and isolation."""

import json
import sys
from pathlib import Path

import pytest

from core.bot import PlugcordBot
from core.exceptions import (
    ModuleAlreadyDisabledError,
    ModuleAlreadyEnabledError,
    PlugcordModuleNotFoundError,
)
from core.models.module import ModuleState


@pytest.mark.asyncio
async def test_module_discovery_and_fault_isolation(mock_bot: PlugcordBot, temp_dir: Path):
    modules_dir = Path(mock_bot.config.modules.directory)

    # 1. Valid module
    mod1 = modules_dir / "valid_mod"
    mod1.mkdir(parents=True, exist_ok=True)
    (mod1 / "manifest.json").write_text(
        json.dumps({
            "id": "valid_mod",
            "name": "Valid Module",
            "version": "1.0.0",
            "description": "A perfectly valid module",
            "author": "Sihwan Lee",
        }),
        encoding="utf-8",
    )
    (mod1 / "cog.py").write_text("# valid cog entrypoint", encoding="utf-8")

    # 2. Module with missing manifest
    mod2 = modules_dir / "no_manifest"
    mod2.mkdir(parents=True, exist_ok=True)
    (mod2 / "cog.py").write_text("# no manifest here", encoding="utf-8")

    # 3. Module with bad JSON
    mod3 = modules_dir / "bad_json"
    mod3.mkdir(parents=True, exist_ok=True)
    (mod3 / "manifest.json").write_text("{ broken json ...", encoding="utf-8")
    (mod3 / "cog.py").write_text("# cog", encoding="utf-8")

    # 4. Module missing cog.py
    mod4 = modules_dir / "missing_cog"
    mod4.mkdir(parents=True, exist_ok=True)
    (mod4 / "manifest.json").write_text(
        json.dumps({
            "id": "missing_cog",
            "name": "Missing Cog",
            "version": "1.0.0",
            "description": "Missing entrypoint",
        }),
        encoding="utf-8",
    )

    discovered = await mock_bot.module_manager.discover()
    assert len(discovered) == 4

    assert discovered["valid_mod"].state == ModuleState.INSTALLED
    assert discovered["valid_mod"].manifest is not None
    assert discovered["valid_mod"].manifest.name == "Valid Module"

    assert discovered["no_manifest"].state == ModuleState.ERROR
    assert "manifest.json missing" in discovered["no_manifest"].error_message

    assert discovered["bad_json"].state == ModuleState.ERROR
    assert "JSON syntax error" in discovered["bad_json"].error_message

    assert discovered["missing_cog"].state == ModuleState.ERROR
    assert "cog.py missing" in discovered["missing_cog"].error_message


@pytest.mark.asyncio
async def test_module_lifecycle_and_persistence(mock_bot: PlugcordBot, temp_dir: Path):
    await mock_bot.database.connect()

    modules_dir = Path(mock_bot.config.modules.directory)
    if str(modules_dir.parent) not in sys.path:
        sys.path.insert(0, str(modules_dir.parent))

    mod = modules_dir / "sample"
    mod.mkdir(parents=True, exist_ok=True)
    (mod / "manifest.json").write_text(
        json.dumps({
            "id": "sample",
            "name": "Sample Module",
            "version": "2.0.0",
            "description": "Functional test module",
        }),
        encoding="utf-8",
    )

    cog_code = """
from discord.ext import commands
from core.models.command import command_meta

class SampleCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.unloaded = False

    def cog_unload(self):
        self.unloaded = True

    @commands.command(name="hello", aliases=["hi"])
    @command_meta(
        name="hello",
        aliases=["hi"],
        description="Says hello",
        usage="hello",
        category="Greeting"
    )
    async def hello(self, ctx):
        await ctx.send("Hello from sample!")

async def setup(bot):
    await bot.add_cog(SampleCog(bot))
"""
    (mod / "cog.py").write_text(cog_code, encoding="utf-8")

    # 1. Discover
    await mock_bot.module_manager.discover()
    record = mock_bot.module_manager.get_module("sample")
    assert record is not None
    assert record.state == ModuleState.INSTALLED

    # 2. Enable
    registered = await mock_bot.module_manager.enable("sample")
    assert "hello" in registered
    assert record.state == ModuleState.ENABLED
    assert "SampleCog" in mock_bot.cogs
    assert mock_bot.command_registry.get_command("hello") is not None

    db_state = await mock_bot.database.get_module_state("sample")
    assert db_state is not None
    assert db_state["enabled"] is True
    assert db_state["last_status"] == "enabled"

    with pytest.raises(ModuleAlreadyEnabledError):
        await mock_bot.module_manager.enable("sample")

    # 3. Reload
    reloaded = await mock_bot.module_manager.reload("sample")
    assert "hello" in reloaded
    assert record.state == ModuleState.ENABLED
    assert "SampleCog" in mock_bot.cogs

    # 4. Disable
    removed = await mock_bot.module_manager.disable("sample")
    assert "hello" in removed
    assert record.state == ModuleState.DISABLED
    assert "SampleCog" not in mock_bot.cogs
    assert mock_bot.command_registry.get_command("hello") is None

    db_state_after = await mock_bot.database.get_module_state("sample")
    assert db_state_after["enabled"] is False
    assert db_state_after["last_status"] == "disabled"

    with pytest.raises(ModuleAlreadyDisabledError):
        await mock_bot.module_manager.disable("sample")

    with pytest.raises(PlugcordModuleNotFoundError):
        await mock_bot.module_manager.enable("non_existent")

    await mock_bot.database.close()


@pytest.mark.asyncio
async def test_auto_restore_with_missing_filesystem_module(mock_bot: PlugcordBot):
    await mock_bot.database.connect()

    await mock_bot.database.set_module_state("ghost_module", enabled=True, last_status="enabled")

    await mock_bot.module_manager.discover()
    await mock_bot.module_manager.restore_states()

    assert mock_bot.module_manager.get_module("ghost_module") is None

    await mock_bot.database.close()
