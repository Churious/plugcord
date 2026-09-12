"""Unit tests for the Dynamic Help Manager."""

import pytest

from core.bot import PlugcordBot
from core.models.command import CommandInfo
from core.models.module import ModuleManifest, ModuleRecord, ModuleState


@pytest.mark.asyncio
async def test_help_manager_command_and_module_details(mock_bot: PlugcordBot):
    manifest = ModuleManifest(
        id="monitoring",
        name="Server Monitoring",
        version="1.2.0",
        description="Monitors Linux hardware metrics.",
        author="Sihwan Lee",
    )
    record = ModuleRecord(
        id="monitoring",
        path=mock_bot.module_manager.modules_dir / "monitoring",
        state=ModuleState.ENABLED,
        manifest=manifest,
    )
    mock_bot.module_manager._modules["monitoring"] = record

    cmd = CommandInfo(
        name="server",
        aliases=["status"],
        description="Checks server resource usage.",
        usage="server [type]",
        examples=["server", "server cpu"],
        category="System",
        permissions=["administrator"],
        hidden=False,
    )
    mock_bot.command_registry.register(cmd, module_id="monitoring")

    cmd_data = mock_bot.help_manager.get_command_help("server")
    assert cmd_data is not None
    assert cmd_data["name"] == "server"
    assert cmd_data["module"] == "Server Monitoring v1.2.0"
    assert "status" in cmd_data["aliases"]
    assert "server cpu" in cmd_data["examples"]

    alias_data = mock_bot.help_manager.get_command_help("status")
    assert alias_data is not None
    assert alias_data["name"] == "server"

    mod_data = mock_bot.help_manager.get_module_help("monitoring")
    assert mod_data is not None
    assert mod_data["name"] == "Server Monitoring"
    assert mod_data["version"] == "1.2.0"
    assert "server" in mod_data["commands"]

    formatted_cmd = mock_bot.help_manager.format_command_detail(cmd_data, prefix="!")
    assert "!server [type]" in formatted_cmd
    assert "Server Monitoring v1.2.0" in formatted_cmd

    formatted_mod = mock_bot.help_manager.format_module_detail(mod_data)
    assert "Server Monitoring" in formatted_mod
    assert "- server" in formatted_mod


@pytest.mark.asyncio
async def test_help_manager_available_commands_filters_disabled_and_hidden(mock_bot: PlugcordBot):
    mock_bot.module_manager._modules["active_mod"] = ModuleRecord(
        id="active_mod",
        path=mock_bot.module_manager.modules_dir / "active_mod",
        state=ModuleState.ENABLED,
        manifest=ModuleManifest(id="active_mod", name="Active Mod", version="1.0", description=""),
    )
    mock_bot.module_manager._modules["disabled_mod"] = ModuleRecord(
        id="disabled_mod",
        path=mock_bot.module_manager.modules_dir / "disabled_mod",
        state=ModuleState.DISABLED,
        manifest=ModuleManifest(id="disabled_mod", name="Disabled Mod", version="1.0", description=""),
    )

    mock_bot.command_registry.register(CommandInfo(name="cmd1", module="active_mod"), "active_mod")
    mock_bot.command_registry.register(CommandInfo(name="cmd2", hidden=True, module="active_mod"), "active_mod")
    mock_bot.command_registry.register(CommandInfo(name="cmd3", module="disabled_mod"), "disabled_mod")

    available = await mock_bot.help_manager.get_available_commands()

    assert "Active Mod" in available
    cmd_names = [c.name for c in available["Active Mod"]]
    assert "cmd1" in cmd_names
    assert "cmd2" not in cmd_names
    assert "Disabled Mod" not in available


def test_help_manager_search(mock_bot: PlugcordBot):
    mock_bot.command_registry.register(
        CommandInfo(name="docker", description="Docker container management", category="DevOps"),
        "docker",
    )
    mock_bot.command_registry.register(
        CommandInfo(name="server", description="Server statistics", category="Monitoring"),
        "monitoring",
    )

    results = mock_bot.help_manager.search_help("container")
    assert len(results) == 1
    assert results[0].name == "docker"

    results = mock_bot.help_manager.search_help("Monitoring")
    assert len(results) == 1
    assert results[0].name == "server"
