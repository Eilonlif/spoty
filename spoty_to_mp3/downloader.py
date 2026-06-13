"""Find and download a matching audio source for a track, as MP3.

Uses yt-dlp to search a public audio source for the closest match to the
track's "<artist> - <title>" query, downloads the best audio stream, and
lets ffmpeg transcode it to a tagged MP3.
"""

from __future__ import annotations

from pathlib import Path

import yt_dlp

from .spotify_client import Track


class DownloadError(Exception):
    """Raised when a track cannot be downloaded or converted."""


class Downloader:
    """Downloads tracks to MP3 using yt-dlp + ffmpeg."""

    def __init__(
        self, output_dir: Path, audio_quality: str = "192", attempts: int = 3
    ) -> None:
        self.output_dir = output_dir
        self.audio_quality = audio_quality
        self.attempts = max(1, attempts)

    def download(self, track: Track) -> Path:
        """Download a single track and return the path to the MP3.

        Retries a few times on transient failures (network blips, throttling)
        before giving up. Raises DownloadError if every attempt fails.
        """
        last_error: Exception | None = None
        for _ in range(self.attempts):
            try:
                return self._download_once(track)
            except DownloadError as exc:
                last_error = exc
        raise DownloadError(
            f"Couldn't download '{track.search_query}' after "
            f"{self.attempts} attempts: {last_error}"
        )

    def _download_once(self, track: Track) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        stem = track.filename_stem
        outtmpl = str(self.output_dir / f"{stem}.%(ext)s")

        options = {
            "format": "bestaudio/best",
            "outtmpl": outtmpl,
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "default_search": "ytsearch1",
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": self.audio_quality,
                },
                {
                    "key": "FFmpegMetadata",
                },
            ],
            # Embed metadata so the resulting file is properly tagged.
            "postprocessor_args": [
                "-metadata", f"title={track.title}",
                "-metadata", f"artist={track.artist}",
                "-metadata", f"album={track.album}",
            ],
        }

        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                # Searching by the query string triggers default_search.
                ydl.extract_info(track.search_query, download=True)
        except Exception as exc:  # yt-dlp raises a variety of error types
            raise DownloadError(
                f"Couldn't download '{track.search_query}': {exc}"
            ) from exc

        mp3_path = self.output_dir / f"{stem}.mp3"
        if not mp3_path.exists():
            raise DownloadError(
                f"Download finished but no MP3 was produced for "
                f"'{track.search_query}'."
            )
        return mp3_path
