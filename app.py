"""Flask web app: paste a Spotify link, get an MP3 (or a ZIP for playlists)."""

from __future__ import annotations

import threading

from flask import Flask, abort, jsonify, render_template, request, send_file

from spoty_to_mp3.config import load_config
from spoty_to_mp3.jobs import JobRegistry, JobStatus
from spoty_to_mp3.service import run_conversion

config = load_config()
registry = JobRegistry()
app = Flask(__name__)


@app.route("/")
def index():
    return render_template(
        "index.html", spotify_configured=config.spotify_configured
    )


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

    job = registry.create(url)
    thread = threading.Thread(
        target=run_conversion,
        args=(job.id, url, config, registry),
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
