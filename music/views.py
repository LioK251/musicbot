"""
Модуль интерактивных компонентов Discord UI (Select Menus, Action Rows, Buttons).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable
import discord
from discord import ui
from core.checks import is_user_in_same_voice
from music.queue import LoopMode

if TYPE_CHECKING:
    from music.player import MusicPlayer


class SongSelectDropdown(ui.Select):
    """Выпадающий список с топ-5 результатами поиска."""

    def __init__(self, tracks: list[dict[str, Any]], callback_coro: Callable[[discord.Interaction, dict[str, Any]], Any]):
        self.tracks = tracks
        self.on_select_callback = callback_coro

        options = []
        for i, item in enumerate(tracks, 1):
            clean_title = " ".join(item.get("title", f"Трек #{i}").split())[:80] or f"Трек #{i}"
            clean_desc = " ".join(f"{item.get('uploader', 'Неизвестно')} • {item.get('duration_str', '')}".split())[:90]
            options.append(
                discord.SelectOption(
                    label=f"{i}. {clean_title}"[:100],
                    description=clean_desc,
                    value=str(i - 1),
                    emoji="🎵",
                )
            )

        super().__init__(
            placeholder="Выберите трек для воспроизведения...",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        idx = int(self.values[0])
        selected_track = self.tracks[idx]
        await self.on_select_callback(interaction, selected_track)


class SongSelectView(ui.View):
    """Интерфейс выбора трека из поиска с возможностью отмены."""

    def __init__(
        self,
        tracks: list[dict[str, Any]],
        author: discord.Member,
        callback_coro: Callable[[discord.Interaction, dict[str, Any]], Any],
        timeout: float = 60.0,
    ):
        super().__init__(timeout=timeout)
        self.author = author
        self.callback_coro = callback_coro
        self.selected: dict[str, Any] | None = None

        # Добавляем выпадающий список
        self.dropdown = SongSelectDropdown(tracks, self._handle_selection)
        self.add_item(self.dropdown)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(
                "❌ Только автор запроса может сделать выбор!", ephemeral=True
            )
            return False
        return True

    async def _handle_selection(self, interaction: discord.Interaction, track_data: dict[str, Any]) -> None:
        self.selected = track_data
        self.stop()
        await self.callback_coro(interaction, track_data)

    @ui.button(label="Отмена", style=discord.ButtonStyle.danger, emoji="✖️", row=1)
    async def cancel_button(self, interaction: discord.Interaction, button: ui.Button) -> None:
        self.stop()
        embed = discord.Embed(
            description="🚫 Выбор трека отменен.",
            color=discord.Color.dark_grey(),
        )
        await interaction.response.edit_message(embed=embed, view=None)

    async def on_timeout(self) -> None:
        # При истечении времени отключаем элементы
        for item in self.children:
            item.disabled = True


class PlayerControlView(ui.View):
    """
    Интерактивная панель кнопок под сообщением Now Playing:
    - ⏯ Пауза / Возобновить
    - ⏭ Пропустить
    - 🔁 Зацикливание (Off / Track / Queue)
    - ⏹ Стоп (Очистка и выход)
    """

    def __init__(self, player: MusicPlayer):
        super().__init__(timeout=None)
        self.player = player
        self.update_buttons()

    def update_buttons(self) -> None:
        """Синхронизирует состояние кнопок со статусом плеера."""
        voice = self.player.voice_client

        # 1. Кнопка Пауза / Возобновить
        if voice and voice.is_paused():
            self.pause_resume_btn.emoji = "▶️"
            self.pause_resume_btn.label = "Возобновить"
            self.pause_resume_btn.style = discord.ButtonStyle.success
        else:
            self.pause_resume_btn.emoji = "⏸️"
            self.pause_resume_btn.label = "Пауза"
            self.pause_resume_btn.style = discord.ButtonStyle.secondary

        # 2. Кнопка Режима зацикливания
        mode = self.player.queue.loop_mode
        self.loop_btn.emoji = mode.emoji
        self.loop_btn.label = f"Цикл: {mode.value}" if mode != LoopMode.OFF else "Цикл"
        if mode != LoopMode.OFF:
            self.loop_btn.style = discord.ButtonStyle.primary
        else:
            self.loop_btn.style = discord.ButtonStyle.secondary

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Проверяет, находится ли пользователь в одном голосовом канале с ботом."""
        if not is_user_in_same_voice(interaction):
            await interaction.response.send_message(
                "❌ Вы должны находиться в одном голосовом канале с ботом, чтобы управлять плеером!",
                ephemeral=True,
            )
            return False
        return True

    @ui.button(label="Пауза", style=discord.ButtonStyle.secondary, emoji="⏸️", row=0)
    async def pause_resume_btn(self, interaction: discord.Interaction, button: ui.Button) -> None:
        """Переключает воспроизведение/паузу."""
        voice = self.player.voice_client
        if not voice:
            await interaction.response.send_message("❌ Бот не подключен к войсу.", ephemeral=True)
            return

        if voice.is_paused():
            voice.resume()
            action_desc = "▶️ Возобновлено"
        elif voice.is_playing():
            voice.pause()
            action_desc = "⏸️ На паузе"
        else:
            action_desc = ""

        self.update_buttons()
        # Обновляем сообщение с Embed и кнопками
        embed = self.player.build_now_playing_embed(status_text=action_desc)
        await interaction.response.edit_message(embed=embed, view=self)

    @ui.button(label="Скип", style=discord.ButtonStyle.primary, emoji="⏭️", row=0)
    async def skip_btn(self, interaction: discord.Interaction, button: ui.Button) -> None:
        """Пропускает текущий трек."""
        voice = self.player.voice_client
        if not voice or not (voice.is_playing() or voice.is_paused()):
            await interaction.response.send_message("❌ Сейчас ничего не играет для пропуска.", ephemeral=True)
            return

        skipped_track = self.player.skip()
        track_title = skipped_track.title if skipped_track else "Трек"

        await interaction.response.send_message(
            f"⏭️ **{interaction.user.display_name}** пропустил: **{track_title}**",
            delete_after=4,
        )

    @ui.button(label="Цикл", style=discord.ButtonStyle.secondary, emoji="➡️", row=0)
    async def loop_btn(self, interaction: discord.Interaction, button: ui.Button) -> None:
        """Переключает зацикливание трека или очереди."""
        new_mode = self.player.queue.cycle_loop_mode()
        self.update_buttons()

        embed = self.player.build_now_playing_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @ui.button(label="Стоп", style=discord.ButtonStyle.danger, emoji="⏹️", row=0)
    async def stop_btn(self, interaction: discord.Interaction, button: ui.Button) -> None:
        """Останавливает воспроизведение, очищает очередь и выходит из голосового канала."""
        # Отключаем все кнопки
        for item in self.children:
            item.disabled = True

        embed = discord.Embed(
            title="⏹️ Воспроизведение остановлено",
            description=f"Плеер был остановлен участником **{interaction.user.display_name}**.\nОчередь очищена, бот покинул голосовой канал.",
            color=discord.Color.dark_red(),
        )
        await interaction.response.edit_message(embed=embed, view=self)
        await self.player.stop(disconnect=True)


