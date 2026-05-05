"""Platform detection from URL — YouTube, TikTok, Instagram, Facebook."""

from urllib.parse import urlparse

YOUTUBE = "YouTube"
TIKTOK = "TikTok"
INSTAGRAM = "Instagram"
FACEBOOK = "Facebook"
UNKNOWN = "Outro"

ALL_PLATFORMS = [YOUTUBE, TIKTOK, INSTAGRAM, FACEBOOK, UNKNOWN]


def detect_platform(url: str) -> str:
    """Detect the platform from a video URL.

    Returns one of: "YouTube", "TikTok", "Instagram", "Facebook", "Outro".
    """
    try:
        host = urlparse(url).hostname or ""
        host = host.lower().removeprefix("www.")
    except Exception:
        return UNKNOWN

    if host in ("youtube.com", "youtu.be", "m.youtube.com", "music.youtube.com"):
        return YOUTUBE
    if host in ("tiktok.com", "vt.tiktok.com", "vm.tiktok.com", "m.tiktok.com"):
        return TIKTOK
    if host in ("instagram.com", "m.instagram.com"):
        return INSTAGRAM
    if host in ("facebook.com", "fb.watch", "m.facebook.com", "web.facebook.com"):
        return FACEBOOK

    return UNKNOWN
