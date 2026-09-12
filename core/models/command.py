"""Command metadata model and registration decorators."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from discord.ext import commands


@dataclass
class CommandInfo:
    """Metadata specification for Plugcord commands used by Dynamic Help and Registry."""

    name: str
    module: str = "Core"
    description: str = ""
    usage: str = ""
    aliases: list[str] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)
    category: str = "General"
    permissions: list[str] = field(default_factory=list)
    hidden: bool = False

    def __post_init__(self) -> None:
        self.name = self.name.strip()
        self.module = self.module.strip()
        self.description = self.description.strip()
        self.usage = self.usage.strip()
        self.category = self.category.strip()
        self.aliases = [a.strip() for a in self.aliases if a.strip()]
        self.examples = [e.strip() for e in self.examples if e.strip()]
        self.permissions = [p.strip().lower() for p in self.permissions if p.strip()]


def command_meta(
    *,
    name: str | None = None,
    module: str = "",
    description: str = "",
    usage: str = "",
    aliases: list[str] | None = None,
    examples: list[str] | None = None,
    category: str = "General",
    permissions: list[str] | None = None,
    hidden: bool = False,
) -> Callable[[Any], Any]:
    """Decorator to attach Plugcord command metadata to a command function or Command instance."""

    def decorator(target: Any) -> Any:
        nonlocal name, aliases, examples, permissions
        cmd_aliases = list(aliases) if aliases else []
        cmd_examples = list(examples) if examples else []
        cmd_perms = list(permissions) if permissions else []

        target_name = name or getattr(target, "name", None) or getattr(target, "__name__", "")

        meta = CommandInfo(
            name=target_name,
            module=module,
            description=description or getattr(target, "help", "") or getattr(target, "description", ""),
            usage=usage or getattr(target, "usage", "") or target_name,
            aliases=cmd_aliases or getattr(target, "aliases", []),
            examples=cmd_examples,
            category=category,
            permissions=cmd_perms,
            hidden=hidden or getattr(target, "hidden", False),
        )

        setattr(target, "__command_info__", meta)
        return target

    return decorator


def plugcord_command(
    *,
    name: str | None = None,
    aliases: list[str] | None = None,
    description: str = "",
    usage: str = "",
    examples: list[str] | None = None,
    category: str = "General",
    permissions: list[str] | None = None,
    hidden: bool = False,
    **command_kwargs: Any,
) -> Callable[[Callable[..., Any]], commands.Command[Any, Any, Any]]:
    """Single decorator combining discord.ext.commands.command with Plugcord metadata."""

    def decorator(func: Callable[..., Any]) -> commands.Command[Any, Any, Any]:
        cmd_name = name or func.__name__
        cmd_aliases = list(aliases) if aliases else []
        cmd_desc = description or func.__doc__ or ""
        cmd_usage = usage or f"{cmd_name}"
        cmd_examples = list(examples) if examples else []
        cmd_perms = list(permissions) if permissions else []

        cmd: commands.Command[Any, Any, Any] = commands.command(
            name=cmd_name,
            aliases=cmd_aliases,
            help=cmd_desc,
            description=cmd_desc,
            usage=cmd_usage,
            hidden=hidden,
            **command_kwargs,
        )(func)

        meta = CommandInfo(
            name=cmd_name,
            module="",
            description=cmd_desc,
            usage=cmd_usage,
            aliases=cmd_aliases,
            examples=cmd_examples,
            category=category,
            permissions=cmd_perms,
            hidden=hidden,
        )
        setattr(cmd, "__command_info__", meta)
        return cmd

    return decorator
