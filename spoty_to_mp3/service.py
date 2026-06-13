"""Orchestrates a conversion job: resolve link -> download -> package.

A single track produces one MP3; a playlist or album produces a ZIP of MP3s.
Progress is reported back through the JobRegistry so the UI can poll it.
"""

from __future__ import annotations

import re
import time
import zipfile
from pathlib import Path

from .config import Config
from .downloader import Downloader, DownloadError
from .jobs import JobRegistry, JobStatus
from .spotify_client import LinkKind, SpotifyClient, SpotifyError


def _safe_name(name: str) -> str:
    """Filesystem-safe version of an arbitrary name."""
    safe = re.sub(r'[\\/:*?"<>|]', "_", name).strip()
    return safe or "spotify_download"


def run_conversion(
    job_id: str,
    url: str,
    config: Config,
    registry: JobRegistry,
    access_token: str | None = None,
) -> None:
    """Execute a conversion job end to end. Intended to run in a thread.

    When ``access_token`` is given (a logged-in user), it is used so the API
    can return the full tracklist of playlists the user owns. Otherwise
    app-only credentials are used (and non-owned playlists fall back to the
    public embed page).
    """
    try:
        registry.update(
            job_id, status=JobStatus.RUNNING, message="Reading Spotify link..."
        )
        if access_token:
            client = SpotifyClient.from_token(access_token)
        else:
            client = SpotifyClient.from_client_credentials(
                config.spotify_client_id, config.spotify_client_secret
            )
        resolved = client.resolve(url)

        registry.update(
            job_id,
            title=resolved.name,
            image_url=resolved.image_url,
            total=len(resolved.tracks),
            started_at=time.time(),
            message=f"Found {len(resolved.tracks)} track(s). Starting download...",
        )

        job_dir = config.download_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        downloader = Downloader(job_dir)

        mp3_paths: list[Path] = []
        failures: list[str] = []
        for index, track in enumerate(resolved.tracks, start=1):
            registry.update(
                job_id,
                message=f"Downloading {index}/{len(resolved.tracks)}: "
                f"{track.search_query}",
            )
            try:
                mp3_paths.append(downloader.download(track))
            except DownloadError as exc:
                failures.append(track.search_query)
                registry.update(job_id, message=f"Skipped: {exc}")
            finally:
                registry.update(job_id, completed=index)

        if not mp3_paths:
            raise DownloadError(
                "None of the tracks could be downloaded. "
                + (f"Failed: {', '.join(failures)}" if failures else "")
            )

        result_path, result_name = _package(resolved, mp3_paths, job_dir)

        done_message = "Done! Your file is ready."
        if failures:
            done_message += f" ({len(failures)} track(s) could not be downloaded.)"
        registry.update(
            job_id,
            status=JobStatus.DONE,
            result_path=result_path,
            result_name=result_name,
            message=done_message,
        )
    except (SpotifyError, DownloadError) as exc:
        registry.update(
            job_id, status=JobStatus.ERROR, error=str(exc), message=str(exc)
        )
    except Exception as exc:  # pragma: no cover - unexpected failures
        registry.update(
            job_id,
            status=JobStatus.ERROR,
            error=f"Unexpected error: {exc}",
            message=f"Unexpected error: {exc}",
        )


def _package(resolved, mp3_paths: list[Path], job_dir: Path) -> tuple[Path, str]:
    """Return (file_path, download_name) for the finished job.

    Single track -> the MP3 itself. Playlist/album -> a ZIP of all MP3s.
    """
    if resolved.kind is LinkKind.TRACK and len(mp3_paths) == 1:
        mp3 = mp3_paths[0]
        return mp3, mp3.name

    zip_name = f"{_safe_name(resolved.name)}.zip"
    zip_path = job_dir / zip_name
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for mp3 in mp3_paths:
            zf.write(mp3, arcname=mp3.name)
    return zip_path, zip_name
