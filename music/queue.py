from __future__ import annotations

from collections import deque
from enum import Enum
import random
from typing import Iterator

from music.source import Track


class LoopMode(Enum):
    OFF = "Off"
    TRACK = "Track"
    QUEUE = "Queue"

    @property
    def emoji(self) -> str:
        if self == LoopMode.TRACK:
            return "🔂"
        elif self == LoopMode.QUEUE:
            return "🔁"
        return "➡️"


class MusicQueue:
    def __init__(self) -> None:
        self._queue: deque[Track] = deque()
        self._history: list[Track] = []
        self._current: Track | None = None
        self._loop_mode: LoopMode = LoopMode.OFF

    @property
    def current(self) -> Track | None:
        return self._current

    @current.setter
    def current(self, track: Track | None) -> None:
        self._current = track

    @property
    def loop_mode(self) -> LoopMode:
        return self._loop_mode

    @loop_mode.setter
    def loop_mode(self, mode: LoopMode) -> None:
        self._loop_mode = mode

    def cycle_loop_mode(self) -> LoopMode:
        if self._loop_mode == LoopMode.OFF:
            self._loop_mode = LoopMode.TRACK
        elif self._loop_mode == LoopMode.TRACK:
            self._loop_mode = LoopMode.QUEUE
        else:
            self._loop_mode = LoopMode.OFF
        return self._loop_mode

    def add(self, track: Track) -> None:
        self._queue.append(track)

    def add_next(self, track: Track) -> None:
        self._queue.appendleft(track)

    def extend(self, tracks: list[Track]) -> None:
        self._queue.extend(tracks)

    def get_next(self, is_skip: bool = False) -> Track | None:
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
        return self.get_next(is_skip=True)

    def shuffle(self) -> None:
        shuffled = list(self._queue)
        random.shuffle(shuffled)
        self._queue = deque(shuffled)

    def remove(self, index: int) -> Track | None:
        if 1 <= index <= len(self._queue):
            target = self._queue[index - 1]
            del self._queue[index - 1]
            return target
        return None

    def clear(self) -> None:
        self._queue.clear()

    @property
    def is_empty(self) -> bool:
        return len(self._queue) == 0

    @property
    def tracks(self) -> list[Track]:
        return list(self._queue)

    def __len__(self) -> int:
        return len(self._queue)

    def __iter__(self) -> Iterator[Track]:
        return iter(self._queue)
