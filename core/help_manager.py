"""Dynamic Help Manager for querying and formatting command and module documentation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.models.command import CommandInfo
from core.models.module import ModuleState

if TYPE_CHECKING:
    from core.bot import PlugcordBot


class HelpManager:
    """Provides structured help information decoupled from Discord presentation."""

    def __init__(self, bot: PlugcordBot) -> None:
        self.bot = bot

    def get_command_help(self, name_or_alias: str) -> dict[str, Any] | None:
        """Retrieves structured help data for a single command.

        Lookup priority: Command name / alias takes precedence over module name.
        """
        cmd_info = self.bot.command_registry.get_command(name_or_alias)
        if cmd_info is None:
            return None

        module_display = cmd_info.module
        if cmd_info.module != "Core":
            mod_record = self.bot.module_manager.get_module(cmd_info.module)
            if mod_record and mod_record.manifest:
                module_display = f"{mod_record.manifest.name} v{mod_record.manifest.version}"

        return {
            "name": cmd_info.name,
            "module": module_display,
            "module_id": cmd_info.module,
            "description": cmd_info.description or "No description provided.",
            "usage": cmd_info.usage or cmd_info.name,
            "aliases": cmd_info.aliases,
            "examples": cmd_info.examples,
            "category": cmd_info.category,
            "permissions": cmd_info.permissions,
            "hidden": cmd_info.hidden,
        }

    def _load_module_help_md(self, record: Any) -> str:
        """Loads optional rich help documentation from modules/<id>/help.md.

        This is a generic Core convention: any module may ship a help.md.
        """
        try:
            help_path = record.path / "help.md"
        except Exception:
            return ""
        if not help_path.is_file():
            return ""
        try:
            return help_path.read_text(encoding="utf-8").strip()
        except Exception:
            return ""

    def get_module_help(self, module_id_or_name: str) -> dict[str, Any] | None:
        """Retrieves structured help data for a module and its registered commands."""
        record = self.bot.module_manager.get_module(module_id_or_name)
        if record is None:
            for mod in self.bot.module_manager.list_modules():
                if mod.manifest and mod.manifest.name.lower() == module_id_or_name.lower():
                    record = mod
                    break

        if record is None:
            return None

        commands = self.bot.command_registry.get_module_commands(record.id)
        cmd_names = [c.name for c in commands if not c.hidden]

        return {
            "id": record.id,
            "name": record.name,
            "version": record.version,
            "description": record.description or "No description provided.",
            "author": record.author,
            "state": str(record.state),
            "commands": cmd_names,
            "command_details": [
                {"name": c.name, "usage": c.usage or c.name, "description": c.description}
                for c in commands
                if not c.hidden
            ],
            "help_md": self._load_module_help_md(record),
        }

    @staticmethod
    def chunk_message(text: str, limit: int = 1900) -> list[str]:
        """Splits text into Discord-safe chunks, preserving line boundaries."""
        if not text:
            return []
        chunks: list[str] = []
        current = ""
        for line in text.splitlines(keepends=True):
            while len(line) > limit:
                if current:
                    chunks.append(current)
                    current = ""
                chunks.append(line[:limit])
                line = line[limit:]
            if len(current) + len(line) > limit:
                chunks.append(current)
                current = line
            else:
                current += line
        if current:
            chunks.append(current)
        return chunks

    async def get_available_commands(
        self,
        ctx: Any = None,
        filter_permissions: bool | None = None,
    ) -> dict[str, list[CommandInfo]]:
        """Returns registered commands grouped by Module display name.

        Hidden commands and commands from disabled modules are omitted.
        """
        if filter_permissions is None:
            filter_permissions = self.bot.config.help.hide_unavailable_commands

        grouped: dict[str, list[CommandInfo]] = {}

        for cmd in self.bot.command_registry.get_all_commands():
            if cmd.hidden:
                continue

            if ctx is not None and filter_permissions:
                can_run = await self.bot.permissions.can_run_command(ctx, cmd)
                if not can_run:
                    continue

            group_name = cmd.module
            if cmd.module != "Core":
                mod_record = self.bot.module_manager.get_module(cmd.module)
                if mod_record:
                    if mod_record.state != ModuleState.ENABLED:
                        continue
                    if mod_record.manifest:
                        group_name = mod_record.manifest.name

            if group_name not in grouped:
                grouped[group_name] = []
            grouped[group_name].append(cmd)

        for group in grouped:
            grouped[group].sort(key=lambda c: c.name)

        return grouped

    def search_help(self, query: str) -> list[CommandInfo]:
        """Searches commands by keyword matching against name, aliases, description, and category."""
        term = query.lower().strip()
        if not term:
            return []

        results: list[CommandInfo] = []
        for cmd in self.bot.command_registry.get_all_commands():
            if cmd.hidden:
                continue

            matches_name = term in cmd.name.lower()
            matches_alias = any(term in a.lower() for a in cmd.aliases)
            matches_desc = term in cmd.description.lower()
            matches_cat = term in cmd.category.lower()

            if matches_name or matches_alias or matches_desc or matches_cat:
                results.append(cmd)

        results.sort(key=lambda c: c.name)
        return results

    def format_overview(self, grouped_commands: dict[str, list[CommandInfo]], prefix: str) -> str:
        """Formats the grouped commands into a clean Discord message string."""
        lines = ["```text", "Available Commands", ""]

        sorted_groups = sorted(
            grouped_commands.keys(),
            key=lambda g: ("" if g == "Core" else g),
        )

        for group in sorted_groups:
            cmds = grouped_commands[group]
            if not cmds:
                continue
            lines.append(f"[{group}]")
            lines.extend(c.name for c in cmds)
            lines.append("")

        lines.append("자세한 사용법:")
        lines.append(f"{prefix}help <command>")
        lines.append(f"{prefix}help <module>")
        lines.append("```")
        return "\n".join(lines)

    def format_command_detail(self, data: dict[str, Any], prefix: str) -> str:
        """Formats single command help details."""
        lines = [
            "```text",
            data["name"],
            "",
            "설명",
            data["description"],
            "",
            "사용법",
            f"{prefix}{data['usage']}",
            "",
            "Aliases",
            ", ".join(data["aliases"]) if data["aliases"] else "None",
            "",
            "예시",
        ]

        if data["examples"]:
            for ex in data["examples"]:
                lines.append(f"{prefix}{ex}")
        else:
            lines.append(f"{prefix}{data['name']}")

        lines.extend([
            "",
            "필요 권한",
            ", ".join(data["permissions"]) if data["permissions"] else "None",
            "",
            "Module",
            data["module"],
            "```",
        ])
        return "\n".join(lines)

    def format_module_usage(self, data: dict[str, Any], prefix: str) -> str:
        """Formats a compact usage-only summary for a module."""
        lines = [
            "```text",
            f"{data['name']} v{data['version']}",
            "",
        ]
        details = data.get("command_details", [])
        if details:
            for c in details:
                lines.append(f"{prefix}{c.get('usage') or c.get('name', '')}")
        else:
            lines.append("No commands")
        lines.append("")
        lines.append(f"{prefix}help module {data['id']} full  (자세히)")
        lines.append("```")
        return "\n".join(lines)

    def format_module_detail(self, data: dict[str, Any]) -> str:
        """Formats module information."""
        lines = [
            "```text",
            f"Module: {data['name']}",
            "",
            f"ID: {data['id']}",
            f"Version: {data['version']}",
            f"Author: {data['author']}",
            f"Status: {data['state']}",
            "",
            "설명",
            data["description"],
            "",
            "포함된 Command",
        ]

        if data["commands"]:
            for cmd in data["commands"]:
                lines.append(f"- {cmd}")
        else:
            lines.append("None")

        lines.append("```")
        return "\n".join(lines)
