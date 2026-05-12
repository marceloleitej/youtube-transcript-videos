FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=America/Sao_Paulo

# Runtime deps:
#   ffmpeg  — yt-dlp merge + audio extraction + ffprobe for transcriber
#   nodejs  — required by yt-dlp-ejs (YouTube JS player extractor)
#   tzdata  — so logs and ISO timestamps are local time
#   ca-certificates — TLS for yt-dlp and Deepgram REST
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        nodejs \
        tzdata \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pi/requirements.txt /app/pi/requirements.txt
RUN pip install -r /app/pi/requirements.txt

# Shared modules from the PC app — single source of truth for downloader,
# transcriber, store, platform detection. Anything imported by pi/ must
# live under core/ here (no Qt deps in core/).
COPY core/ /app/core/
COPY pi/ /app/pi/

# Where downloads land inside the container. Mapped to a Syncthing folder
# on the host via docker-compose.
ENV OUTPUT_DIR=/output

EXPOSE 8080

CMD ["uvicorn", "pi.app:app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers"]
