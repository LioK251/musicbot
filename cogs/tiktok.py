from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import tempfile
from typing import Tuple
import discord
from discord import app_commands
from discord.ext import commands
import yt_dlp

from config import config

logger = logging.getLogger("DiscordBot.TikTok")

TIKTOK_REGEX = re.compile(
    r"https?://(?:www\.)?(?:(?:vm|vt)\.tiktok\.com/[\w.-]+/?|tiktok\.com/@[\w.-]+/video/\d+/?|tiktok\.com/t/[\w.-]+/?)(?:\?[^\s<>]*)?",
    re.IGNORECASE,
)


async def download_tiktok_video(url: str, max_size_mb: int = 25) -> Tuple[str | None, str | None]:
    loop = asyncio.get_running_loop()
    temp_dir = tempfile.mkdtemp(prefix="tt_")
    outtmpl = os.path.join(temp_dir, "tiktok_video.%(ext)s")

    ydl_opts = {
        "format": "mp4/bestvideo+bestaudio/best",
        "outtmpl": outtmpl,
        "max_filesize": max_size_mb * 1024 * 1024,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }

    def _extract_and_download() -> str | None:
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            for fname in os.listdir(temp_dir):
                if fname.endswith((".mp4", ".mov", ".webm")):
                    return os.path.join(temp_dir, fname)
            return None
        except Exception as e:
            logger.warning(f"Error downloading TikTok video ({url}): {e}")
            return None

    try:
        file_path = await asyncio.wait_for(loop.run_in_executor(None, _extract_and_download), timeout=18.0)
        if file_path and os.path.exists(file_path):
            return file_path, temp_dir
    except Exception as exc:
        logger.warning(f"TikTok download timed out or failed: {exc}")

    shutil.rmtree(temp_dir, ignore_errors=True)
    return None, None


class TikTokCog(commands.Cog, name="TikTok"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _convert_tiktok_url(self, url: str) -> str:
        service = config.tiktok_service.strip()
        return re.sub(
            r"https?://(?:www\.|vm\.|vt\.)?tiktok\.com",
            f"https://{service}",
            url,
            flags=re.IGNORECASE,
        )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or not message.content:
            return

        if not config.tiktok_enabled:
            return

        matches = TIKTOK_REGEX.findall(message.content)
        if not matches:
            return

        target_url = matches[0]
        logger.info(f"Detected TikTok link in message from {message.author} in #{message.channel}")

        bot_member = message.guild.me if message.guild else None
        can_manage_messages = (
            message.channel.permissions_for(bot_member).manage_messages
            if bot_member and isinstance(message.channel, (discord.TextChannel, discord.Thread))
            else False
        )

        cleaned_text = message.content
        for raw_link in matches:
            cleaned_text = cleaned_text.replace(raw_link, "").strip()

        video_path = None
        temp_dir = None

        try:
            if config.tiktok_send_video:
                video_path, temp_dir = await download_tiktok_video(target_url, max_size_mb=25)

            caption = f"📱 **TikTok** • {message.author.mention}"
            if cleaned_text:
                caption += f"\n> {cleaned_text}"

            if video_path and os.path.exists(video_path):
                if can_manage_messages and config.tiktok_delete_original:
                    try:
                        await message.delete()
                    except Exception:
                        pass
                elif can_manage_messages:
                    try:
                        await message.edit(suppress=True)
                    except Exception:
                        pass

                with open(video_path, "rb") as fp:
                    discord_file = discord.File(fp, filename="tiktok.mp4")
                    await message.channel.send(content=caption, file=discord_file)

            else:
                converted = self._convert_tiktok_url(target_url)
                if can_manage_messages and config.tiktok_delete_original:
                    try:
                        await message.delete()
                    except Exception:
                        pass
                    fallback_text = f"📱 {message.author.mention}: {converted}"
                    if cleaned_text:
                        fallback_text = f"📱 {message.author.mention}: {cleaned_text}\n{converted}"
                    await message.channel.send(fallback_text)
                else:
                    if can_manage_messages:
                        try:
                            await message.edit(suppress=True)
                        except Exception:
                            pass
                    await message.reply(f"📱 {converted}", mention_author=False)

        except Exception as e:
            logger.error(f"Error processing TikTok video: {e}", exc_info=True)
        finally:
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)

    @app_commands.command(name="tiktok", description="Download and send TikTok video directly to chat")
    @app_commands.describe(url="TikTok video link")
    async def tiktok_command(self, interaction: discord.Interaction, url: str) -> None:
        url = url.strip()
        match = TIKTOK_REGEX.search(url)
        if not match:
            await interaction.response.send_message(
                "❌ Invalid TikTok video link.",
                ephemeral=True,
            )
            return

        await interaction.response.defer()
        target_url = match.group(0)

        video_path, temp_dir = await download_tiktok_video(target_url, max_size_mb=25)
        try:
            if video_path and os.path.exists(video_path):
                with open(video_path, "rb") as fp:
                    discord_file = discord.File(fp, filename="tiktok.mp4")
                    await interaction.followup.send(
                        content=f"📱 **TikTok** (requested by {interaction.user.mention})",
                        file=discord_file,
                    )
            else:
                converted_url = self._convert_tiktok_url(target_url)
                await interaction.followup.send(
                    f"📱 {interaction.user.mention}: {converted_url}"
                )
        finally:
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(TikTokCog(bot))
