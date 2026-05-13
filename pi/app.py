"""FastAPI service: web UI + REST API to download/transcribe videos on the Pi.

Output files go to OUTPUT_DIR (a Syncthing-watched folder), so the PC app
picks them up automatically — the JSON sidecar format is identical.
"""

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, field_validator

from core.store import VideoStore
from pi.jobs import JobManager

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
)
log = logging.getLogger("pi.app")

OUTPUT_DIR = os.getenv("OUTPUT_DIR", "/output")
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY", "")
DEFAULT_LANGUAGE = os.getenv("DEFAULT_LANGUAGE", "pt-BR")
MAX_CONCURRENT_JOBS = int(os.getenv("MAX_CONCURRENT_JOBS", "2"))
JOB_HISTORY_LIMIT = int(os.getenv("JOB_HISTORY_LIMIT", "50"))

# UI language presets — Deepgram nova-3 codes. "multi" auto-detects.
LANGUAGES = [
    ("pt-BR", "Portugues (BR)"),
    ("en-US", "Ingles (US)"),
    ("es", "Espanhol"),
    ("fr", "Frances"),
    ("de", "Alemao"),
    ("it", "Italiano"),
    ("multi", "Auto (multi)"),
]

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="Videos Pi", version="0.1")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
# Serve downloaded media files. Starlette's StaticFiles handles HTTP Range
# requests natively, so the HTML5 <video> tag can seek without extra code.
os.makedirs(OUTPUT_DIR, exist_ok=True)
app.mount("/media", StaticFiles(directory=OUTPUT_DIR), name="media")

job_manager = JobManager(
    output_dir=OUTPUT_DIR,
    api_key=DEEPGRAM_API_KEY,
    max_workers=MAX_CONCURRENT_JOBS,
    history_limit=JOB_HISTORY_LIMIT,
)


class DownloadRequest(BaseModel):
    url: str = Field(min_length=4, max_length=2048)
    format: str = Field(default="mp4")
    transcribe: bool = False
    language: str = Field(default="")

    @field_validator("format")
    @classmethod
    def _check_format(cls, v: str) -> str:
        v = (v or "").lower().strip()
        if v not in ("mp4", "mp3"):
            raise ValueError("format must be 'mp4' or 'mp3'")
        return v

    @field_validator("url")
    @classmethod
    def _check_url(cls, v: str) -> str:
        v = (v or "").strip()
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("URL must start with http:// or https://")
        return v


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    # Starlette >=1.0 requires Request as the first positional arg.
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "languages": LANGUAGES,
            "default_language": DEFAULT_LANGUAGE,
            "deepgram_configured": bool(DEEPGRAM_API_KEY),
            "output_dir": OUTPUT_DIR,
        },
    )


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "output_dir": OUTPUT_DIR,
        "deepgram_configured": bool(DEEPGRAM_API_KEY),
        "max_concurrent_jobs": MAX_CONCURRENT_JOBS,
    }


@app.post("/api/download")
def create_download(req: DownloadRequest):
    if req.transcribe and not DEEPGRAM_API_KEY:
        raise HTTPException(
            status_code=400,
            detail="DEEPGRAM_API_KEY nao configurada — transcricao indisponivel.",
        )
    language = req.language or DEFAULT_LANGUAGE
    job = job_manager.submit(req.url, req.format, req.transcribe, language)
    log.info("queued job %s — %s (%s, transcribe=%s)", job.id, req.url, req.format, req.transcribe)
    return JSONResponse(job.to_dict(), status_code=201)


@app.get("/api/jobs")
def list_jobs():
    return {"jobs": job_manager.list()}


@app.get("/api/library")
def list_library():
    """List every video that lives in OUTPUT_DIR (the Syncthing-watched folder).

    Each entry includes a ``media_url`` rooted at /media/ so the UI can stream
    via the StaticFiles mount.
    """
    items = VideoStore.list_videos(OUTPUT_DIR)
    for v in items:
        v["media_url"] = "/media/" + os.path.basename(v["media_path"])
    return {"videos": items}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    job = job_manager.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return job


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str):
    ok = job_manager.cancel(job_id)
    if not ok:
        raise HTTPException(
            status_code=404,
            detail="job not found or already finished",
        )
    return {"ok": True}


@app.delete("/api/jobs/{job_id}")
def remove_job(job_id: str):
    ok = job_manager.remove(job_id)
    if not ok:
        raise HTTPException(
            status_code=400,
            detail="job not found or still running (cancel first)",
        )
    return {"ok": True}


@app.on_event("shutdown")
def _shutdown():
    job_manager.shutdown()
