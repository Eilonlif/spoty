"""Flask web app: paste a Spotify link, get an MP3 (or a ZIP for playlists)."""

from __future__ import annotations

import threading

from flask import (
    Flask,
    abort,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)

from spoty_to_mp3 import auth
from spoty_to_mp3.config import load_config
from spoty_to_mp3.jobs import JobRegistry, JobStatus
from spoty_to_mp3.service import run_conversion

config = load_config()
registry = JobRegistry()
app = Flask(__name__)
app.secret_key = config.secret_key


@app.route("/")
def index():
    return render_template(
        "index.html",
        spotify_configured=config.spotify_configured,
        logged_in=auth.is_logged_in(config),
    )


@app.get("/login")
def login():
    """Send the user to Spotify to authorize, then back to /callback."""
    return redirect(auth.make_oauth(config).get_authorize_url())


@app.get("/callback")
def callback():
    """Exchange the auth code for a token, stored in the session."""
    error = request.args.get("error")
    if error:
        return redirect(url_for("index"))
    code = request.args.get("code")
    if code:
        # Caches the token in the Flask session via the cache handler.
        auth.make_oauth(config).get_access_token(code, as_dict=False)
    return redirect(url_for("index"))


@app.get("/logout")
def logout():
    auth.logout()
    return redirect(url_for("index"))


@app.post("/api/convert")
def convert():
    """Start a conversion job and return its id."""
    if not config.spotify_configured:
        return (
            jsonify(
                error="Spotify credentials are not configured on the server."
            ),
            503,
        )

    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    if not url:
        return jsonify(error="Please paste a Spotify link."), 400

    # The token must be read here (request context); the worker thread has no
    # access to the Flask session. None means app-only (tracks/albums only).
    access_token = auth.current_access_token(config)

    job = registry.create(url)
    thread = threading.Thread(
        target=run_conversion,
        args=(job.id, url, config, registry, access_token),
        daemon=True,
    )
    thread.start()
    return jsonify(job.to_dict()), 202


@app.get("/api/status/<job_id>")
def status(job_id: str):
    job = registry.get(job_id)
    if job is None:
        return jsonify(error="Unknown job."), 404
    return jsonify(job.to_dict())


@app.get("/api/download/<job_id>")
def download(job_id: str):
    job = registry.get(job_id)
    if job is None:
        abort(404)
    if job.status is not JobStatus.DONE or not job.result_path:
        abort(409, description="This job isn't finished yet.")
    if not job.result_path.exists():
        abort(410, description="The file is no longer available.")
    return send_file(
        job.result_path,
        as_attachment=True,
        download_name=job.result_name or job.result_path.name,
    )


if __name__ == "__main__":
    app.run(host=config.host, port=config.port, debug=config.debug)
