from __future__ import annotations

import logging
import discord
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger("DiscordBot.Errors")


class MusicBotException(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class NotConnectedToVoice(MusicBotException):
    def __init__(self, message: str = "You must be connected to a voice channel to use this command!"):
        super().__init__(message)


class BotNotConnectedToVoice(MusicBotException):
    def __init__(self, message: str = "The bot is not connected to any voice channel!"):
        super().__init__(message)


class DifferentVoiceChannel(MusicBotException):
    def __init__(self, message: str = "You must be in the same voice channel as the bot!"):
        super().__init__(message)


class MissingVoicePermissions(MusicBotException):
    def __init__(self, message: str = "The bot lacks CONNECT or SPEAK permissions in this channel!"):
        super().__init__(message)


class TrackFetchError(MusicBotException):
    def __init__(self, message: str = "Failed to fetch track audio stream. The video may be unavailable or restricted."):
        super().__init__(message)


class QueueEmptyError(MusicBotException):
    def __init__(self, message: str = "The playback queue is currently empty!"):
        super().__init__(message)


class SpotifyConfigError(MusicBotException):
    def __init__(self, message: str = "Spotify API is not configured (SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET required in .env)."):
        super().__init__(message)


async def handle_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
    if isinstance(error, app_commands.CommandInvokeError):
        error = error.original

    if isinstance(error, MusicBotException):
        cmd = f"/{interaction.command.name}" if interaction.command else "unknown"
        user_info = f"{interaction.user} (ID: {interaction.user.id})"
        guild_info = f"{interaction.guild.name} (ID: {interaction.guild.id})" if interaction.guild else "DM"
        logger.warning(f"Error in command {cmd} by {user_info} in {guild_info}: {error.message}")
        embed = discord.Embed(
            title="⚠️ Notice",
            description=error.message,
            color=discord.Color.gold(),
        )
    elif isinstance(error, app_commands.MissingPermissions):
        missing = ", ".join(error.missing_permissions)
        embed = discord.Embed(
            title="⛔ Missing Permissions",
            description=f"You are missing the following permissions: **{missing}**",
            color=discord.Color.red(),
        )
    elif isinstance(error, app_commands.BotMissingPermissions):
        missing = ", ".join(error.missing_permissions)
        embed = discord.Embed(
            title="⛔ Bot Missing Permissions",
            description=f"The bot requires the following permissions: **{missing}**",
            color=discord.Color.red(),
        )
    elif isinstance(error, app_commands.CommandOnCooldown):
        embed = discord.Embed(
            title="⏳ Command Cooldown",
            description=f"Please wait **{error.retry_after:.1f}s** before using this command again.",
            color=discord.Color.orange(),
        )
    else:
        logger.error(f"Unhandled error in command /{interaction.command.name if interaction.command else 'unknown'}: {error}", exc_info=True)
        embed = discord.Embed(
            title="❌ An Error Occurred",
            description=f"An unexpected error occurred while executing the command:\n`{error}`",
            color=discord.Color.red(),
        )

    try:
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)
    except Exception as send_err:
        logger.error(f"Failed to send error message to user: {send_err}")
