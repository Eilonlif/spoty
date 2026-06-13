# Spotify → MP3

A small web app: paste a Spotify **track** or **playlist** link and download it
as an MP3. A single track gives you one `.mp3`; a playlist (or album) gives you
a `.zip` of all the tracks.

## How it works

Spotify does **not** provide downloadable audio files. This app:

1. Uses the **Spotify Web API** (via your client ID/secret) to read track
   *metadata* — title, artist, album.
2. Searches a public audio source with **yt-dlp** for the closest match.
3. Transcodes to MP3 with **ffmpeg**, embedding the metadata as tags.
4. Returns a single MP3, or zips a playlist/album.

> For personal use only. Respect the rights of content creators and the terms
> of the services you use.

### Spotify login (required for playlists)

As of late 2024, Spotify's API no longer lets *app-only* credentials read a
playlist's tracks — it returns `401 Valid user authentication required` for
every playlist. Tracks and albums still work app-only, but **playlists require
a logged-in Spotify user**. The app therefore includes a **Connect Spotify**
button (OAuth Authorization Code flow); once connected, playlists work.

For this to work, the **Redirect URI** in your Spotify app dashboard must
exactly match `SPOTIFY_REDIRECT_URI` (see below).

### Playlists you don't own

Spotify's API only returns a playlist's items for playlists you **own or
collaborate on** — any other playlist returns `403 Forbidden` by design, even
when logged in. For public playlists you don't own, the app falls back to
reading the tracklist from Spotify's **public embed page** (no API), then
downloads as usual.

> Heads up: this whole app downloads audio matched from Spotify metadata,
> which is contrary to Spotify's Developer Terms ("no facilitating downloads /
> stream ripping") and may infringe copyright. It's intended as a personal
> tool — use it accordingly.

## Project layout

```
app.py                     Flask entry point + API routes
spoty_to_mp3/
  config.py                Loads settings from .env
  spotify_client.py        Resolves a Spotify link into track metadata
  downloader.py            yt-dlp search + ffmpeg -> tagged MP3
  jobs.py                  In-memory job registry + progress tracking
  service.py               Orchestration (resolve -> download -> package)
templates/index.html       The UI
static/style.css, app.js   Styling + progress polling
Dockerfile, render.yaml    Deployment (ships ffmpeg)
```

The web layer starts a background thread per conversion and the browser polls
`/api/status/<id>`, so long playlists don't hit a request timeout.

## Requirements

- Python 3.11+
- **ffmpeg** installed and on your `PATH` (`ffmpeg -version` to check)
- Spotify API credentials (free): create an app at
  <https://developer.spotify.com/dashboard>
- In that app's settings, add a **Redirect URI** of
  `http://127.0.0.1:5000/callback` (for local dev). For production, also add
  your deployed URL, e.g. `https://your-app.onrender.com/callback`.

## Run locally

```bash
pip install -r requirements.txt

cp .env.example .env
# edit .env and fill in SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET

python app.py
# open http://127.0.0.1:5000
```

## Deploy to Render

The included `Dockerfile` installs ffmpeg, so deploy as a **Docker** service.

1. Push this repo to GitHub.
2. In <https://dashboard.render.com> → **New → Blueprint**, select the repo
   (it reads `render.yaml`). Or **New → Web Service** → Docker runtime.
3. In the service's **Environment** tab, set `SPOTIFY_CLIENT_ID` and
   `SPOTIFY_CLIENT_SECRET`.
4. Deploy. Render builds the container and serves it via gunicorn on `$PORT`.

## API

| Method | Endpoint                | Purpose                          |
| ------ | ----------------------- | -------------------------------- |
| `POST` | `/api/convert`          | Start a job (`{"url": "..."}`)   |
| `GET`  | `/api/status/<job_id>`  | Poll progress                    |
| `GET`  | `/api/download/<job_id>`| Download the finished MP3/ZIP    |

## Environment variables

| Variable                | Required | Default     | Notes                       |
| ----------------------- | -------- | ----------- | --------------------------- |
| `SPOTIFY_CLIENT_ID`     | yes      | —           | From the Spotify dashboard  |
| `SPOTIFY_CLIENT_SECRET` | yes      | —           | From the Spotify dashboard  |
| `SPOTIFY_REDIRECT_URI`  | yes*     | `http://127.0.0.1:5000/callback` | Must match the dashboard exactly |
| `FLASK_SECRET_KEY`      | yes*     | dev default | Signs session cookies; random in prod |
| `DOWNLOAD_DIR`          | no       | `downloads` | Where finished files land   |
| `FLASK_HOST`            | no       | `127.0.0.1` | Local dev only              |
| `FLASK_PORT`            | no       | `5000`      | Local dev only              |
| `FLASK_DEBUG`           | no       | `0`         | Local dev only              |
