"""Unit tests for asynchronous database abstraction."""

import pytest

from core.database import Database


@pytest.mark.asyncio
async def test_database_initialization_and_crud(test_db: Database):
    state = await test_db.get_module_state("unknown_module")
    assert state is None

    await test_db.set_module_state("monitoring", enabled=True, last_status="enabled")
    state = await test_db.get_module_state("monitoring")
    assert state is not None
    assert state["id"] == "monitoring"
    assert state["enabled"] is True
    assert state["last_status"] == "enabled"
    assert "updated_at" in state

    await test_db.set_module_state("monitoring", enabled=False, last_status="disabled")
    state_updated = await test_db.get_module_state("monitoring")
    assert state_updated is not None
    assert state_updated["enabled"] is False
    assert state_updated["last_status"] == "disabled"

    await test_db.set_module_state("docker", enabled=True, last_status="enabled")

    all_mods = await test_db.get_all_modules()
    assert len(all_mods) == 2
    assert "monitoring" in all_mods
    assert "docker" in all_mods

    deleted = await test_db.delete_module_record("monitoring")
    assert deleted is True

    state_after = await test_db.get_module_state("monitoring")
    assert state_after is None
