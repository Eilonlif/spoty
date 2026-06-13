"""Read a public playlist's tracklist from Spotify's embed page.

Spotify's Web API only returns a playlist's items for playlists the
authenticated user owns or collaborates on; other playlists return 403. The
public embed widget (open.spotify.com/embed/playlist/<id>) renders the full
tracklist in a JSON blob with no authentication, so we use it as a fallback
for public playlists the user doesn't own.

Note: this reads only public, link-accessible metadata (track titles and
artist names) that the embed widget already exposes to anyone.
"""

from __future__ import annotations

import json
import re

import requests

from .spotify_client import LinkKind, ResolvedLink, SpotifyError, Track

_EMBED_URL = "https://open.spotify.com/embed/playlist/{id}"
# Tolerant of extra/reordered attributes on the script tag.
_NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',
    re.DOTALL,
)
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; spoty-to-mp3/1.0)"}
_ATTEMPTS = 4


def _fetch_next_data(playlist_id: str) -> str:
    """Fetch the embed page and return the raw __NEXT_DATA__ JSON string.

    The embed CDN occasionally serves a page without the data blob, so retry
    a few times before giving up.
    """
    url = _EMBED_URL.format(id=playlist_id)
    last_problem = "no data"
    for _ in range(_ATTEMPTS):
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as exc:
            last_problem = str(exc)
            continue
        match = _NEXT_DATA_RE.search(resp.text)
        if match:
            return match.group(1)
        last_problem = "data blob missing from page"
    raise SpotifyError(
        f"Couldn't read this playlist after {_ATTEMPTS} tries "
        f"({last_problem}). It may be private or unavailable."
    )


def resolve_playlist_via_embed(playlist_id: str) -> ResolvedLink:
    """Resolve a public playlist's tracks from its embed page."""
    raw = _fetch_next_data(playlist_id)
    try:
        entity = json.loads(raw)["props"]["pageProps"]["state"]["data"]["entity"]
    except (KeyError, ValueError) as exc:
        raise SpotifyError(
            "The playlist page had an unexpected format."
        ) from exc

    name = entity.get("name") or entity.get("title") or "playlist"
    track_list = entity.get("trackList") or []
    tracks: list[Track] = []
    for item in track_list:
        title = item.get("title")
        subtitle = item.get("subtitle") or ""
        if not title:
            continue
        artists = [a.strip() for a in subtitle.split(",") if a.strip()]
        tracks.append(
            Track(
                title=title,
                artists=artists or ["Unknown Artist"],
                album="",
                duration_ms=int(item.get("duration") or 0),
            )
        )

    if not tracks:
        raise SpotifyError("That playlist appears to have no public tracks.")
    return ResolvedLink(kind=LinkKind.PLAYLIST, name=name, tracks=tracks)
