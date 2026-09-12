"""Plugcord - Modular Discord Bot Bootstrap Entrypoint."""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from pathlib import Path

from core.bot import PlugcordBot
from core.config_manager import ConfigManager
from core.logger import setup_logger


def setup_signal_handlers(bot: PlugcordBot, loop: asyncio.AbstractEventLoop) -> None:
    """Configures graceful termination signal handlers for Unix and Windows."""
    def handle_signal(sig_name: str) -> None:
        logging.getLogger("plugcord").info(f"Received termination signal: {sig_name}. Initiating graceful shutdown...")
        loop.create_task(bot.close())

    if sys.platform != "win32":
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, lambda s=sig: handle_signal(s.name))
            except NotImplementedError:
                pass


async def main() -> None:
    """Initializes and runs the Plugcord Discord Bot."""
    base_dir = Path(__file__).resolve().parent

    config_path = base_dir / "config" / "config.yaml"
    env_path = base_dir / ".env"
    config_mgr = ConfigManager(config_path=config_path, env_path=env_path)
    config = config_mgr.load()

    log_file = base_dir / config.logging.file
    logger = setup_logger(
        name="plugcord",
        log_level=config.logging.level,
        log_file=log_file,
        max_bytes=config.logging.max_bytes,
        backup_count=config.logging.backup_count,
    )

    logger.info("Starting Plugcord Framework...")
    logger.info(f"Loaded configuration from {config_path}")

    token = config.token
    if not token:
        logger.critical(
            "DISCORD_TOKEN is missing or empty! Please set DISCORD_TOKEN in your .env file."
        )
        sys.exit(1)

    bot = PlugcordBot(config=config)

    loop = asyncio.get_running_loop()
    setup_signal_handlers(bot, loop)

    try:
        logger.info("Connecting to Discord Gateway...")
        await bot.start(token)
    except asyncio.CancelledError:
        logger.info("Event loop cancelled, closing...")
    except Exception as e:
        logger.critical(f"Fatal error running bot: {e}", exc_info=True)
    finally:
        if not bot.is_closed():
            await bot.close()
        logger.info("Plugcord has terminated.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
