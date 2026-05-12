"""Job queue for the Pi download service.

Reuses core/ (downloader, transcriber, store) verbatim — same JSON sidecar
format as the PC app, so files synced via Syncthing land in the PC
history with zero translation.
"""

import logging
import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Optional

from core.downloader import VideoDownloader
from core.platform_detect import detect_platform
from core.store import VideoData, VideoStore
from core.transcriber import NoAudioTrackError, transcribe_file

log = logging.getLogger(__name__)

# Job statuses — string enums so the JSON UI sees them as-is.
QUEUED = "queued"
DOWNLOADING = "downloading"
TRANSCRIBING = "transcribing"
DONE = "done"
ERROR = "error"
CANCELLED = "cancelled"

TERMINAL_STATUSES = {DONE, ERROR, CANCELLED}


@dataclass
class Job:
    """One download (+optional transcription) request."""

    id: str
    url: str
    format: str           # "mp4" | "mp3"
    transcribe: bool
    language: str
    status: str = QUEUED
    progress: float = 0.0
    message: str = ""
    title: str = ""
    filepath: str = ""    # absolute path inside container; UI shows basename
    error: str = ""
    created_at: str = ""
    started_at: str = ""
    finished_at: str = ""

    def to_dict(self) -> dict:
        # Strip internal fields, expose only what the UI needs.
        d = asdict(self)
        d["media_file"] = os.path.basename(self.filepath) if self.filepath else ""
        return d


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobManager:
    """Thread-safe in-memory job store + worker pool."""

    def __init__(
        self,
        output_dir: str,
        api_key: str,
        max_workers: int = 2,
        history_limit: int = 50,
    ):
        self._output_dir = output_dir
        self._api_key = api_key
        self._history_limit = history_limit
        self._jobs: dict[str, Job] = {}
        # Per-job downloader instance so cancel() can reach into yt-dlp.
        self._downloaders: dict[str, VideoDownloader] = {}
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="job"
        )
        os.makedirs(output_dir, exist_ok=True)

    # ----- public API -----------------------------------------------------

    def submit(
        self,
        url: str,
        fmt: str,
        transcribe: bool,
        language: str,
    ) -> Job:
        job = Job(
            id=uuid.uuid4().hex[:12],
            url=url.strip(),
            format=fmt,
            transcribe=bool(transcribe),
            language=language or "pt-BR",
            created_at=_now(),
            message="Na fila...",
        )
        with self._lock:
            self._jobs[job.id] = job
            self._prune_locked()
        self._executor.submit(self._run, job.id)
        return job

    def list(self) -> list[dict]:
        with self._lock:
            jobs = list(self._jobs.values())
        # Newest first
        jobs.sort(key=lambda j: j.created_at, reverse=True)
        return [j.to_dict() for j in jobs]

    def get(self, job_id: str) -> Optional[dict]:
        with self._lock:
            job = self._jobs.get(job_id)
        return job.to_dict() if job else None

    def cancel(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            dl = self._downloaders.get(job_id)
        if not job:
            return False
        if job.status in TERMINAL_STATUSES:
            return False
        # Tell yt-dlp to abort at the next progress tick. Deepgram REST
        # call is not cancellable mid-request — caller will see CANCELLED
        # after the request returns.
        if dl is not None:
            dl.cancel()
        # If still queued (no worker has picked it up), flip to cancelled
        # immediately. _run() will see it and bail.
        if job.status == QUEUED:
            job.status = CANCELLED
            job.finished_at = _now()
            job.message = "Cancelado antes de iniciar"
        return True

    def remove(self, job_id: str) -> bool:
        """Remove a terminal job from the list. No-op for active jobs."""
        with self._lock:
            job = self._jobs.get(job_id)
            if not job or job.status not in TERMINAL_STATUSES:
                return False
            del self._jobs[job_id]
            self._downloaders.pop(job_id, None)
        return True

    def shutdown(self):
        self._executor.shutdown(wait=False, cancel_futures=True)

    # ----- worker ---------------------------------------------------------

    def _run(self, job_id: str):
        with self._lock:
            job = self._jobs.get(job_id)
        if not job:
            return
        # Caller may have cancelled before we picked the job up.
        if job.status == CANCELLED:
            return

        job.status = DOWNLOADING
        job.started_at = _now()
        job.message = "Iniciando download..."

        def _progress(pct: float, msg: str):
            # If transcribing, downloads occupy 0-70% of overall progress.
            ceiling = 0.7 if job.transcribe else 1.0
            job.progress = max(0.0, min(1.0, float(pct) * ceiling))
            if msg:
                job.message = msg

        # windowsfilenames=True: sanitize illegal chars (:, ?, *, etc) so the
        # file Syncthing replicates can be written on the PC's NTFS too.
        downloader = VideoDownloader(
            progress_callback=_progress,
            extra_opts={"windowsfilenames": True},
        )
        with self._lock:
            self._downloaders[job_id] = downloader

        try:
            result = downloader.download(job.url, job.format, self._output_dir)
        except RuntimeError as e:
            # VideoDownloader raises RuntimeError("Download cancelado...")
            if "cancelado" in str(e).lower():
                job.status = CANCELLED
                job.message = "Cancelado pelo usuario"
                job.finished_at = _now()
                return
            job.status = ERROR
            job.error = str(e)
            job.message = f"Erro no download: {e}"
            job.finished_at = _now()
            return
        except Exception as e:  # noqa: BLE001
            log.exception("download failed for %s", job.url)
            job.status = ERROR
            job.error = str(e)
            job.message = f"Erro no download: {e}"
            job.finished_at = _now()
            return

        filepath = result["filepath"]
        job.filepath = filepath
        job.title = result.get("title") or os.path.basename(filepath)

        transcription = ""
        if job.transcribe:
            job.status = TRANSCRIBING
            job.message = "Iniciando transcricao..."

            def _tr_progress(pct: float, msg: str):
                job.progress = 0.7 + max(0.0, min(1.0, float(pct))) * 0.3
                if msg:
                    job.message = msg

            try:
                transcription = transcribe_file(
                    audio_path=filepath,
                    api_key=self._api_key,
                    language=job.language,
                    on_progress=_tr_progress,
                )
            except NoAudioTrackError as e:
                # Download worked, transcription didn't — keep the file,
                # mark job as done but flag the message.
                job.message = f"Baixado, sem audio para transcrever: {e}"
            except Exception as e:  # noqa: BLE001
                log.exception("transcription failed for %s", filepath)
                job.message = f"Baixado, transcricao falhou: {e}"
                job.error = str(e)
                # Fall through and still write the sidecar — file is valid.

        # Build the same VideoData the PC app would produce. JSON sidecar
        # lives at <filepath>.json — Syncthing replicates both.
        data = VideoData(
            video_id=uuid.uuid4().hex[:12],
            url=job.url,
            title=job.title,
            platform=detect_platform(job.url),
            media_file=os.path.basename(filepath),
            format=job.format,
            duration_seconds=float(result.get("duration") or 0),
            uploader=result.get("uploader", "") or "",
            thumbnail_url=result.get("thumbnail", "") or "",
            created_at=_now(),
            transcription=transcription,
            transcribed_at=_now() if transcription else "",
            language=job.language if transcription else "",
        )
        try:
            VideoStore.save(filepath, data)
        except Exception as e:  # noqa: BLE001
            log.exception("VideoStore.save failed for %s", filepath)
            job.status = ERROR
            job.error = f"Falha ao salvar sidecar JSON: {e}"
            job.message = job.error
            job.finished_at = _now()
            return

        job.progress = 1.0
        job.status = DONE
        if not job.error:
            job.message = "Concluido"
        job.finished_at = _now()

    # ----- housekeeping ---------------------------------------------------

    def _prune_locked(self):
        """Keep at most history_limit terminal jobs; active jobs are never pruned."""
        terminal = sorted(
            (j for j in self._jobs.values() if j.status in TERMINAL_STATUSES),
            key=lambda j: j.finished_at or j.created_at,
        )
        excess = len(terminal) - self._history_limit
        for j in terminal[:max(0, excess)]:
            self._jobs.pop(j.id, None)
            self._downloaders.pop(j.id, None)
