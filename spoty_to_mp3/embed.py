"""Read a public playlist's tracklist without a user login.

Spotify's official Web API only returns a playlist's items for playlists the
authenticated user owns or collaborates on; other playlists return 403. So for
public playlists we read the tracklist from Spotify's own front end instead:

1. The embed page (open.spotify.com/embed/playlist/<id>) renders the first
   100 tracks in a JSON blob, and also hands out an anonymous web-player
   access token.
2. That token lets us page through the *full* tracklist via the standard
   playlist-items endpoint, so playlists longer than 100 tracks come back
   complete. If that call is unavailable (e.g. rate limited), we fall back to
   the 100 tracks already present on the embed page.

Note: this reads only public, link-accessible metadata (track titles and
artist names) that Spotify's own embed already exposes to anyone.
"""

from __future__ import annotations

import json
import re
import time

import requests

from .spotify_client import LinkKind, ResolvedLink, SpotifyError, Track

_EMBED_URL = "https://open.spotify.com/embed/playlist/{id}"
_TRACKS_URL = "https://api.spotify.com/v1/playlists/{id}/tracks"
# Tolerant of extra/reordered attributes on the script tag.
_NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',
    re.DOTALL,
)
_TOKEN_RE = re.compile(r'"accessToken"\s*:\s*"([^"]+)"')
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; spoty-to-mp3/1.0)"}
_ATTEMPTS = 4
_PAGE_LIMIT = 100
# Don't honour absurd Retry-After values (Spotify can return hours); past this
# we give up on the API and fall back to the embed's first 100 tracks.
_MAX_BACKOFF_SECONDS = 8


def resolve_playlist_via_embed(playlist_id: str) -> ResolvedLink:
    """Resolve a public playlist's full tracklist."""
    name, token, embed_tracks = _read_embed(playlist_id)

    # Try to page the full list with the anonymous token. Fall back to the
    # embed's first 100 if it's unavailable.
    full = _fetch_all_tracks(playlist_id, token) if token else None
    tracks = full if full else embed_tracks

    if not tracks:
        raise SpotifyError("That playlist appears to have no public tracks.")
    return ResolvedLink(kind=LinkKind.PLAYLIST, name=name, tracks=tracks)


def _read_embed(playlist_id: str) -> tuple[str, str | None, list[Track]]:
    """Return (name, anon_token, first_100_tracks) from the embed page."""
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
        if not match:
            last_problem = "data blob missing from page"
            continue
        try:
            data = json.loads(match.group(1))
            entity = data["props"]["pageProps"]["state"]["data"]["entity"]
        except (KeyError, ValueError) as exc:
            raise SpotifyError(
                "The playlist page had an unexpected format."
            ) from exc
        name = entity.get("name") or entity.get("title") or "playlist"
        tracks = [
            t
            for t in (_track_from_embed(i) for i in entity.get("trackList", []))
            if t is not None
        ]
        token_match = _TOKEN_RE.search(resp.text)
        return name, (token_match.group(1) if token_match else None), tracks

    raise SpotifyError(
        f"Couldn't read this playlist after {_ATTEMPTS} tries "
        f"({last_problem}). It may be private or unavailable."
    )


def _fetch_all_tracks(playlist_id: str, token: str) -> list[Track] | None:
    """Page the full tracklist via the anonymous token, or None on failure."""
    url = _TRACKS_URL.format(id=playlist_id)
    headers = {**_HEADERS, "Authorization": f"Bearer {token}"}
    fields = "items(track(name,artists(name),duration_ms)),next"
    tracks: list[Track] = []
    offset = 0
    while True:
        page = _get_page(url, headers, fields, offset)
        if page is None:
            # Unavailable (e.g. rate limited): signal fallback unless we've
            # already gathered a full set on earlier pages.
            return tracks or None
        for item in page.get("items", []):
            track = _track_from_api(item.get("track"))
            if track is not None:
                tracks.append(track)
        if not page.get("next"):
            break
        offset += _PAGE_LIMIT
    return tracks or None


def _get_page(url, headers, fields, offset) -> dict | None:
    """Fetch one page, honouring brief Retry-After backoff. None to fall back."""
    params = {"offset": offset, "limit": _PAGE_LIMIT, "fields": fields}
    for _ in range(3):
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=30)
        except requests.RequestException:
            return None
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code == 429:
            wait = int(resp.headers.get("Retry-After", "1") or "1")
            if wait > _MAX_BACKOFF_SECONDS:
                return None  # throttled too long; fall back to embed's 100
            time.sleep(wait)
            continue
        return None
    return None


def _track_from_embed(item: dict) -> Track | None:
    title = item.get("title")
    if not title:
        return None
    artists = [a.strip() for a in (item.get("subtitle") or "").split(",") if a.strip()]
    return Track(
        title=title,
        artists=artists or ["Unknown Artist"],
        album="",
        duration_ms=int(item.get("duration") or 0),
    )


def _track_from_api(node: dict | None) -> Track | None:
    if not node or not node.get("name"):
        return None
    artists = [a["name"] for a in node.get("artists", []) if a.get("name")]
    return Track(
        title=node["name"],
        artists=artists or ["Unknown Artist"],
        album="",
        duration_ms=int(node.get("duration_ms") or 0),
    )
