from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
load_dotenv(dotenv_path=ENV_PATH)


@dataclass(frozen=True)
class Config:
    token: str = field(default_factory=lambda: os.getenv("DISCORD_TOKEN", "").strip())
    guild_id: int | None = field(
        default_factory=lambda: (
            int(os.getenv("DISCORD_GUILD_ID"))
            if os.getenv("DISCORD_GUILD_ID", "").strip().isdigit()
            else None
        )
    )
    prefix: str = field(
        default_factory=lambda: os.getenv("BOT_PREFIX", "!").strip() or "!"
    )
    spotify_client_id: str = field(
        default_factory=lambda: os.getenv("SPOTIFY_CLIENT_ID", "").strip()
    )
    spotify_client_secret: str = field(
        default_factory=lambda: os.getenv("SPOTIFY_CLIENT_SECRET", "").strip()
    )
    default_volume: int = field(
        default_factory=lambda: int(os.getenv("DEFAULT_VOLUME", "70"))
    )
    idle_timeout: int = field(
        default_factory=lambda: int(os.getenv("IDLE_TIMEOUT", "300"))
    )
    tiktok_enabled: bool = field(
        default_factory=lambda: os.getenv("TIKTOK_ENABLED", "true").lower() in ("true", "1", "yes")
    )
    tiktok_service: str = field(
        default_factory=lambda: os.getenv("TIKTOK_SERVICE", "vxtiktok.com").strip()
    )
    tiktok_replace_mode: str = field(
        default_factory=lambda: os.getenv("TIKTOK_REPLACE_MODE", "suppress").strip().lower()
    )
    tiktok_send_video: bool = field(
        default_factory=lambda: os.getenv("TIKTOK_SEND_VIDEO", "true").lower() in ("true", "1", "yes")
    )
    tiktok_delete_original: bool = field(
        default_factory=lambda: os.getenv("TIKTOK_DELETE_ORIGINAL", "true").lower() in ("true", "1", "yes")
    )

    def validate(self) -> None:
        if not self.token or self.token == "your_discord_bot_token_here":
            raise ValueError(
                "DISCORD_TOKEN is not set in the .env file!\n"
                "Please configure a valid bot token in .env."
            )

    @property
    def has_spotify_credentials(self) -> bool:
        return bool(
            self.spotify_client_id
            and self.spotify_client_secret
            and self.spotify_client_id != "your_spotify_client_id_here"
            and self.spotify_client_secret != "your_spotify_client_secret_here"
        )


config = Config()
