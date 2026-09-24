"""
Главная точка входа для запуска Discord-бота.
Инициализирует бота, регистрирует обработчики ошибок, загружает модули (Cogs) и синхронизирует слэш-команды.
"""

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
    """Кастомный класс Discord-бота с модульной архитектурой Cogs."""

    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True  # Требуется для перехвата ссылок TikTok в чатах
        intents.voice_states = True     # Требуется для отслеживания голосовых каналов
        intents.guilds = True

        super().__init__(
            command_prefix=config.prefix,
            intents=intents,
            help_command=None,  # Используем собственную слэш-команду /help
        )

        # Список когов для автоматической загрузки
        self.initial_extensions: list[str] = [
            "cogs.general",
            "cogs.music",
            "cogs.tiktok",
        ]

    async def setup_hook(self) -> None:
        """Хук инициализации перед подключением к шлюзу Discord."""
        # 0. Проверка и инициализация библиотеки Opus для стабильного звука
        try:
            if not discord.opus.is_loaded():
                discord.opus._load_default()
            logger.info("✓ Аудио-кодек Opus успешно инициализирован.")
        except Exception as opus_err:
            logger.warning(f"Предупреждение Opus: {opus_err}")

        # 1. Привязка глобального обработчика ошибок слэш-команд
        self.tree.on_error = handle_app_command_error

        # 2. Динамическая загрузка расширений (Cogs)
        for ext in self.initial_extensions:
            try:
                await self.load_extension(ext)
                logger.info(f"✓ Модуль '{ext}' успешно загружен.")
            except Exception as e:
                logger.critical(f"✗ Ошибка при загрузке модуля '{ext}': {e}", exc_info=True)

        # 3. Синхронизация слэш-команд
        if config.guild_id:
            guild = discord.Object(id=config.guild_id)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            logger.info(f"Синхронизировано {len(synced)} слэш-команд для тестовой гильдии ID: {config.guild_id}")
        else:
            synced = await self.tree.sync()
            logger.info(f"Глобально синхронизировано {len(synced)} слэш-команд.")

    async def on_ready(self) -> None:
        """Событие успешной авторизации и готовности бота."""
        logger.info("=" * 60)
        logger.info(f"Бот успешно запущен как: {self.user} (ID: {self.user.id})")
        logger.info(f"Подключено серверов: {len(self.guilds)}")
        logger.info("=" * 60)

        # Устанавливаем статус присутствия
        activity = discord.Activity(
            type=discord.ActivityType.listening,
            name="/play | TikTok автозамена",
        )
        await self.change_presence(status=discord.Status.online, activity=activity)

    async def close(self) -> None:
        """Корректное завершение работы бота с отключением от всех голосовых каналов."""
        logger.info("Завершение работы бота: отключение от голосовых каналов...")
        for vc in self.voice_clients:
            try:
                await vc.disconnect(force=True)
            except Exception:
                pass
        await super().close()
        logger.info("Бот успешно остановлен.")


def main() -> None:
    """Точка входа запуска."""
    # Проверка наличия и валидности конфигурации
    try:
        config.validate()
    except ValueError as e:
        logger.error(str(e))
        print("\n" + "=" * 70)
        print("ОШИБКА КОНФИГУРАЦИИ:")
        print(str(e))
        print("=" * 70 + "\n")
        sys.exit(1)

    bot = MusicDiscordBot()

    # Запуск бота
    try:
        bot.run(config.token, log_handler=None)
    except discord.LoginFailure:
        logger.critical("Неверный токен Discord! Проверьте значение DISCORD_TOKEN в файле .env.")
    except Exception as e:
        logger.critical(f"Критическая ошибка при запуске бота: {e}", exc_info=True)


if __name__ == "__main__":
    main()
