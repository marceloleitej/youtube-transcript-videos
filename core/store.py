"""Video metadata store — JSON sidecar persistence alongside media files."""

import json
import os
import re
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Optional, Union


def _normalize_dirs(value: "Union[str, list[str]]") -> list[str]:
    """Accept either a single path or a list — return a clean list of existing dirs."""
    if isinstance(value, str):
        candidates = [value]
    else:
        candidates = list(value or [])
    seen: set[str] = set()
    out: list[str] = []
    for p in candidates:
        if not p:
            continue
        norm = os.path.normpath(p)
        key = os.path.normcase(norm)
        if key in seen:
            continue
        seen.add(key)
        out.append(norm)
    return out

from core.platform_detect import UNKNOWN, detect_platform

# Position saves now run on a background QThreadPool worker while notes/
# bookmark/folder saves run on the UI thread. Serialize read-modify-write
# against a single lock so a background position save can't clobber a
# concurrent notes/bookmarks save (or vice versa).
_store_lock = threading.Lock()


@dataclass
class VideoData:
    """Metadata for a downloaded video/audio file."""

    video_id: str = ""
    url: str = ""
    title: str = ""
    platform: str = UNKNOWN
    media_file: str = ""          # filename only (not full path)
    format: str = "mp4"           # "mp4" or "mp3"
    duration_seconds: float = 0.0
    uploader: str = ""
    thumbnail_url: str = ""
    created_at: str = ""          # ISO 8601
    transcription: str = ""
    transcribed_at: str = ""      # ISO 8601 or ""
    language: str = ""
    folder: str = ""              # virtual folder/category; empty = root
    bookmarks: list = field(default_factory=list)  # [{"name": str, "time_ms": int, "category": str}]
    last_position_ms: int = 0     # playback resume position
    notes: str = ""               # user's personal notes about this video


def _json_path(media_path: str) -> str:
    """Return the .json sidecar path for a given media file.

    New format: video.mp4.json (unique per extension).
    """
    return media_path + ".json"


def _legacy_json_path(media_path: str) -> str:
    """Old format: video.json (shared between .mp4 and .mp3 with same stem)."""
    return os.path.splitext(media_path)[0] + ".json"


def _resolve_json_path(media_path: str) -> str | None:
    """Find the JSON sidecar: try new path first, then legacy."""
    jp = _json_path(media_path)
    if os.path.isfile(jp):
        return jp
    legacy = _legacy_json_path(media_path)
    if os.path.isfile(legacy):
        return legacy
    return None


