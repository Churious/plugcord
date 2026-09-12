"""Module state, manifest, and runtime representation models."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from core.exceptions import InvalidManifestError


class ModuleState(StrEnum):
    """Lifecycle states of a Plugcord module."""

    INSTALLED = "installed"
    ENABLED = "enabled"
    DISABLED = "disabled"
    ERROR = "error"


MODULE_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")


@dataclass(frozen=True)
class ModuleManifest:
    """Represents a validated module manifest.json."""

    id: str
    name: str
    version: str
    description: str
    author: str = "Unknown"
    min_core_version: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any], module_dir_name: str | None = None) -> ModuleManifest:
        """Validate raw dictionary and construct a ModuleManifest instance.

        Raises:
            InvalidManifestError: If any required field is missing or invalid.
        """
        target_id = module_dir_name or data.get("id", "")

        if not isinstance(data, dict):
            raise InvalidManifestError(target_id, "Manifest root must be a JSON object.")

        required_fields = ["id", "name", "version", "description"]
        missing = [f for f in required_fields if f not in data or data[f] is None]
        if missing:
            raise InvalidManifestError(
                target_id, f"Missing required fields: {', '.join(missing)}"
            )

        mod_id = str(data["id"]).strip()
        if not mod_id:
            raise InvalidManifestError(target_id, "Field 'id' cannot be empty.")

        if not MODULE_ID_PATTERN.match(mod_id):
            raise InvalidManifestError(
                mod_id,
                f"Field 'id' '{mod_id}' contains invalid characters. "
                "Only letters, numbers, underscores, and hyphens are allowed.",
            )

        if module_dir_name and mod_id != module_dir_name:
            raise InvalidManifestError(
                mod_id,
                f"Manifest 'id' ('{mod_id}') does not match directory name ('{module_dir_name}').",
            )

        name = str(data["name"]).strip()
        if not name:
            raise InvalidManifestError(mod_id, "Field 'name' cannot be empty.")

        version = str(data["version"]).strip()
        if not version:
            raise InvalidManifestError(mod_id, "Field 'version' cannot be empty.")

        description = str(data["description"]).strip()
        if not description:
            raise InvalidManifestError(mod_id, "Field 'description' cannot be empty.")

        author = str(data.get("author", "Unknown")).strip() or "Unknown"
        min_core_version = data.get("min_core_version")

        extra = {k: v for k, v in data.items() if k not in required_fields and k not in ("author", "min_core_version")}

        return cls(
            id=mod_id,
            name=name,
            version=version,
            description=description,
            author=author,
            min_core_version=min_core_version,
            extra=extra,
        )


@dataclass
class ModuleRecord:
    """Runtime record representing a discovered or registered module."""

    id: str
    path: Path
    state: ModuleState = ModuleState.INSTALLED
    manifest: ModuleManifest | None = None
    error_message: str | None = None
    loaded_commands: list[str] = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.manifest.name if self.manifest else self.id

    @property
    def version(self) -> str:
        return self.manifest.version if self.manifest else "unknown"

    @property
    def description(self) -> str:
        return self.manifest.description if self.manifest else ""

    @property
    def author(self) -> str:
        return self.manifest.author if self.manifest else "Unknown"
