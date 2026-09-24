from __future__ import annotations

import asyncio
import os
import signal
import sys
import discord
from discord.ext import commands

from config import config
from core.errors import handle_app_command_error
from core.logger import setup_logger

logger = setup_logger("DiscordBot")


class MusicDiscordBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        intents.voice_states = True
        intents.guilds = True

        super().__init__(
            command_prefix=config.prefix,
            intents=intents,
            help_command=None,
        )

        self.initial_extensions: list[str] = [
            "cogs.general",
            "cogs.music",
            "cogs.tiktok",
        ]

    async def setup_hook(self) -> None:
        try:
            if not discord.opus.is_loaded():
                discord.opus._load_default()
            logger.info("✓ Opus audio codec successfully initialized.")
        except Exception as opus_err:
            logger.warning(f"Opus warning: {opus_err}")

        self.tree.on_error = handle_app_command_error

        for ext in self.initial_extensions:
            try:
                await self.load_extension(ext)
                logger.info(f"✓ Module '{ext}' successfully loaded.")
            except Exception as e:
                logger.critical(f"✗ Failed to load module '{ext}': {e}", exc_info=True)

        if config.guild_id:
            guild = discord.Object(id=config.guild_id)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            logger.info(f"Synced {len(synced)} slash commands for guild ID: {config.guild_id}")
        else:
            synced = await self.tree.sync()
            logger.info(f"Globally synced {len(synced)} slash commands.")

    async def on_ready(self) -> None:
        logger.info("=" * 60)
        logger.info(f"Bot logged in as: {self.user} (ID: {self.user.id})")
        logger.info(f"Connected guilds: {len(self.guilds)}")
        logger.info("=" * 60)

        activity = discord.Activity(
            type=discord.ActivityType.listening,
            name="/play | TikTok auto-embed",
        )
        await self.change_presence(status=discord.Status.online, activity=activity)

    async def close(self) -> None:
        logger.info("Shutting down bot: disconnecting from voice channels...")
        for vc in self.voice_clients:
            try:
                await vc.disconnect(force=True)
            except Exception:
                pass
        await super().close()
        logger.info("Bot successfully stopped.")


def main() -> None:
    try:
        config.validate()
    except ValueError as e:
        logger.error(str(e))
        print("\n" + "=" * 70)
        print("CONFIGURATION ERROR:")
        print(str(e))
        print("=" * 70 + "\n")
        sys.exit(1)

    bot = MusicDiscordBot()

    try:
        bot.run(config.token, log_handler=None)
    except discord.LoginFailure:
        logger.critical("Invalid Discord token! Check DISCORD_TOKEN in .env.")
    except Exception as e:
        logger.critical(f"Critical error starting bot: {e}", exc_info=True)


if __name__ == "__main__":
    main()