class VideoStore:
    """Static methods for JSON sidecar persistence next to media files."""

    @staticmethod
    def save(media_path: str, data: VideoData) -> None:
        """Write VideoData as JSON next to the media file (atomic)."""
        jp = _json_path(media_path)
        tmp = jp + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(asdict(data), f, ensure_ascii=False, indent=2)
        os.replace(tmp, jp)
        # Remove legacy sidecar if it exists and differs from the new path
        legacy = _legacy_json_path(media_path)
        if legacy != jp and os.path.isfile(legacy):
            # Only remove if no other media file depends on it
            base = os.path.splitext(media_path)[0]
            ext = os.path.splitext(media_path)[1]
            other_ext = ".mp3" if ext.lower() == ".mp4" else ".mp4"
            other_media = base + other_ext
            if not os.path.isfile(other_media):
                os.remove(legacy)

    @staticmethod
    def load(media_path: str) -> Optional[VideoData]:
        """Load VideoData from the JSON sidecar. Returns None if missing."""
        jp = _resolve_json_path(media_path)
        if jp is None:
            return None
        try:
            with open(jp, "r", encoding="utf-8") as f:
                d = json.load(f)
            return VideoData(**{k: v for k, v in d.items() if k in VideoData.__dataclass_fields__})
        except Exception:
            return None

    @staticmethod
    def list_videos(output_dirs: "Union[str, list[str]]") -> list[dict]:
        """Return a lightweight list of videos for populating the sidebar.

        Accepts a single path (legacy) or a list of paths. When multiple
        dirs are passed, results are merged and de-duplicated by media_path.
        Each dict carries ``output_dir`` so callers can locate the per-folder
        thumbnail cache without re-deriving from media_path.
        """
        dirs = _normalize_dirs(output_dirs)
        results: list[dict] = []
        seen: set[str] = set()

        for output_dir in dirs:
            if not os.path.isdir(output_dir):
                continue
            for fname in os.listdir(output_dir):
                ext = os.path.splitext(fname)[1].lower()
                if ext not in (".mp4", ".mp3"):
                    continue
                media_path = os.path.join(output_dir, fname)
                key = os.path.normcase(os.path.normpath(media_path))
                if key in seen:
                    continue
                data = VideoStore.load(media_path)
                if data is None:
                    continue
                seen.add(key)
                results.append({
                    "media_path": media_path,
                    "title": data.title or fname,
                    "platform": data.platform,
                    "format": ext.lstrip("."),
                    "created_at": data.created_at,
                    "duration_seconds": data.duration_seconds,
                    "has_transcription": bool(data.transcription),
                    "folder": data.folder,
                    "video_id": data.video_id,
                    "thumbnail_url": data.thumbnail_url,
                    "last_position_ms": data.last_position_ms,
                    "output_dir": output_dir,
                })

        # Sort by created_at descending (newest first)
        results.sort(key=lambda v: v["created_at"], reverse=True)
        return results

    @staticmethod
    def update_transcription(media_path: str, text: str, language: str) -> None:
        """Update only the transcription fields in the sidecar JSON."""
        with _store_lock:
            data = VideoStore.load(media_path)
            if data is None:
                return
            data.transcription = text
            data.language = language
            data.transcribed_at = datetime.now(timezone.utc).isoformat()
            VideoStore.save(media_path, data)

    @staticmethod
    def update_platform(media_path: str, platform: str) -> None:
        """Update only the platform field in the sidecar JSON."""
        with _store_lock:
            data = VideoStore.load(media_path)
            if data is None:
                return
            data.platform = platform
            VideoStore.save(media_path, data)

    @staticmethod
    def update_folder(media_path: str, folder: str) -> None:
        """Update only the folder field in the sidecar JSON."""
        with _store_lock:
            data = VideoStore.load(media_path)
            if data is None:
                return
            data.folder = folder
            VideoStore.save(media_path, data)

    @staticmethod
    def update_folder_bulk(media_paths: list[str], folder: str) -> None:
        """Update the folder field for multiple videos."""
        for mp in media_paths:
            VideoStore.update_folder(mp, folder)

    @staticmethod
    def update_position(media_path: str, position_ms: int) -> None:
        """Update last playback position."""
        with _store_lock:
            data = VideoStore.load(media_path)
            if data is None:
                return
            data.last_position_ms = int(position_ms)
            VideoStore.save(media_path, data)

    @staticmethod
    def list_bookmark_categories(output_dirs: "Union[str, list[str]]") -> list[str]:
        """Collect unique non-empty bookmark categories across all videos.

        Accepts a single path (legacy) or a list of paths.
        """
        dirs = _normalize_dirs(output_dirs)
        categories: set[str] = set()
        for output_dir in dirs:
            if not os.path.isdir(output_dir):
                continue
            for fname in os.listdir(output_dir):
                ext = os.path.splitext(fname)[1].lower()
                if ext not in (".mp4", ".mp3"):
                    continue
                media_path = os.path.join(output_dir, fname)
                data = VideoStore.load(media_path)
                if data is None:
                    continue
                for bk in data.bookmarks or []:
                    cat = (bk.get("category") or "").strip()
                    if cat:
                        categories.add(cat)
        return sorted(categories)

    @staticmethod
    def update_notes(media_path: str, notes: str) -> None:
        """Update only the notes field in the sidecar JSON."""
        with _store_lock:
            data = VideoStore.load(media_path)
            if data is None:
                return
            data.notes = notes
            VideoStore.save(media_path, data)

    @staticmethod
    def update_bookmarks(media_path: str, bookmarks: list) -> None:
        """Update only the bookmarks list in the sidecar JSON."""
        with _store_lock:
            data = VideoStore.load(media_path)
            if data is None:
                return
            data.bookmarks = bookmarks
            VideoStore.save(media_path, data)

    @staticmethod
    def rename_video(media_path: str, new_title: str) -> str:
        """Rename a video: updates the title in JSON and renames files on disk.

        Returns the new media_path.  Raises OSError on filesystem errors.
        """
        data = VideoStore.load(media_path)
        if data is None:
            raise FileNotFoundError(f"JSON sidecar not found for {media_path}")

        # Sanitise the new title for use as a filename
        safe = re.sub(r'[<>:"/\\|?*]', '_', new_title).strip().rstrip('.')
        if not safe:
            safe = "video"
        # Limit length (keep room for extension)
        safe = safe[:80]

        directory = os.path.dirname(media_path)
        ext = os.path.splitext(media_path)[1]          # e.g. ".mp4"
        old_json = _resolve_json_path(media_path)

        new_media_name = safe + ext
        new_media_path = os.path.join(directory, new_media_name)
        new_json_path = _json_path(new_media_path)

        # Avoid overwriting an existing different file
        if os.path.normcase(new_media_path) != os.path.normcase(media_path):
            # If target already exists, add a short suffix
            counter = 1
            while os.path.exists(new_media_path) or os.path.exists(new_json_path):
                new_media_name = f"{safe}_{counter}{ext}"
                new_media_path = os.path.join(directory, new_media_name)
                new_json_path = _json_path(new_media_path)
                counter += 1

        # Rename files on disk
        if os.path.normcase(new_media_path) != os.path.normcase(media_path):
            os.rename(media_path, new_media_path)
            if old_json and os.path.isfile(old_json):
                os.rename(old_json, new_json_path)

        # Update JSON content
        data.title = new_title
        data.media_file = new_media_name
        VideoStore.save(new_media_path, data)

        return new_media_path

    @staticmethod
    def delete_video(media_path: str) -> None:
        """Delete the media file and its JSON sidecar."""
        jp_new = _json_path(media_path)
        jp_legacy = _legacy_json_path(media_path)
        # Load data first to know the video_id for thumb cleanup
        data = VideoStore.load(media_path)
        # Always delete the media file and the new-format sidecar
        for p in (media_path, jp_new):
            if os.path.isfile(p):
                os.remove(p)
        # Only delete legacy sidecar if no other media file shares it
        if os.path.isfile(jp_legacy):
            base = os.path.splitext(media_path)[0]
            ext = os.path.splitext(media_path)[1]
            other_ext = ".mp3" if ext.lower() == ".mp4" else ".mp4"
            other_media = base + other_ext
            if not os.path.isfile(other_media):
                os.remove(jp_legacy)
        # Remove cached thumbnail (only if no other media with same video_id)
        if data and data.video_id:
            output_dir = os.path.dirname(media_path)
            tp = os.path.join(output_dir, ".thumbs", f"{data.video_id}.jpg")
            base = os.path.splitext(media_path)[0]
            ext = os.path.splitext(media_path)[1]
            other_ext = ".mp3" if ext.lower() == ".mp4" else ".mp4"
            other_media = base + other_ext
            if os.path.isfile(tp) and not os.path.isfile(other_media):
                try:
                    os.remove(tp)
                except OSError:
                    pass

    @staticmethod
    def migrate_existing_media(output_dirs: "Union[str, list[str]]") -> int:
        """Create JSON sidecars for media files that don't have one yet.

        Accepts a single path (legacy) or a list of paths.
        Returns the total number of files migrated across all dirs.
        """
        dirs = _normalize_dirs(output_dirs)
        count = 0
        for output_dir in dirs:
            if not os.path.isdir(output_dir):
                continue
            for fname in os.listdir(output_dir):
                ext = os.path.splitext(fname)[1].lower()
                if ext not in (".mp4", ".mp3"):
                    continue
                media_path = os.path.join(output_dir, fname)
                if _resolve_json_path(media_path):
                    continue

                # Create a minimal VideoData from filesystem info
                title = os.path.splitext(fname)[0]
                stat = os.stat(media_path)
                created = datetime.fromtimestamp(
                    stat.st_mtime, tz=timezone.utc
                ).isoformat()

                data = VideoData(
                    video_id=uuid.uuid4().hex[:12],
                    title=title,
                    platform=UNKNOWN,
                    media_file=fname,
                    format=ext.lstrip("."),
                    created_at=created,
                )
                VideoStore.save(media_path, data)
                count += 1

        return count