class QueuePaginationView(ui.View):
    """Интерфейс пагинации списка очереди (/queue)."""

    def __init__(self, pages: list[discord.Embed], author: discord.Member, timeout: float = 120.0):
        super().__init__(timeout=timeout)
        self.pages = pages
        self.author = author
        self.current_page = 0
        self._update_buttons()

    def _update_buttons(self) -> None:
        self.prev_btn.disabled = self.current_page == 0
        self.next_btn.disabled = self.current_page >= len(self.pages) - 1

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("❌ Управлять страницами может только автор команды.", ephemeral=True)
            return False
        return True

    @ui.button(label="◀ Назад", style=discord.ButtonStyle.secondary)
    async def prev_btn(self, interaction: discord.Interaction, button: ui.Button) -> None:
        if self.current_page > 0:
            self.current_page -= 1
            self._update_buttons()
            await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)

    @ui.button(label="Вперед ▶", style=discord.ButtonStyle.secondary)
    async def next_btn(self, interaction: discord.Interaction, button: ui.Button) -> None:
        if self.current_page < len(self.pages) - 1:
            self.current_page += 1
            self._update_buttons()
            await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)

    @ui.button(label="Закрыть", style=discord.ButtonStyle.danger, emoji="✖️")
    async def close_btn(self, interaction: discord.Interaction, button: ui.Button) -> None:
        self.stop()
        await interaction.response.edit_message(view=None)

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True
