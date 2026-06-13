"""Application configuration, loaded from environment / .env file."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Load variables from a local .env file if present. Real environment
# variables always take precedence over the file.
load_dotenv()

# Project root (the directory that contains this package).
ROOT_DIR = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Config:
    """Resolved application settings."""

    spotify_client_id: str
    spotify_client_secret: str
    download_dir: Path
    host: str
    port: int
    debug: bool

    @property
    def spotify_configured(self) -> bool:
        """True when both Spotify credentials are present."""
        return bool(self.spotify_client_id and self.spotify_client_secret)


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def load_config() -> Config:
    """Build a Config from the current environment."""
    download_dir = Path(os.getenv("DOWNLOAD_DIR", ROOT_DIR / "downloads"))
    if not download_dir.is_absolute():
        download_dir = ROOT_DIR / download_dir
    download_dir.mkdir(parents=True, exist_ok=True)

    return Config(
        spotify_client_id=os.getenv("SPOTIFY_CLIENT_ID", "").strip(),
        spotify_client_secret=os.getenv("SPOTIFY_CLIENT_SECRET", "").strip(),
        download_dir=download_dir,
        host=os.getenv("FLASK_HOST", "127.0.0.1"),
        port=int(os.getenv("FLASK_PORT", "5000")),
        debug=_as_bool(os.getenv("FLASK_DEBUG"), default=False),
    )
