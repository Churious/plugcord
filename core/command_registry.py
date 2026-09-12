"""Centralized Command Registry for metadata tracking and conflict resolution."""

from __future__ import annotations

import logging

from core.exceptions import CommandConflictError
from core.models.command import CommandInfo

logger = logging.getLogger("plugcord.registry")


class CommandRegistry:
    """Stores and validates command metadata registered by Core and Modules."""

    def __init__(self) -> None:
        self._commands: dict[str, CommandInfo] = {}
        self._aliases: dict[str, str] = {}
        self._module_commands: dict[str, set[str]] = {}

    def register(self, command_info: CommandInfo, module_id: str = "Core") -> None:
        """Registers a command and its aliases for a given module.

        Raises:
            CommandConflictError: If the command name or any alias conflicts with another module.
        """
        cmd_name = command_info.name.lower()
        command_info.module = module_id

        if cmd_name in self._commands:
            existing = self._commands[cmd_name]
            if existing.module != module_id:
                logger.warning(
                    f"Command conflict detected: '{cmd_name}' in module '{module_id}' "
                    f"conflicts with module '{existing.module}'"
                )
                raise CommandConflictError(cmd_name, existing.module, module_id)

        if cmd_name in self._aliases:
            primary_name = self._aliases[cmd_name]
            existing = self._commands[primary_name]
            if existing.module != module_id:
                raise CommandConflictError(cmd_name, existing.module, module_id)

        for alias in command_info.aliases:
            alias_lower = alias.lower()
            if alias_lower in self._commands:
                existing = self._commands[alias_lower]
                if existing.module != module_id:
                    raise CommandConflictError(alias_lower, existing.module, module_id)
            if alias_lower in self._aliases:
                primary_name = self._aliases[alias_lower]
                existing = self._commands[primary_name]
                if existing.module != module_id:
                    raise CommandConflictError(alias_lower, existing.module, module_id)

        if cmd_name in self._commands and self._commands[cmd_name].module == module_id:
            self._remove_single_command(cmd_name)

        self._commands[cmd_name] = command_info

        for alias in command_info.aliases:
            self._aliases[alias.lower()] = cmd_name

        if module_id not in self._module_commands:
            self._module_commands[module_id] = set()
        self._module_commands[module_id].add(cmd_name)

        logger.info(f"Command registered: '{cmd_name}' (Module: '{module_id}')")

    def _remove_single_command(self, cmd_name: str) -> None:
        """Removes a single command and its aliases."""
        if cmd_name not in self._commands:
            return

        cmd_info = self._commands.pop(cmd_name)
        for alias in cmd_info.aliases:
            self._aliases.pop(alias.lower(), None)

        if cmd_info.module in self._module_commands:
            self._module_commands[cmd_info.module].discard(cmd_name)

    def unregister_module(self, module_id: str) -> list[str]:
        """Unregisters all commands and aliases belonging to a module.

        Returns:
            List of unregistering command primary names.
        """
        registered_names = list(self._module_commands.get(module_id, set()))
        for name in registered_names:
            self._remove_single_command(name)

        self._module_commands.pop(module_id, None)
        logger.info(f"Unregistered {len(registered_names)} command(s) for module '{module_id}'")
        return registered_names

    def get_command(self, name_or_alias: str) -> CommandInfo | None:
        """Finds a command by its primary name or alias."""
        key = name_or_alias.lower().strip()
        if key in self._commands:
            return self._commands[key]
        if key in self._aliases:
            primary = self._aliases[key]
            return self._commands.get(primary)
        return None

    def get_module_commands(self, module_id: str) -> list[CommandInfo]:
        """Returns all CommandInfo objects belonging to a module."""
        names = self._module_commands.get(module_id, set())
        return [self._commands[name] for name in sorted(names) if name in self._commands]

    def get_all_commands(self) -> list[CommandInfo]:
        """Returns all registered CommandInfo objects."""
        return list(self._commands.values())

    def clear(self) -> None:
        """Clears all registered commands and aliases."""
        self._commands.clear()
        self._aliases.clear()
        self._module_commands.clear()
