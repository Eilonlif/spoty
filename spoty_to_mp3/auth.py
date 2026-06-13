"""Spotify user login via the OAuth Authorization Code flow.

App-only credentials can read tracks and albums, but Spotify now requires a
logged-in *user* to read playlist tracks. This module wires up spotipy's
SpotifyOAuth using the Flask session as its token cache, so each browser
session has its own login.
"""

from __future__ import annotations

from flask import session
from spotipy.cache_handler import CacheHandler
from spotipy.oauth2 import SpotifyOAuth

from .config import Config

# Scopes needed to read the user's own private/collaborative playlists.
# Public playlists work with any valid user token; these cover the rest.
SCOPE = "playlist-read-private playlist-read-collaborative"

_TOKEN_KEY = "spotify_token_info"


class FlaskSessionCacheHandler(CacheHandler):
    """Stores the spotipy token dict in the signed Flask session cookie."""

    def get_cached_token(self):
        return session.get(_TOKEN_KEY)

    def save_token_to_cache(self, token_info):
        session[_TOKEN_KEY] = token_info


def make_oauth(config: Config) -> SpotifyOAuth:
    """Build a SpotifyOAuth manager backed by the Flask session."""
    return SpotifyOAuth(
        client_id=config.spotify_client_id,
        client_secret=config.spotify_client_secret,
        redirect_uri=config.spotify_redirect_uri,
        scope=SCOPE,
        cache_handler=FlaskSessionCacheHandler(),
        show_dialog=False,
    )


def is_logged_in(config: Config) -> bool:
    """True if the current session holds a (refreshable) Spotify token."""
    return make_oauth(config).cache_handler.get_cached_token() is not None


def current_access_token(config: Config) -> str | None:
    """Return a valid user access token, refreshing if needed; else None."""
    oauth = make_oauth(config)
    token_info = oauth.cache_handler.get_cached_token()
    if not token_info:
        return None
    if oauth.is_token_expired(token_info):
        token_info = oauth.refresh_access_token(token_info["refresh_token"])
    return token_info["access_token"]


def logout() -> None:
    """Forget the current session's Spotify token."""
    session.pop(_TOKEN_KEY, None)
