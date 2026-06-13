"""Resolve a Spotify URL into track metadata using the Spotify Web API.

Spotify does not serve downloadable audio. This module only reads *metadata*
(title, artist, album, duration) so the downloader can find a matching audio
source elsewhere.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

import spotipy
from spotipy.oauth2 import SpotifyClientCredentials


class LinkKind(str, Enum):
    TRACK = "track"
    PLAYLIST = "playlist"
    ALBUM = "album"


@dataclass(frozen=True)
class Track:
    """A single resolved track's metadata."""

    title: str
    artists: list[str]
    album: str
    duration_ms: int

    @property
    def artist(self) -> str:
        return ", ".join(self.artists)

    @property
    def search_query(self) -> str:
        """Query used to find a matching audio source."""
        return f"{self.artist} - {self.title}"

    @property
    def filename_stem(self) -> str:
        """Filesystem-safe base name (no extension)."""
        raw = f"{self.artist} - {self.title}"
        safe = re.sub(r'[\\/:*?"<>|]', "_", raw).strip()
        return safe or "track"


@dataclass(frozen=True)
class ResolvedLink:
    """The outcome of resolving a Spotify URL."""

    kind: LinkKind
    name: str           # track title, or playlist/album name
    tracks: list[Track]


# Matches both open.spotify.com URLs and spotify:track:... URIs.
_LINK_RE = re.compile(
    r"(?:open\.spotify\.com/(?:intl-\w+/)?(?P<kind1>track|playlist|album)/(?P<id1>[A-Za-z0-9]+))"
    r"|(?:spotify:(?P<kind2>track|playlist|album):(?P<id2>[A-Za-z0-9]+))"
)


class SpotifyError(Exception):
    """Raised for invalid links or Spotify API problems."""


def parse_link(url: str) -> tuple[LinkKind, str]:
    """Extract the kind and id from a Spotify URL or URI."""
    match = _LINK_RE.search(url.strip())
    if not match:
        raise SpotifyError(
            "That doesn't look like a Spotify track, playlist, or album link."
        )
    kind = match.group("kind1") or match.group("kind2")
    spotify_id = match.group("id1") or match.group("id2")
    return LinkKind(kind), spotify_id


class SpotifyClient:
    """Thin wrapper around spotipy for the metadata we need.

    Tracks and albums come from the API. Playlists are read from the public
    embed page, except when a logged-in user token is present — then the API
    is tried first so playlists the user owns return their full tracklist
    (the embed caps at 100); non-owned playlists fall back to the embed.
    """

    def __init__(self, sp: "spotipy.Spotify", user_auth: bool = False) -> None:
        self._sp = sp
        self._user_auth = user_auth

    @classmethod
    def from_client_credentials(
        cls, client_id: str, client_secret: str
    ) -> "SpotifyClient":
        if not client_id or not client_secret:
            raise SpotifyError(
                "Spotify credentials are missing. Set SPOTIFY_CLIENT_ID and "
                "SPOTIFY_CLIENT_SECRET in your .env file."
            )
        auth = SpotifyClientCredentials(
            client_id=client_id, client_secret=client_secret
        )
        return cls(spotipy.Spotify(auth_manager=auth), user_auth=False)

    @classmethod
    def from_token(cls, access_token: str) -> "SpotifyClient":
        """Build a client from a logged-in user's access token."""
        return cls(spotipy.Spotify(auth=access_token), user_auth=True)

    def resolve(self, url: str) -> ResolvedLink:
        """Resolve a Spotify URL into its tracks."""
        kind, spotify_id = parse_link(url)
        if kind is LinkKind.PLAYLIST:
            return self._resolve_playlist(spotify_id)
        try:
            if kind is LinkKind.TRACK:
                return self._resolve_track(spotify_id)
            return self._resolve_album(spotify_id)
        except spotipy.SpotifyException as exc:  # pragma: no cover - network
            raise SpotifyError(f"Spotify API error: {exc.msg or exc}") from exc

    # -- per-kind resolvers -------------------------------------------------

    def _resolve_playlist(self, playlist_id: str) -> ResolvedLink:
        from .embed import resolve_playlist_via_embed

        # Logged in: try the API first — playlists the user owns return their
        # full tracklist. Anything the API refuses (403 non-owned, etc.) and
        # the logged-out case both fall back to the public embed page.
        if self._user_auth:
            try:
                return self._resolve_playlist_api(playlist_id)
            except spotipy.SpotifyException:
                pass
        return resolve_playlist_via_embed(playlist_id)

    def _resolve_playlist_api(self, playlist_id: str) -> ResolvedLink:
        name = self._sp.playlist(playlist_id, fields="name").get(
            "name", "playlist"
        )
        tracks: list[Track] = []
        results = self._sp.playlist_items(playlist_id)
        while results:
            for item in results["items"]:
                node = item.get("track")
                if node and node.get("type") == "track":
                    tracks.append(_track_from_api(node))
            results = self._sp.next(results) if results.get("next") else None
        if not tracks:
            raise SpotifyError("That playlist has no playable tracks.")
        return ResolvedLink(kind=LinkKind.PLAYLIST, name=name, tracks=tracks)

    def _resolve_track(self, track_id: str) -> ResolvedLink:
        data = self._sp.track(track_id)
        track = _track_from_api(data)
        return ResolvedLink(kind=LinkKind.TRACK, name=track.title, tracks=[track])

    def _resolve_album(self, album_id: str) -> ResolvedLink:
        album = self._sp.album(album_id)
        name = album.get("name", "album")
        album_name = name
        tracks: list[Track] = []
        results = album["tracks"]
        while results:
            for node in results["items"]:
                tracks.append(_track_from_api(node, album_name=album_name))
            results = self._sp.next(results) if results.get("next") else None
        if not tracks:
            raise SpotifyError("That album has no tracks.")
        return ResolvedLink(kind=LinkKind.ALBUM, name=name, tracks=tracks)


def _track_from_api(node: dict, album_name: str | None = None) -> Track:
    """Build a Track from a Spotify API track object."""
    artists = [a["name"] for a in node.get("artists", []) if a.get("name")]
    album = album_name or (node.get("album", {}) or {}).get("name", "")
    return Track(
        title=node.get("name", "Unknown"),
        artists=artists or ["Unknown Artist"],
        album=album,
        duration_ms=node.get("duration_ms", 0),
    )
