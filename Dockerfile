# Render (and any container host) build. ffmpeg is required at runtime for
# transcoding to MP3, so we install it at the system level here.
FROM python:3.12-slim

# ffmpeg for audio conversion.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Render provides $PORT; default to 5000 for local container runs.
ENV PORT=5000
EXPOSE 5000

# gunicorn serves the Flask app. Long downloads need a generous timeout.
CMD gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 600
