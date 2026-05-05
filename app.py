"""Super Video Downloader — entry point."""

import os
import sys

# Use Qt's FFmpeg multimedia backend instead of Windows Media Foundation.
# MF has known audio stutter/glitch issues in QMediaPlayer; FFmpeg is more
# robust for long playback and gapless auto-advance. Must be set BEFORE any
# PySide6.QtMultimedia import.
os.environ.setdefault("QT_MEDIA_BACKEND", "ffmpeg")

# Set Windows AppUserModelID so the taskbar shows our icon, not Python's.
# Also raise the process scheduling priority a notch so the audio thread
# gets fewer OS-level preemptions (media apps commonly do this to kill
# micro-stutter during playback).
if sys.platform == "win32":
    import ctypes
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
        "com.supervideodownloader.app"
    )
    try:
        ABOVE_NORMAL_PRIORITY_CLASS = 0x00008000
        _kernel32 = ctypes.windll.kernel32
        _kernel32.SetPriorityClass(
            _kernel32.GetCurrentProcess(), ABOVE_NORMAL_PRIORITY_CLASS
        )
    except Exception:
        pass

from dotenv import load_dotenv
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from core.store import VideoStore
from ui.main_window import MainWindow, DARK_STYLE

load_dotenv()


def main():
    # Ensure output directory exists
    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
    os.makedirs(output_dir, exist_ok=True)

    # Migrate existing media files that don't have JSON sidecars yet
    VideoStore.migrate_existing_media(output_dir)

    api_key = os.getenv("DEEPGRAM_API_KEY", "")

    app = QApplication(sys.argv)
    app.setStyleSheet(DARK_STYLE)

    # App icon (Alt+Tab, taskbar, title bar)
    icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")
    if os.path.isfile(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    window = MainWindow(api_key=api_key)
    window.history_panel.refresh()

    # Install console redirect so prints appear in the Console tab
    window.console_panel.install()

    window.show()

    exit_code = app.exec()

    # Restore original streams before exiting
    window.console_panel.uninstall()

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
