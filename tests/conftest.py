"""Pytest fixtures and test setup for Plugcord test suite."""

from __future__ import annotations

import tempfile
from collections.abc import AsyncGenerator, Generator
from pathlib import Path

import pytest
import pytest_asyncio

from core.bot import PlugcordBot
from core.config_manager import (
    Config,
    DatabaseConfig,
    DiscordConfig,
    HelpConfig,
    LoggingConfig,
    ModulesConfig,
)
from core.database import Database


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Provides a temporary directory that is automatically cleaned up."""
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp)


@pytest.fixture
def test_config(temp_dir: Path) -> Config:
    """Generates a test configuration pointing to the temporary directory."""
    db_path = temp_dir / "test_plugcord.db"
    log_path = temp_dir / "test_plugcord.log"
    modules_path = temp_dir / "test_modules"
    modules_path.mkdir(parents=True, exist_ok=True)

    return Config(
        discord=DiscordConfig(prefix="!", owners=[111222333444555666]),
        modules=ModulesConfig(auto_restore=True, directory=str(modules_path)),
        help=HelpConfig(hide_unavailable_commands=True),
        logging=LoggingConfig(level="DEBUG", file=str(log_path)),
        database=DatabaseConfig(path=str(db_path)),
        token="TEST_MOCK_TOKEN",
    )


@pytest_asyncio.fixture
async def test_db(temp_dir: Path) -> AsyncGenerator[Database, None]:
    """Initializes a temporary SQLite database for testing."""
    db_path = temp_dir / "test_db.db"
    db = Database(db_path=db_path)
    await db.connect()
    yield db
    await db.close()


@pytest.fixture
def mock_bot(test_config: Config) -> PlugcordBot:
    """Creates a PlugcordBot instance with test config (without gateway login)."""
    bot = PlugcordBot(config=test_config)
    return bot
