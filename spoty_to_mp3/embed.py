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
_NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
    re.DOTALL,
)
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; spoty-to-mp3/1.0)"}


def resolve_playlist_via_embed(playlist_id: str) -> ResolvedLink:
    """Resolve a public playlist's tracks from its embed page."""
    url = _EMBED_URL.format(id=playlist_id)
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise SpotifyError(
            f"Couldn't load the playlist's public page: {exc}"
        ) from exc

    match = _NEXT_DATA_RE.search(resp.text)
    if not match:
        raise SpotifyError(
            "Couldn't read this playlist. It may be private or unavailable."
        )

    try:
        entity = (
            json.loads(match.group(1))["props"]["pageProps"]["state"]["data"][
                "entity"
            ]
        )
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
