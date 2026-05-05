"""Deepgram batch transcription via REST API."""

import json
import mimetypes
import os
import shutil
import subprocess
from typing import Callable, Optional

import httpx


class NoAudioTrackError(RuntimeError):
    """Raised when the media file has no audio stream."""


def _find_ffprobe() -> Optional[str]:
    """Locate ffprobe on the system (ships with ffmpeg)."""
    exe = shutil.which("ffprobe") or shutil.which("ffprobe.exe")
    if exe:
        return exe
    # Try common install locations on Windows
    for candidate in [
        r"C:\Program Files\ffmpeg\bin\ffprobe.exe",
        r"C:\ffmpeg\bin\ffprobe.exe",
    ]:
        if os.path.isfile(candidate):
            return candidate
    return None


def has_audio_stream(media_path: str) -> Optional[bool]:
    """Check if the media file has any audio stream.

    Returns True/False, or None if ffprobe is unavailable (cannot determine).
    """
    ffprobe = _find_ffprobe()
    if not ffprobe:
        return None
    try:
        result = subprocess.run(
            [
                ffprobe, "-v", "error",
                "-select_streams", "a",
                "-show_entries", "stream=codec_type",
                "-of", "json",
                media_path,
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return None
        data = json.loads(result.stdout or "{}")
        streams = data.get("streams", [])
        return any(s.get("codec_type") == "audio" for s in streams)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
        return None


MIME_MAP = {
    ".mp3": "audio/mpeg",
    ".mp4": "video/mp4",
    ".m4a": "audio/mp4",
    ".wav": "audio/wav",
    ".ogg": "audio/ogg",
    ".flac": "audio/flac",
    ".webm": "audio/webm",
}


def transcribe_file(
    audio_path: str,
    api_key: str,
    language: str = "pt-BR",
    on_progress: Optional[Callable[[float, str], None]] = None,
) -> str:
    """Transcribe an audio/video file using Deepgram REST API.

    Args:
        audio_path: Path to audio or video file.
        api_key: Deepgram API key.
        language: Language code (e.g. 'pt-BR', 'en', 'es').
        on_progress: Callback(percent, message).

    Returns:
        Transcribed text as a single string.
    """
    if on_progress:
        on_progress(0.02, "Verificando arquivo...")

    # Fail fast if the file has no audio track (saves an API call)
    audio_present = has_audio_stream(audio_path)
    if audio_present is False:
        raise NoAudioTrackError(
            "Este arquivo não possui faixa de áudio. "
            "Nada para transcrever."
        )

    if on_progress:
        on_progress(0.05, "Lendo arquivo de áudio...")

    ext = os.path.splitext(audio_path)[1].lower()
    content_type = MIME_MAP.get(ext, "application/octet-stream")

    with open(audio_path, "rb") as f:
        audio_data = f.read()

    if on_progress:
        on_progress(0.1, "Enviando para Deepgram...")

    url = "https://api.deepgram.com/v1/listen"
    params = {
        "model": "nova-3",
        "smart_format": "true",
        "punctuate": "true",
        "paragraphs": "true",
        "utterances": "true",
        "numerals": "true",
    }
    if language and language.lower() != "auto":
        params["language"] = language
    else:
        params["detect_language"] = "true"

    headers = {
        "Authorization": f"Token {api_key}",
        "Content-Type": content_type,
    }

    if on_progress:
        on_progress(0.2, "Transcrevendo com Deepgram...")

    # Scale timeout with file size (min 5 min, +2 min per 50 MB)
    size_mb = len(audio_data) / (1024 * 1024)
    base_timeout = max(300.0, 300.0 + (size_mb / 50) * 120)

    max_attempts = 3
    last_err = None
    for attempt in range(max_attempts):
        try:
            timeout = base_timeout * (attempt + 1)
            response = httpx.post(
                url,
                params=params,
                headers=headers,
                content=audio_data,
                timeout=timeout,
            )
            response.raise_for_status()
            result = response.json()
            break
        except httpx.HTTPStatusError as e:
            raise RuntimeError(f"Erro Deepgram ({e.response.status_code}): {e.response.text}")
        except (httpx.TimeoutException, httpx.TransportError, ConnectionError, OSError) as e:
            last_err = e
            if on_progress:
                on_progress(0.2, f"Erro de conexão — tentativa {attempt + 2}/{max_attempts}...")
    else:
        raise RuntimeError(f"Falha após {max_attempts} tentativas: {last_err}")

    if on_progress:
        on_progress(0.8, "Processando resultados...")

    # Extract text from response
    text = _extract_text(result)

    if on_progress:
        on_progress(1.0, "Transcrição concluída!")

    return text


def _extract_text(result: dict) -> str:
    """Extract formatted text from Deepgram response."""
    results = result.get("results", {})

    # Try paragraphs first (best formatting)
    channels = results.get("channels", [])
    if channels:
        for ch in channels:
            for alt in ch.get("alternatives", []):
                paragraphs = alt.get("paragraphs", {})
                if paragraphs and paragraphs.get("paragraphs"):
                    parts = []
                    for para in paragraphs["paragraphs"]:
                        sentences = para.get("sentences", [])
                        para_text = " ".join(s.get("text", "") for s in sentences)
                        if para_text.strip():
                            parts.append(para_text.strip())
                    if parts:
                        return "\n\n".join(parts)

    # Fallback: utterances
    utterances = results.get("utterances", [])
    if utterances:
        return "\n\n".join(u.get("transcript", "") for u in utterances if u.get("transcript", "").strip())

    # Last resort: channel transcript
    if channels:
        for ch in channels:
            for alt in ch.get("alternatives", []):
                transcript = alt.get("transcript", "")
                if transcript.strip():
                    return transcript.strip()

    return ""
