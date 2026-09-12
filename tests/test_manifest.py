"""Unit tests for module manifest parsing and validation."""

import pytest

from core.exceptions import InvalidManifestError
from core.models.module import ModuleManifest


def test_valid_manifest():
    data = {
        "id": "monitoring",
        "name": "Server Monitoring",
        "version": "1.0.0",
        "description": "Linux server metrics monitor.",
        "author": "Sihwan Lee",
        "custom_extra_key": "custom_value",
    }
    manifest = ModuleManifest.from_dict(data, module_dir_name="monitoring")
    assert manifest.id == "monitoring"
    assert manifest.name == "Server Monitoring"
    assert manifest.version == "1.0.0"
    assert manifest.description == "Linux server metrics monitor."
    assert manifest.author == "Sihwan Lee"
    assert manifest.extra.get("custom_extra_key") == "custom_value"


@pytest.mark.parametrize(
    "missing_field",
    ["id", "name", "version", "description"],
)
def test_missing_required_fields_raise_error(missing_field: str):
    data = {
        "id": "test_mod",
        "name": "Test Mod",
        "version": "1.0.0",
        "description": "Test description",
    }
    del data[missing_field]

    with pytest.raises(InvalidManifestError) as exc_info:
        ModuleManifest.from_dict(data)
    assert "Missing required fields" in str(exc_info.value)


def test_directory_name_mismatch_raises_error():
    data = {
        "id": "mod_a",
        "name": "Module A",
        "version": "1.0.0",
        "description": "Description",
    }
    with pytest.raises(InvalidManifestError) as exc_info:
        ModuleManifest.from_dict(data, module_dir_name="mod_b")
    assert "does not match directory name" in str(exc_info.value)


@pytest.mark.parametrize(
    "bad_id",
    ["invalid id with space", "bad$id", "hello/world", ""],
)
def test_invalid_id_characters_raise_error(bad_id: str):
    data = {
        "id": bad_id,
        "name": "Test Mod",
        "version": "1.0.0",
        "description": "Test description",
    }
    with pytest.raises(InvalidManifestError):
        ModuleManifest.from_dict(data)
