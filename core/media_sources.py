"""Configuration of media source folders for the history view.

Persists a list of folders the app should scan for downloaded media,
beyond the bundled ``output/`` directory. Lets the PC app see videos
the Pi service downloads into a Syncthing-replicated folder.

Stored in ``media_sources.json`` at the repo root (per-machine, not
committed — paths are absolute and differ across machines).

Config schema (all fields optional, accepted forms):

- ``["path1", "path2"]``  — extras only (legacy)
- ``{"paths": [...]}``    — extras only (legacy dict)
- ``{"primary": "...", "paths": [...]}`` — primary override + extras

When ``primary`` is set, new downloads land there instead of repo ``output/``.
Used by Marcelo to point the PC at the Syncthing folder so every download
replicates to the Pi automatically.
"""

import json
import os

CONFIG_FILENAME = "media_sources.json"


def _config_path(repo_root: str) -> str:
    return os.path.join(repo_root, CONFIG_FILENAME)


def _fallback_primary(repo_root: str) -> str:
    return os.path.normpath(os.path.join(repo_root, "output"))


def _read_raw(repo_root: str) -> "dict | list | None":
    cfg = _config_path(repo_root)
    if not os.path.isfile(cfg):
        return None
    try:
        with open(cfg, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _parse(raw: "dict | list | None", repo_root: str) -> "tuple[str, list[str]]":
    """Return ``(primary_path, extras)`` from a parsed config blob."""
    fallback = _fallback_primary(repo_root)
    if isinstance(raw, list):
        extras = [str(p) for p in raw if isinstance(p, str) and p.strip()]
        return fallback, extras
    if isinstance(raw, dict):
        prim_raw = raw.get("primary")
        prim = os.path.normpath(prim_raw) if isinstance(prim_raw, str) and prim_raw.strip() else fallback
        paths = raw.get("paths")
        extras = (
            [str(p) for p in paths if isinstance(p, str) and p.strip()]
            if isinstance(paths, list)
            else []
        )
        return prim, extras
    return fallback, []


def load(repo_root: str) -> list[str]:
    """Load the full list of media source folders to scan.

    Primary is always first (new downloads land there). Extras come after,
    de-duplicated case-insensitively. Non-existent paths are kept (user can
    still see them in the UI) but skipped during scans by the store.
    """
    prim, extras = _parse(_read_raw(repo_root), repo_root)
    seen: set[str] = set()
    out: list[str] = []
    for p in [prim, *extras]:
        norm = os.path.normpath(p)
        key = os.path.normcase(norm)
        if key in seen:
            continue
        seen.add(key)
        out.append(norm)
    return out


def save(repo_root: str, paths: list[str]) -> None:
    """Persist the user-configured *extra* paths, preserving the primary override.

    The primary path (if previously set in the config) is preserved across
    saves — only extras are rewritten by this call.
    """
    raw = _read_raw(repo_root)
    prim, _ = _parse(raw, repo_root)
    primary_key = os.path.normcase(prim)

    extras: list[str] = []
    seen: set[str] = set()
    for p in paths or []:
        if not isinstance(p, str) or not p.strip():
            continue
        norm = os.path.normpath(p)
        key = os.path.normcase(norm)
        if key == primary_key or key in seen:
            continue
        seen.add(key)
        extras.append(norm)

    payload: "dict | list"
    if isinstance(raw, dict) and "primary" in raw:
        payload = {"primary": prim, "paths": extras}
    else:
        payload = extras
    with open(_config_path(repo_root), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def primary(repo_root: str) -> str:
    """The folder where new downloads on this machine land — always exists."""
    p, _ = _parse(_read_raw(repo_root), repo_root)
    os.makedirs(p, exist_ok=True)
    return p


def set_primary(repo_root: str, path: str) -> None:
    """Persist a new primary path, keeping current extras intact."""
    raw = _read_raw(repo_root)
    _, extras = _parse(raw, repo_root)
    prim = os.path.normpath(path)
    payload = {"primary": prim, "paths": extras}
    with open(_config_path(repo_root), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def existing(paths: "list[str] | None") -> list[str]:
    """Filter a path list down to those that exist on disk right now."""
    return [p for p in (paths or []) if os.path.isdir(p)]
