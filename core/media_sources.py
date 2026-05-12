"""Configuration of media source folders for the history view.

Persists a list of folders the app should scan for downloaded media,
beyond the bundled ``output/`` directory. Lets the PC app see videos
the Pi service downloads into a Syncthing-replicated folder.

Stored in ``media_sources.json`` at the repo root (per-machine, not
committed — paths are absolute and differ across machines).
"""

import json
import os
from typing import Optional

CONFIG_FILENAME = "media_sources.json"


def _config_path(repo_root: str) -> str:
    return os.path.join(repo_root, CONFIG_FILENAME)


def _default_paths(repo_root: str) -> list[str]:
    return [os.path.normpath(os.path.join(repo_root, "output"))]


def load(repo_root: str) -> list[str]:
    """Load the list of media source folders.

    Always includes the bundled ``output/`` folder first so the app has
    somewhere to write new downloads even if the user never configured
    extra sources. Missing or invalid config falls back to defaults.
    Non-existent paths are kept (so users see they configured them) but
    skipped during scans by the store.
    """
    primary = _default_paths(repo_root)[0]
    cfg = _config_path(repo_root)
    extra: list[str] = []
    if os.path.isfile(cfg):
        try:
            with open(cfg, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, list):
                extra = [str(p) for p in raw if isinstance(p, str) and p.strip()]
            elif isinstance(raw, dict) and isinstance(raw.get("paths"), list):
                extra = [str(p) for p in raw["paths"] if isinstance(p, str) and p.strip()]
        except (OSError, json.JSONDecodeError):
            extra = []

    # Normalize + de-duplicate (case-insensitive on Windows), keeping order.
    # Primary always wins as the first entry — downloads go there.
    seen: set[str] = set()
    out: list[str] = []
    for p in [primary, *extra]:
        norm = os.path.normpath(p)
        key = os.path.normcase(norm)
        if key in seen:
            continue
        seen.add(key)
        out.append(norm)
    return out


def save(repo_root: str, paths: list[str]) -> None:
    """Persist the user-configured *extra* paths (primary is implicit)."""
    primary = os.path.normcase(_default_paths(repo_root)[0])
    extras: list[str] = []
    seen: set[str] = set()
    for p in paths or []:
        if not isinstance(p, str) or not p.strip():
            continue
        norm = os.path.normpath(p)
        key = os.path.normcase(norm)
        if key == primary or key in seen:
            continue
        seen.add(key)
        extras.append(norm)
    with open(_config_path(repo_root), "w", encoding="utf-8") as f:
        json.dump(extras, f, ensure_ascii=False, indent=2)


def primary(repo_root: str) -> str:
    """The folder where new downloads on this machine land — always exists."""
    p = _default_paths(repo_root)[0]
    os.makedirs(p, exist_ok=True)
    return p


def existing(paths: "list[str] | None") -> list[str]:
    """Filter a path list down to those that exist on disk right now."""
    return [p for p in (paths or []) if os.path.isdir(p)]
