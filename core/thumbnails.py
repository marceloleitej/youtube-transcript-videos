"""Thumbnail caching: downloads remote thumbnails and serves local JPEGs."""

import os
from typing import Optional

import httpx


THUMB_DIRNAME = ".thumbs"


def thumb_dir(output_dir: str) -> str:
    path = os.path.join(output_dir, THUMB_DIRNAME)
    os.makedirs(path, exist_ok=True)
    return path


def thumb_path(output_dir: str, video_id: str) -> str:
    """Return the expected path for a video's thumbnail."""
    return os.path.join(thumb_dir(output_dir), f"{video_id}.jpg")


def has_thumb(output_dir: str, video_id: str) -> bool:
    return bool(video_id) and os.path.isfile(thumb_path(output_dir, video_id))


def fetch_thumbnail(url: str, dest_path: str, timeout: float = 15.0) -> bool:
    """Download a thumbnail URL to dest_path. Returns True on success."""
    if not url:
        return False
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            resp = client.get(url)
            resp.raise_for_status()
            data = resp.content
        if not data:
            return False
        with open(dest_path, "wb") as f:
            f.write(data)
        return True
    except Exception:
        return False


def ensure_thumbnail(output_dir: str, video_id: str, url: str) -> Optional[str]:
    """If a thumb already exists return its path, else try to download it."""
    if not video_id:
        return None
    p = thumb_path(output_dir, video_id)
    if os.path.isfile(p):
        return p
    if fetch_thumbnail(url, p):
        return p
    return None
