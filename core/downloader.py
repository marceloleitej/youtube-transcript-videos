"""Video downloader using yt-dlp — supports YouTube, TikTok, Instagram, Facebook."""

import glob
import os
import re
import shutil
from typing import Callable, Optional

import yt_dlp


def _find_node() -> dict:
    """Return yt-dlp js_runtimes config for Node.js if available."""
    # Check common Windows install path first
    for candidate in [
        r"C:\Program Files\nodejs\node.exe",
        r"C:\Program Files (x86)\nodejs\node.exe",
    ]:
        if os.path.isfile(candidate):
            return {"node": {"exe": candidate}}

    # Fall back to PATH lookup
    node = shutil.which("node") or shutil.which("node.exe")
    if node:
        return {"node": {"exe": node}}

    return {}


class VideoDownloader:
    """Download videos/audio from YouTube, TikTok, Instagram via yt-dlp."""

    def __init__(self, progress_callback: Optional[Callable[[float, str], None]] = None,
                 cookies_file: str = ""):
        self.progress_callback = progress_callback
        self.cookies_file = cookies_file
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def _apply_common_opts(self, opts: dict) -> None:
        """Add cookies and JS runtime config to yt-dlp opts."""
        if self.cookies_file and os.path.isfile(self.cookies_file):
            opts["cookiefile"] = self.cookies_file
        js = _find_node()
        if js:
            opts["js_runtimes"] = js

    def get_info(self, url: str) -> dict:
        """Return metadata: title, duration, thumbnail URL."""
        opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
        }
        self._apply_common_opts(opts)
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return {
                "title": info.get("title", "Unknown"),
                "duration": info.get("duration", 0),
                "thumbnail": info.get("thumbnail", ""),
                "uploader": info.get("uploader", ""),
            }

    def download(self, url: str, fmt: str, output_dir: str) -> dict:
        """Download video (MP4) or audio (MP3). Returns metadata dict.

        Args:
            url: Video URL (YouTube, TikTok, Instagram, etc.)
            fmt: 'mp4' for video, 'mp3' for audio-only
            output_dir: Directory to save the file

        Returns:
            dict with keys: filepath, title, duration, uploader, thumbnail
        """
        self._cancelled = False
        os.makedirs(output_dir, exist_ok=True)

        outtmpl = os.path.join(output_dir, "%(title).80s.%(ext)s")

        if fmt == "mp3":
            opts = {
                "format": "bestaudio/best",
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }],
                "keepvideo": False,
                "outtmpl": outtmpl,
                "quiet": True,
                "no_warnings": True,
                "progress_hooks": [self._progress_hook],
            }
        else:
            # Format fallback chain:
            # 1. bv*+ba         — best video (allowing muxed) + best separate audio
            # 2. b[acodec!=none] — best single stream that already has an audio codec
            # 3. b              — any best stream (last resort)
            opts = {
                "format": "bv*+ba/b[acodec!=none]/b",
                "merge_output_format": "mp4",
                "outtmpl": outtmpl,
                "quiet": True,
                "no_warnings": True,
                "progress_hooks": [self._progress_hook],
            }

        self._apply_common_opts(opts)

        # Snapshot existing files so we can detect what's new
        expected_ext = ".mp3" if fmt == "mp3" else ".mp4"
        before = set(
            os.path.join(output_dir, f)
            for f in os.listdir(output_dir)
            if f.lower().endswith(expected_ext)
        )

        # Capture real filepath from hooks (yt-dlp writes sanitized names)
        self._final_filepath = None

        def _pp_hook(d: dict):
            if d.get("status") == "finished" and d.get("filepath"):
                self._final_filepath = d["filepath"]

        opts["postprocessor_hooks"] = [_pp_hook]

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if self._cancelled:
                raise RuntimeError("Download cancelado pelo usuário.")

            filename = self._resolve_filepath(
                info, ydl, fmt, output_dir, expected_ext, before,
            )

            # For MP4 downloads, validate the file actually has audio.
            # If not, retry with a more permissive format selector.
            if fmt == "mp4" and self._file_has_audio(filename) is False:
                if self.progress_callback:
                    self.progress_callback(0.0, "Audio ausente — tentando outro formato...")
                try:
                    os.remove(filename)
                except OSError:
                    pass
                filename = self._retry_download_with_audio(url, output_dir, expected_ext)

            return {
                "filepath": filename,
                "title": info.get("title", "Unknown"),
                "duration": info.get("duration", 0),
                "uploader": info.get("uploader", ""),
                "thumbnail": info.get("thumbnail", ""),
            }

    @staticmethod
    def _file_has_audio(path: str) -> Optional[bool]:
        """Return True/False/None (None = can't determine) for audio presence."""
        from core.transcriber import has_audio_stream
        return has_audio_stream(path)

    def _retry_download_with_audio(self, url: str, output_dir: str, expected_ext: str) -> str:
        """Fallback: download the single 'best' stream that has an audio codec."""
        before = set(
            os.path.join(output_dir, f)
            for f in os.listdir(output_dir)
            if f.lower().endswith(expected_ext)
        )
        self._final_filepath = None

        opts = {
            "format": "b[acodec!=none]/b",
            "merge_output_format": "mp4",
            "outtmpl": os.path.join(output_dir, "%(title).80s.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            "progress_hooks": [self._progress_hook],
            "postprocessor_hooks": [
                lambda d: setattr(self, "_final_filepath", d.get("filepath"))
                if d.get("status") == "finished" and d.get("filepath") else None
            ],
        }
        self._apply_common_opts(opts)

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = self._resolve_filepath(info, ydl, "mp4", output_dir, expected_ext, before)

        return filename

    def _resolve_filepath(self, info, ydl, fmt, output_dir, expected_ext, before):
        """Find the actual file on disk after download completes."""
        # 1. Postprocessor hook (most reliable for MP3 / merged MP4)
        if self._final_filepath and os.path.isfile(self._final_filepath):
            return self._final_filepath

        # 2. requested_downloads from yt-dlp info
        for dl in info.get("requested_downloads", []):
            fp = dl.get("filepath", "")
            if fp and os.path.isfile(fp):
                return fp

        # 3. Detect new file in output directory (diff against snapshot)
        after = set(
            os.path.join(output_dir, f)
            for f in os.listdir(output_dir)
            if f.lower().endswith(expected_ext)
        )
        new_files = after - before
        if len(new_files) == 1:
            return new_files.pop()
        if len(new_files) > 1:
            # Pick the most recently modified
            return max(new_files, key=os.path.getmtime)

        # 4. prepare_filename with expected extension (may have unsanitized chars)
        base = os.path.splitext(ydl.prepare_filename(info))[0]
        candidate = base + expected_ext
        if os.path.isfile(candidate):
            return candidate

        raise FileNotFoundError(
            f"Arquivo não encontrado após download no diretório: {output_dir}"
        )

    def _progress_hook(self, d: dict):
        if self._cancelled:
            raise yt_dlp.utils.DownloadCancelled()

        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes", 0)
            if total > 0:
                pct = downloaded / total
            else:
                pct = 0.0
            speed = d.get("_speed_str", "")
            eta = d.get("_eta_str", "")
            msg = f"Baixando... {speed} ETA: {eta}".strip()
            if self.progress_callback:
                self.progress_callback(pct, msg)

        elif d["status"] == "finished":
            if self.progress_callback:
                self.progress_callback(1.0, "Download concluído, processando...")
