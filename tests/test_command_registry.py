"""Unit tests for centralized command registry and conflict detection."""

import pytest

from core.command_registry import CommandRegistry
from core.exceptions import CommandConflictError
from core.models.command import CommandInfo


def test_register_and_lookup_command():
    registry = CommandRegistry()
    cmd = CommandInfo(
        name="server",
        aliases=["status", "srv"],
        description="Server metrics",
        usage="server [type]",
        category="Monitoring",
    )
    registry.register(cmd, module_id="monitoring")

    found = registry.get_command("server")
    assert found is not None
    assert found.name == "server"
    assert found.module == "monitoring"

    assert registry.get_command("SERVER") is not None

    assert registry.get_command("status") is not None
    assert registry.get_command("STATUS").name == "server"
    assert registry.get_command("srv").name == "server"


def test_duplicate_command_conflict_raises_error():
    registry = CommandRegistry()
    cmd1 = CommandInfo(name="ping", module="core")
    registry.register(cmd1, module_id="core")

    cmd2 = CommandInfo(name="ping", module="network")
    with pytest.raises(CommandConflictError) as exc_info:
        registry.register(cmd2, module_id="network")

    assert "conflicts with" in str(exc_info.value)
    assert exc_info.value.command_name == "ping"


def test_alias_conflict_with_primary_name_raises_error():
    registry = CommandRegistry()
    cmd1 = CommandInfo(name="server", module="monitoring")
    registry.register(cmd1, module_id="monitoring")

    cmd2 = CommandInfo(name="remote", aliases=["server"], module="ssh")
    with pytest.raises(CommandConflictError):
        registry.register(cmd2, module_id="ssh")


def test_alias_conflict_with_alias_raises_error():
    registry = CommandRegistry()
    cmd1 = CommandInfo(name="server", aliases=["st"], module="monitoring")
    registry.register(cmd1, module_id="monitoring")

    cmd2 = CommandInfo(name="state", aliases=["st"], module="cluster")
    with pytest.raises(CommandConflictError):
        registry.register(cmd2, module_id="cluster")


def test_reregister_in_same_module_succeeds_without_conflict():
    registry = CommandRegistry()
    cmd1 = CommandInfo(name="server", aliases=["st"], description="v1", module="monitoring")
    registry.register(cmd1, module_id="monitoring")

    cmd2 = CommandInfo(name="server", aliases=["st"], description="v2", module="monitoring")
    registry.register(cmd2, module_id="monitoring")

    found = registry.get_command("server")
    assert found is not None
    assert found.description == "v2"


def test_unregister_module_removes_commands_and_aliases():
    registry = CommandRegistry()
    cmd1 = CommandInfo(name="server", aliases=["st"], module="monitoring")
    cmd2 = CommandInfo(name="disk", module="monitoring")
    cmd3 = CommandInfo(name="help", module="core")

    registry.register(cmd1, module_id="monitoring")
    registry.register(cmd2, module_id="monitoring")
    registry.register(cmd3, module_id="core")

    assert len(registry.get_module_commands("monitoring")) == 2

    removed = registry.unregister_module("monitoring")
    assert set(removed) == {"server", "disk"}
    assert registry.get_command("server") is None
    assert registry.get_command("st") is None
    assert registry.get_command("disk") is None
    assert registry.get_command("help") is not None
