"""
Модуль очереди воспроизведения треков и управления режимами зацикливания.
"""

from __future__ import annotations

from collections import deque
from enum import Enum
import random
from typing import Iterator

from music.source import Track


class LoopMode(Enum):
    """Режимы зацикливания воспроизведения."""
    OFF = "Выключено"
    TRACK = "Текущий трек"
    QUEUE = "Вся очередь"

    @property
    def emoji(self) -> str:
        """Возвращает соответствующий эмодзи для статуса."""
        if self == LoopMode.TRACK:
            return "🔂"
        elif self == LoopMode.QUEUE:
            return "🔁"
        return "➡️"


class MusicQueue:
    """Управление FIFO очередью треков с поддержкой зацикливания и перемешивания."""

    def __init__(self) -> None:
        self._queue: deque[Track] = deque()
        self._history: list[Track] = []
        self._current: Track | None = None
        self._loop_mode: LoopMode = LoopMode.OFF

    @property
    def current(self) -> Track | None:
        """Текущий воспроизводимый трек."""
        return self._current

    @current.setter
    def current(self, track: Track | None) -> None:
        self._current = track

    @property
    def loop_mode(self) -> LoopMode:
        """Текущий режим зацикливания."""
        return self._loop_mode

    @loop_mode.setter
    def loop_mode(self, mode: LoopMode) -> None:
        self._loop_mode = mode

    def cycle_loop_mode(self) -> LoopMode:
        """Переключает режим зацикливания по кругу: OFF -> TRACK -> QUEUE -> OFF."""
        if self._loop_mode == LoopMode.OFF:
            self._loop_mode = LoopMode.TRACK
        elif self._loop_mode == LoopMode.TRACK:
            self._loop_mode = LoopMode.QUEUE
        else:
            self._loop_mode = LoopMode.OFF
        return self._loop_mode

    def add(self, track: Track) -> None:
        """Добавляет трек в конец очереди."""
        self._queue.append(track)

    def add_next(self, track: Track) -> None:
        """Добавляет трек в начало очереди (следующим)."""
        self._queue.appendleft(track)

    def extend(self, tracks: list[Track]) -> None:
        """Добавляет пачку треков в конец очереди."""
        self._queue.extend(tracks)

    def get_next(self, is_skip: bool = False) -> Track | None:
        """
        Извлекает следующий трек с учетом текущего режима зацикливания:
        - Если был запрошен явный скип (is_skip=True), то даже в режиме TRACK
          текущий трек отправляется в историю (или в очередь при QUEUE) и берется следующий!
        - TRACK (без скипа): повторяет текущий трек.
        - QUEUE: возвращает текущий трек в конец очереди и берет следующий.
        - OFF: сохраняет текущий трек в историю и берет следующий из очереди.
        """
        if self._current:
            if self._loop_mode == LoopMode.TRACK and not is_skip:
                return self._current
            elif self._loop_mode == LoopMode.QUEUE:
                self._queue.append(self._current)
            else:
                self._history.append(self._current)

        if not self._queue:
            self._current = None
            return None

        self._current = self._queue.popleft()
        return self._current

    def force_skip(self) -> Track | None:
        """Принудительно пропускает трек даже при активном LoopMode.TRACK."""
        return self.get_next(is_skip=True)

    def shuffle(self) -> None:
        """Перемешивает треки в очереди в случайном порядке."""
        shuffled = list(self._queue)
        random.shuffle(shuffled)
        self._queue = deque(shuffled)

    def remove(self, index: int) -> Track | None:
        """
        Удаляет трек по 1-индексированному номеру.
        Возвращает удаленный трек или None, если индекс вне диапазона.
        """
        if 1 <= index <= len(self._queue):
            target = self._queue[index - 1]
            del self._queue[index - 1]
            return target
        return None

    def clear(self) -> None:
        """Очищает очередь треков (не останавливая текущий трек)."""
        self._queue.clear()

    @property
    def is_empty(self) -> bool:
        """Проверяет, пуста ли очередь."""
        return len(self._queue) == 0

    @property
    def tracks(self) -> list[Track]:
        """Возвращает список треков в очереди."""
        return list(self._queue)

    def __len__(self) -> int:
        return len(self._queue)

    def __iter__(self) -> Iterator[Track]:
        return iter(self._queue)
