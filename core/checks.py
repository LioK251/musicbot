from __future__ import annotations

import discord
from discord import app_commands
from core.errors import (
    NotConnectedToVoice,
    BotNotConnectedToVoice,
    DifferentVoiceChannel,
    MissingVoicePermissions,
)


def ensure_voice_connection(check_bot_connected: bool = False, require_same_channel: bool = True):
    async def predicate(interaction: discord.Interaction) -> bool:
        if not interaction.guild:
            await interaction.response.send_message("❌ This command is only available in a server!", ephemeral=True)
            return False

        user: discord.Member = interaction.user
        if not user.voice or not user.voice.channel:
            raise NotConnectedToVoice()

        user_channel = user.voice.channel
        bot_voice: discord.VoiceClient | None = interaction.guild.voice_client

        if check_bot_connected and not bot_voice:
            raise BotNotConnectedToVoice()

        if bot_voice and require_same_channel:
            if bot_voice.channel.id != user_channel.id:
                raise DifferentVoiceChannel(
                    f"You must be in the channel **{bot_voice.channel.name}** where the bot is currently playing!"
                )

        bot_member = interaction.guild.me
        permissions = user_channel.permissions_for(bot_member)
        if not permissions.connect or not permissions.speak:
            raise MissingVoicePermissions()

        return True

    return app_commands.check(predicate)


def is_user_in_same_voice(interaction: discord.Interaction) -> bool:
    if not interaction.guild:
        return False

    bot_voice: discord.VoiceClient | None = interaction.guild.voice_client
    if not bot_voice or not bot_voice.channel:
        return False

    user: discord.Member = interaction.user
    if not user.voice or not user.voice.channel:
        return False

    return user.voice.channel.id == bot_voice.channel.id
