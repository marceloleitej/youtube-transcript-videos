"""Video history panel — sidebar with filters, folders, and clickable video list."""

import html
import os
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from PySide6.QtCore import Qt, QThread, Signal, Slot
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from core.platform_detect import ALL_PLATFORMS, FACEBOOK, INSTAGRAM, TIKTOK, YOUTUBE
from core.store import VideoStore
from core.thumbnails import ensure_thumbnail, has_thumb, thumb_path

# Badge colors per platform
_BADGE_COLORS = {
    YOUTUBE: "#FF0000",
    TIKTOK: "#00f2ea",
    INSTAGRAM: "#E1306C",
    FACEBOOK: "#1877F2",
}

_BADGE_LABELS = {
    YOUTUBE: "YT",
    TIKTOK: "TT",
    INSTAGRAM: "IG",
    FACEBOOK: "FB",
}

_MENU_STYLE = (
    "QMenu { background-color: #1c1c2e; color: #f0f0f5; border: 1px solid #2f3056; "
    "border-radius: 8px; padding: 4px; }"
    "QMenu::item { padding: 7px 22px; border-radius: 4px; }"
    "QMenu::item:selected { background-color: #e94560; }"
)


# ─── Folder path helpers ───────────────────────────────────────
# Folders support a simple "/" hierarchy. E.g. "Games/Resident Evil"
# is a subfolder of "Games". Top-level folders have no "/".

def folder_parts(folder: str) -> list[str]:
    return [p.strip() for p in (folder or "").split("/") if p.strip()]


def folder_depth(folder: str) -> int:
    return len(folder_parts(folder))


def folder_leaf(folder: str) -> str:
    parts = folder_parts(folder)
    return parts[-1] if parts else ""


def folder_belongs_to(folder: str, ancestor: str) -> bool:
    """Is `folder` inside `ancestor` (or equal to it)?"""
    if not ancestor:
        return True
    return folder == ancestor or folder.startswith(ancestor + "/")


def expand_ancestors(folders: list[str]) -> list[str]:
    """Return all folders plus any missing ancestor folders, deduped.

    If the data has 'Games/Resident Evil' but no 'Games' entry, we still
    want 'Games' to appear as a collapsible header in the UI.
    """
    seen: set[str] = set()
    for f in folders:
        parts = folder_parts(f)
        for i in range(1, len(parts) + 1):
            seen.add("/".join(parts[:i]))
    return sorted(seen)


def _format_duration(seconds: float) -> str:
    s = int(seconds)
    if s <= 0:
        return ""
    m, sec = divmod(s, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{sec:02d}"
    return f"{m}:{sec:02d}"


def _format_date(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso)
        return dt.strftime("%d/%m/%Y")
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Folder header (collapsible)
# ---------------------------------------------------------------------------

class FolderHeaderWidget(QFrame):
    """Collapsible header for a folder section."""

    toggled = Signal(str, bool)  # folder_name, is_collapsed

    def __init__(self, folder_name: str, count: int, collapsed: bool = False, parent=None):
        super().__init__(parent)
        self._folder = folder_name
        self._collapsed = collapsed
        self.setObjectName("folderHeader")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(28)

        layout = QHBoxLayout(self)
        depth = folder_depth(folder_name)
        indent = max(0, depth - 1) * 14  # 14px per extra hierarchy level
        layout.setContentsMargins(8 + indent, 2, 8, 2)
        layout.setSpacing(6)

        self._arrow = QLabel("\u25B6" if collapsed else "\u25BC")
        self._arrow.setFixedWidth(14)
        self._arrow.setStyleSheet("color: #e94560; font-size: 10px; background: transparent;")
        layout.addWidget(self._arrow)

        display = folder_leaf(folder_name) if folder_name else "Sem pasta"
        self._title = QLabel(f"<b>{display}</b>")
        self._title.setTextFormat(Qt.RichText)
        if folder_name:
            color = "#e94560" if depth == 1 else "#d9577a"
        else:
            color = "#9a9ab0"
        font_size = 12 if depth <= 1 else 11
        self._title.setStyleSheet(
            f"color: {color}; font-size: {font_size}px; background: transparent; "
            f"letter-spacing: 0.3px;"
        )
        layout.addWidget(self._title, 1)

        self._count = QLabel(f"{count}")
        self._count.setStyleSheet(
            "color: #64647d; font-size: 10px; font-weight: 600; "
            "background: #13131f; border-radius: 8px; padding: 2px 8px;"
        )
        layout.addWidget(self._count)

        self._update_style()

    @property
    def folder(self) -> str:
        return self._folder

    def _update_style(self):
        self.setStyleSheet(
            "#folderHeader { background-color: #242438; border: 1px solid #2f3056; border-radius: 6px; }"
            "#folderHeader:hover { background-color: #2d2d46; border: 1px solid #e94560; }"
        )

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._collapsed = not self._collapsed
            self._arrow.setText("\u25B6" if self._collapsed else "\u25BC")
            self.toggled.emit(self._folder, self._collapsed)
        super().mousePressEvent(event)


# ---------------------------------------------------------------------------
# Background thumbnail fetcher
# ---------------------------------------------------------------------------

class _ThumbFetchWorker(QThread):
    """Download missing thumbnails in background, emits (video_id, local_path)."""

    thumb_ready = Signal(str, str)

    def __init__(self, jobs: list[tuple[str, str, str]], parent=None):
        # jobs: list of (output_dir, video_id, thumbnail_url) — each video
        # can come from a different media source folder.
        super().__init__(parent)
        self._jobs = list(jobs)

    def run(self):
        for output_dir, vid, url in self._jobs:
            p = ensure_thumbnail(output_dir, vid, url)
            if p:
                self.thumb_ready.emit(vid, p)


# ---------------------------------------------------------------------------
# Single video item
# ---------------------------------------------------------------------------

class VideoHistoryItem(QFrame):
    """Single item in the video history list."""

    clicked = Signal(str)               # media_path
    delete_requested = Signal(str)      # media_path
    transcribe_requested = Signal(str)  # media_path
    platform_change_requested = Signal(str, str)  # media_path, new_platform
    rename_requested = Signal(str, str)            # media_path, new_title
    folder_change_requested = Signal(str, str)     # media_path, new_folder

    def __init__(self, info: dict, folders: list[str] | None = None,
                 thumb_local_path: str | None = None, parent=None):
        super().__init__(parent)
        self._media_path = info["media_path"]
        self._current_folder = info.get("folder", "")
        self._folders = folders or []
        self._video_id = info.get("video_id", "")
        self._selected = False
        self.setObjectName("historyItem")
        self.setCursor(Qt.PointingHandCursor)
        self.setFrameShape(QFrame.StyledPanel)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(10)

        # Thumbnail (if available) with platform badge overlay
        platform = info.get("platform", "")
        self._thumb_label = QLabel()
        self._thumb_label.setFixedSize(72, 48)
        self._thumb_label.setAlignment(Qt.AlignCenter)
        self._thumb_label.setStyleSheet(
            "background-color: #13131f; border-radius: 4px;"
        )
        self.set_thumbnail(thumb_local_path, platform)
        layout.addWidget(self._thumb_label)

        # Small platform badge overlay inside the thumbnail corner
        badge_text = _BADGE_LABELS.get(platform, "??")
        badge_color = _BADGE_COLORS.get(platform, "#666666")
        self.badge = QLabel(badge_text, self._thumb_label)
        self.badge.setFixedSize(22, 14)
        self.badge.setAlignment(Qt.AlignCenter)
        self.badge.setStyleSheet(
            f"background-color: {badge_color}; color: white; font-weight: 700; "
            f"font-size: 9px; border-radius: 3px;"
        )
        self.badge.move(2, 2)
        self.badge.show()

        # Info column
        info_col = QVBoxLayout()
        info_col.setSpacing(2)

        # Line 1: title + format
        title_text = info.get("title", "Sem titulo")
        if len(title_text) > 40:
            title_text = title_text[:37] + "..."
        fmt_tag = info.get("format", "mp4").upper()
        safe_title = html.escape(title_text)
        line1 = QLabel(
            f"{safe_title}  <span style='color:#64647d;font-size:10px;font-weight:600;"
            f"background-color:#13131f;padding:2px 6px;border-radius:4px;'>&nbsp;{html.escape(fmt_tag)}&nbsp;</span>"
        )
        line1.setTextFormat(Qt.RichText)
        line1.setStyleSheet("font-size: 13px; font-weight: 500; background: transparent; color: #f0f0f5;")
        info_col.addWidget(line1)

        # Line 2: date + duration + transcription status
        date_str = _format_date(info.get("created_at", ""))
        dur_str = _format_duration(info.get("duration_seconds", 0))
        has_trans = info.get("has_transcription", False)

        parts = []
        if date_str:
            parts.append(date_str)
        if dur_str:
            parts.append(dur_str)

        if has_trans:
            parts.append("<span style='color:#4caf50;'>\u2713 Transcrito</span>")
        else:
            parts.append("<span style='color:#64647d;'>\u25CB Sem transcri\u00e7\u00e3o</span>")

        line2 = QLabel("  \u00b7  ".join(parts))
        line2.setTextFormat(Qt.RichText)
        line2.setStyleSheet("font-size: 11px; color: #9a9ab0; background: transparent;")
        info_col.addWidget(line2)

        layout.addLayout(info_col, 1)

        self._update_style()

    @property
    def media_path(self) -> str:
        return self._media_path

    @property
    def video_id(self) -> str:
        return self._video_id

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self._update_style()

    def set_thumbnail(self, local_path: str | None, platform: str = "") -> None:
        """Set thumbnail image; if missing, show a colored placeholder."""
        if local_path and os.path.isfile(local_path):
            pix = QPixmap(local_path)
            if not pix.isNull():
                pix = pix.scaled(72, 48, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                self._thumb_label.setPixmap(pix)
                self._thumb_label.setStyleSheet(
                    "background-color: #000; border-radius: 4px;"
                )
                return
        # Placeholder: platform letter on a dim background
        letter = _BADGE_LABELS.get(platform, "?")
        color = _BADGE_COLORS.get(platform, "#3a3b66")
        self._thumb_label.clear()
        self._thumb_label.setText(f"<span style='color:{color};font-weight:700;font-size:18px;'>{letter}</span>")
        self._thumb_label.setTextFormat(Qt.RichText)
        self._thumb_label.setStyleSheet(
            "background-color: #13131f; border: 1px solid #2f3056; border-radius: 4px;"
        )

    def _update_style(self) -> None:
        if self._selected:
            self.setStyleSheet(
                "#historyItem { background-color: #2d2d46; border: 1px solid #e94560; border-radius: 8px; }"
            )
        else:
            self.setStyleSheet(
                "#historyItem { background-color: #1c1c2e; border: 1px solid #2f3056; border-radius: 8px; }"
                "#historyItem:hover { background-color: #242438; border: 1px solid #3a3b66; }"
            )

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self._media_path)
        super().mousePressEvent(event)

    def _show_context_menu(self, pos):
        menu = QMenu(self)
        menu.setStyleSheet(_MENU_STYLE)
        act_transcribe = menu.addAction("Transcrever")
        act_open = menu.addAction("Abrir pasta")
        act_rename = menu.addAction("Renomear")

        # Platform change submenu
        platform_menu = menu.addMenu("Alterar plataforma")
        platform_menu.setStyleSheet(_MENU_STYLE)
        platform_actions = {}
        for plat in ALL_PLATFORMS:
            act = platform_menu.addAction(plat)
            platform_actions[act] = plat

        # Folder submenu with nested hierarchy (Games > Resident Evil > ...)
        folder_menu = menu.addMenu("Enviar para pasta")
        folder_menu.setStyleSheet(_MENU_STYLE)
        folder_actions = {}

        menus_by_path = {"": folder_menu}
        for fname in self._folders:
            parts = folder_parts(fname)
            for i in range(1, len(parts) + 1):
                path = "/".join(parts[:i])
                if path in menus_by_path:
                    continue
                parent_path = "/".join(parts[:i - 1])
                parent_menu = menus_by_path.get(parent_path, folder_menu)
                leaf = parts[i - 1]
                sub = parent_menu.addMenu(leaf)
                sub.setStyleSheet(_MENU_STYLE)
                marker = "\u2713 " if path == self._current_folder else ""
                act_self = sub.addAction(f"{marker}Esta pasta ({leaf})")
                folder_actions[act_self] = path
                sub.addSeparator()
                menus_by_path[path] = sub

        folder_menu.addSeparator()
        act_new_folder = folder_menu.addAction("+ Nova pasta...")
        folder_actions[act_new_folder] = "__new__"
        if self._current_folder:
            act_remove_folder = folder_menu.addAction("Remover da pasta")
            folder_actions[act_remove_folder] = ""

        menu.addSeparator()
        act_delete = menu.addAction("Excluir")

        action = menu.exec(self.mapToGlobal(pos))
        if action is None:
            return
        if action == act_transcribe:
            self.transcribe_requested.emit(self._media_path)
        elif action == act_open:
            folder = os.path.dirname(self._media_path)
            if sys.platform == "win32":
                os.startfile(folder)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", folder])
            else:
                subprocess.Popen(["xdg-open", folder])
        elif action == act_rename:
            current_title = os.path.splitext(os.path.basename(self._media_path))[0]
            new_title, ok = QInputDialog.getText(
                self, "Renomear video", "Novo titulo:",
                text=current_title,
            )
            if ok and new_title.strip():
                self.rename_requested.emit(self._media_path, new_title.strip())
        elif action == act_delete:
            self.delete_requested.emit(self._media_path)
        elif action in platform_actions:
            self.platform_change_requested.emit(self._media_path, platform_actions[action])
        elif action in folder_actions:
            target = folder_actions[action]
            if target == "__new__":
                name, ok = QInputDialog.getText(
                    self, "Nova pasta",
                    "Nome da pasta (use '/' para criar subpasta, ex: Games/Resident Evil):",
                )
                if ok and name.strip():
                    # Normalize: strip slashes, collapse multiple
                    clean = "/".join(p.strip() for p in name.split("/") if p.strip())
                    if clean:
                        self.folder_change_requested.emit(self._media_path, clean)
            else:
                self.folder_change_requested.emit(self._media_path, target)


# ---------------------------------------------------------------------------
# Main history panel
# ---------------------------------------------------------------------------

class VideoHistoryPanel(QWidget):
    """Sidebar panel showing video history with search, filters, and folders."""

    video_selected = Signal(str)      # media_path
    video_delete = Signal(str)        # media_path
    video_transcribe = Signal(str)    # media_path
    video_platform_change = Signal(str, str)  # media_path, new_platform
    video_rename = Signal(str, str)            # media_path, new_title
    video_folder_change = Signal(list, str)    # list[media_path], new_folder

    def __init__(self, output_dirs, parent=None):
        """``output_dirs`` accepts str (legacy) or list[str] of media folders."""
        super().__init__(parent)
        if isinstance(output_dirs, str):
            self._output_dirs: list[str] = [output_dirs]
        else:
            self._output_dirs = list(output_dirs or [])
        self._videos: list[dict] = []
        self._items: list[VideoHistoryItem] = []
        self._headers: list[FolderHeaderWidget] = []
        self._selected_paths: set[str] = set()
        self._known_folders: list[str] = []
        self._folder_collapsed: dict[str, bool] = {}
        self._items_by_vid: dict[str, VideoHistoryItem] = {}
        self._thumb_worker: _ThumbFetchWorker | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Header row: title + result count
        header_row = QHBoxLayout()
        header = QLabel("Historico")
        header.setStyleSheet(
            "font-size: 18px; font-weight: 700; color: #f0f0f5; "
            "letter-spacing: 0.5px; padding: 4px 2px;"
        )
        header_row.addWidget(header)
        header_row.addStretch()
        self.count_badge = QLabel("")
        self.count_badge.setStyleSheet(
            "color: #9a9ab0; font-size: 11px; font-weight: 600; "
            "background: #242438; border-radius: 8px; padding: 2px 8px;"
        )
        header_row.addWidget(self.count_badge)
        layout.addLayout(header_row)

        # Breadcrumb — shows active filters
        self.breadcrumb = QLabel("")
        self.breadcrumb.setStyleSheet(
            "color: #e94560; font-size: 11px; font-weight: 600; "
            "padding: 2px 2px 4px 2px;"
        )
        self.breadcrumb.setVisible(False)
        self.breadcrumb.setTextFormat(Qt.RichText)
        layout.addWidget(self.breadcrumb)

        # Search
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Pesquisar...")
        self.search_input.textChanged.connect(self._apply_filters)
        layout.addWidget(self.search_input)

        # Platform filter
        self.platform_combo = QComboBox()
        self.platform_combo.addItem("Todas", "")
        self.platform_combo.addItem("YouTube", YOUTUBE)
        self.platform_combo.addItem("TikTok", TIKTOK)
        self.platform_combo.addItem("Instagram", INSTAGRAM)
        self.platform_combo.addItem("Facebook", FACEBOOK)
        self.platform_combo.currentIndexChanged.connect(self._apply_filters)
        layout.addWidget(self.platform_combo)

        # Folder filter
        self.folder_combo = QComboBox()
        self.folder_combo.addItem("Todas as pastas", None)
        self.folder_combo.addItem("Sem pasta", "")
        self.folder_combo.currentIndexChanged.connect(self._apply_filters)
        layout.addWidget(self.folder_combo)

        # Date filter
        self.date_combo = QComboBox()
        self.date_combo.addItems(["Todas", "Hoje", "7 dias", "30 dias"])
        self.date_combo.currentIndexChanged.connect(self._apply_filters)
        layout.addWidget(self.date_combo)

        # Scroll area for items
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.list_widget = QWidget()
        self.list_layout = QVBoxLayout(self.list_widget)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(4)
        self.list_layout.addStretch()
        self.scroll.setWidget(self.list_widget)
        layout.addWidget(self.scroll, 1)

        # Empty label
        self.empty_label = QLabel()
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setWordWrap(True)
        self.empty_label.setTextFormat(Qt.RichText)
        self.empty_label.setStyleSheet(
            "color: #9a9ab0; font-size: 13px; padding: 40px 20px; line-height: 150%;"
        )
        self.empty_label.setVisible(False)
        layout.addWidget(self.empty_label)

    # -- Public API --

    @property
    def selected_path(self) -> str:
        """Return the primary selected path (first in set, or empty)."""
        if self._selected_paths:
            return next(iter(self._selected_paths))
        return ""

    def set_selected_path(self, path: str) -> None:
        """Set single selection (clears multi-select)."""
        self._selected_paths = {path} if path else set()

    def visible_media_paths(self, fmt: str | None = None) -> list[str]:
        """Return media paths currently visible under the active filters.

        fmt: 'mp3' | 'mp4' | None (no filter).
        Ordering matches the history list display order.
        """
        result = []
        for v in self._get_filtered_videos():
            if fmt is not None and v.get("format") != fmt:
                continue
            result.append(v["media_path"])
        return result

    def set_output_dir(self, path: str) -> None:
        """Legacy single-folder setter — preserved for backwards-compat."""
        self._output_dirs = [path] if path else []

    def set_output_dirs(self, paths: list[str]) -> None:
        """Replace the full list of media source folders and refresh."""
        self._output_dirs = list(paths or [])

    @property
    def output_dirs(self) -> list[str]:
        return list(self._output_dirs)

    @property
    def primary_output_dir(self) -> str:
        """The folder where new downloads on this machine should land."""
        return self._output_dirs[0] if self._output_dirs else ""

    def refresh(self) -> None:
        """Reload video list from disk and rebuild UI."""
        self._videos = VideoStore.list_videos(self._output_dirs)
        raw_folders = [v["folder"] for v in self._videos if v.get("folder")]
        # Include implicit ancestor folders (e.g. "Games/RE" implies "Games")
        self._known_folders = expand_ancestors(raw_folders)
        self._refresh_folder_combo()
        self._rebuild_list()

    # -- Internal --

    def _refresh_folder_combo(self) -> None:
        """Rebuild folder combo items preserving current selection.

        Sub-folders are visually indented (e.g. '  Resident Evil' under 'Games').
        """
        prev = self.folder_combo.currentData()
        self.folder_combo.blockSignals(True)
        self.folder_combo.clear()
        self.folder_combo.addItem("Todas as pastas", None)
        self.folder_combo.addItem("Sem pasta", "")
        for fn in self._known_folders:
            depth = folder_depth(fn)
            indent = "    " * (depth - 1)  # 4 spaces per level
            label = f"{indent}{folder_leaf(fn)}" if depth > 1 else fn
            self.folder_combo.addItem(label, fn)

        # Restore previous selection
        for i in range(self.folder_combo.count()):
            if self.folder_combo.itemData(i) == prev:
                self.folder_combo.setCurrentIndex(i)
                break
        self.folder_combo.blockSignals(False)

    def _rebuild_list(self) -> None:
        """Clear and recreate all items, applying current filters."""
        # Remove old items and headers
        for item in self._items:
            self.list_layout.removeWidget(item)
            item.deleteLater()
        self._items.clear()
        self._items_by_vid.clear()
        for hdr in self._headers:
            self.list_layout.removeWidget(hdr)
            hdr.deleteLater()
        self._headers.clear()

        filtered = self._get_filtered_videos()

        is_empty = len(filtered) == 0
        if is_empty:
            if not self._videos:
                # Truly empty library
                self.empty_label.setText(
                    "<b>Nenhum video ainda</b><br><br>"
                    "Cole uma URL na aba <b style='color:#e94560;'>Download</b> "
                    "para comecar."
                )
            else:
                # Videos exist but filters hide them all
                self.empty_label.setText(
                    "<b>Nenhum resultado</b><br><br>"
                    "Tente limpar os filtros ou a busca."
                )
        self.empty_label.setVisible(is_empty)
        self.scroll.setVisible(not is_empty)

        folder_filter = self.folder_combo.currentData()
        search = self.search_input.text().strip()
        use_groups = folder_filter is None and not search

        if use_groups:
            self._build_grouped(filtered)
        else:
            self._build_flat(filtered)

        self._update_breadcrumb(filtered)
        self._kick_thumb_fetch(filtered)

    def _update_breadcrumb(self, filtered: list[dict]) -> None:
        """Show active filter summary above the list."""
        parts = []
        folder_filter = self.folder_combo.currentData()
        platform = self.platform_combo.currentData()
        date_idx = self.date_combo.currentIndex()
        search = self.search_input.text().strip()

        if folder_filter == "":
            parts.append("Sem pasta")
        elif folder_filter:
            # Show full path with chevron separators
            parts.append(folder_filter.replace("/", " › "))
        if platform:
            parts.append(platform)
        if date_idx == 1:
            parts.append("hoje")
        elif date_idx == 2:
            parts.append("ultimos 7 dias")
        elif date_idx == 3:
            parts.append("ultimos 30 dias")
        if search:
            parts.append(f'"{search}"')

        self.count_badge.setText(f"{len(filtered)}")
        if parts:
            self.breadcrumb.setText(" \u203A ".join(parts))
            self.breadcrumb.setVisible(True)
        else:
            self.breadcrumb.setVisible(False)

    def _kick_thumb_fetch(self, videos: list[dict]) -> None:
        """Spawn a worker to download any missing thumbs for the visible items.

        Each video may live in a different output_dir (Pi-synced folder vs
        local), so we look up the cache path per-video.
        """
        missing = []
        for v in videos:
            vid = v.get("video_id", "")
            url = v.get("thumbnail_url", "")
            out = self._video_dir(v)
            if not (vid and url and out):
                continue
            if has_thumb(out, vid):
                continue
            missing.append((out, vid, url))
        if not missing:
            return
        if self._thumb_worker and self._thumb_worker.isRunning():
            return  # let the current batch finish; next refresh will pick up the rest
        self._thumb_worker = _ThumbFetchWorker(missing, self)
        self._thumb_worker.thumb_ready.connect(self._on_thumb_ready)
        self._thumb_worker.start()

    @staticmethod
    def _video_dir(info: dict) -> str:
        """Return the folder a video lives in — prefer the stamp from list_videos."""
        out = info.get("output_dir")
        if out:
            return out
        path = info.get("media_path", "")
        return os.path.dirname(path) if path else ""

    @Slot(str, str)
    def _on_thumb_ready(self, video_id: str, local_path: str) -> None:
        item = self._items_by_vid.get(video_id)
        if item is not None:
            item.set_thumbnail(local_path)

    def _build_flat(self, videos: list[dict]) -> None:
        """Insert items as a flat list (no folder headers)."""
        for info in videos:
            self._insert_item(info)

    def _build_grouped(self, videos: list[dict]) -> None:
        """Insert items grouped by folder with collapsible hierarchical headers.

        Sub-folders are rendered under their parent; collapsing a parent hides
        all descendants (headers + items) as well.
        """
        groups: dict[str, list[dict]] = defaultdict(list)
        for v in videos:
            groups[v.get("folder", "")].append(v)

        # All folders to render: ones with direct items + ancestors of those
        folders_with_items = [f for f in groups.keys() if f]
        all_folders = set(folders_with_items) | set(expand_ancestors(folders_with_items))

        # Hierarchical sort: parent before children, alphabetical siblings
        def sort_key(f: str):
            return tuple(folder_parts(f))
        ordered = ["" if "" in groups else None] + sorted(all_folders, key=sort_key)
        ordered = [o for o in ordered if o is not None]

        for folder_name in ordered:
            items_in_group = groups.get(folder_name, [])
            # Compute total descendant count for header badge
            descendant_count = len(items_in_group) + sum(
                len(v) for k, v in groups.items()
                if k and folder_name and k != folder_name and k.startswith(folder_name + "/")
            )
            if folder_name == "":
                descendant_count = len(items_in_group)

            collapsed = self._folder_collapsed.get(folder_name, True)
            # Cascade: if any ancestor of this folder is collapsed, this header is hidden
            hidden_by_ancestor = self._any_ancestor_collapsed(folder_name)

            header = FolderHeaderWidget(folder_name, descendant_count, collapsed)
            header.toggled.connect(self._on_folder_toggled)
            self.list_layout.insertWidget(self.list_layout.count() - 1, header)
            self._headers.append(header)
            if hidden_by_ancestor:
                header.setVisible(False)

            for info in items_in_group:
                item = self._insert_item(info)
                if collapsed or hidden_by_ancestor:
                    item.setVisible(False)
                # Stamp the item's folder so toggle can recompute visibility
                item.setProperty("_folder", folder_name)

    def _any_ancestor_collapsed(self, folder: str) -> bool:
        """Is any strict ancestor of this folder currently collapsed?"""
        parts = folder_parts(folder)
        for i in range(1, len(parts)):  # stop BEFORE self
            ancestor = "/".join(parts[:i])
            if self._folder_collapsed.get(ancestor, True):
                return True
        return False

    def _insert_item(self, info: dict) -> VideoHistoryItem:
        """Create a VideoHistoryItem, connect signals, and insert into layout."""
        vid = info.get("video_id", "")
        out = self._video_dir(info)
        tp = thumb_path(out, vid) if (vid and out) else None
        local_thumb = tp if (tp and os.path.isfile(tp)) else None
        item = VideoHistoryItem(info, folders=self._known_folders,
                                thumb_local_path=local_thumb)
        item.clicked.connect(self._on_item_clicked)
        item.delete_requested.connect(self.video_delete.emit)
        item.transcribe_requested.connect(self.video_transcribe.emit)
        item.platform_change_requested.connect(self.video_platform_change.emit)
        item.rename_requested.connect(self.video_rename.emit)
        item.folder_change_requested.connect(self._on_folder_change_requested)
        if info["media_path"] in self._selected_paths:
            item.set_selected(True)
        self.list_layout.insertWidget(self.list_layout.count() - 1, item)
        self._items.append(item)
        if vid:
            self._items_by_vid[vid] = item
        return item

    def _get_filtered_videos(self) -> list[dict]:
        """Apply text, platform, folder, and date filters."""
        search = self.search_input.text().strip().lower()
        platform = self.platform_combo.currentData()
        folder_filter = self.folder_combo.currentData()
        date_idx = self.date_combo.currentIndex()

        now = datetime.now(timezone.utc)
        if date_idx == 1:  # Hoje
            cutoff = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif date_idx == 2:  # 7 dias
            cutoff = now - timedelta(days=7)
        elif date_idx == 3:  # 30 dias
            cutoff = now - timedelta(days=30)
        else:
            cutoff = None

        result = []
        for v in self._videos:
            # Text filter
            if search and search not in v.get("title", "").lower():
                continue
            # Platform filter
            if platform and v.get("platform") != platform:
                continue
            # Folder filter. None=all, ""=root only, "name"=that folder + subfolders
            if folder_filter is not None:
                v_folder = v.get("folder", "")
                if folder_filter == "":
                    # "Sem pasta": only items with no folder at all
                    if v_folder:
                        continue
                else:
                    # Named folder: include this folder AND any sub-folder of it
                    if not folder_belongs_to(v_folder, folder_filter):
                        continue
            # Date filter
            if cutoff:
                try:
                    created = datetime.fromisoformat(v["created_at"])
                    if created < cutoff:
                        continue
                except Exception:
                    continue
            result.append(v)
        return result

    @Slot()
    def _apply_filters(self) -> None:
        self._rebuild_list()

    @Slot(str)
    def _on_item_clicked(self, media_path: str) -> None:
        mods = QApplication.keyboardModifiers()
        if mods & Qt.ControlModifier:
            # Ctrl+click: toggle multi-select
            if media_path in self._selected_paths:
                self._selected_paths.discard(media_path)
            else:
                self._selected_paths.add(media_path)
            for item in self._items:
                item.set_selected(item.media_path in self._selected_paths)
        else:
            # Normal click: single select
            self._selected_paths = {media_path}
            for item in self._items:
                item.set_selected(item.media_path == media_path)
            self.video_selected.emit(media_path)

    @Slot(str, bool)
    def _on_folder_toggled(self, folder_name: str, collapsed: bool) -> None:
        """Toggle collapse state and cascade visibility through descendants."""
        self._folder_collapsed[folder_name] = collapsed

        current_folder = None  # which folder's items are we currently under?
        for i in range(self.list_layout.count()):
            widget = self.list_layout.itemAt(i).widget()
            if widget is None:
                continue
            if isinstance(widget, FolderHeaderWidget):
                current_folder = widget.folder
                # Sub-headers: hidden if any ancestor (including folder_name
                # when it's an ancestor of current_folder) is collapsed.
                if current_folder == folder_name:
                    widget.setVisible(not self._any_ancestor_collapsed(current_folder))
                elif folder_belongs_to(current_folder, folder_name) and current_folder != folder_name:
                    # Descendant header — visibility depends on ALL ancestors
                    widget.setVisible(not self._any_ancestor_collapsed(current_folder))
            elif isinstance(widget, VideoHistoryItem) and current_folder is not None:
                if folder_belongs_to(current_folder, folder_name):
                    # Item inside the toggled folder or a descendant: hide if
                    # this folder is collapsed OR any ancestor is collapsed
                    widget.setVisible(
                        not self._folder_collapsed.get(current_folder, True)
                        and not self._any_ancestor_collapsed(current_folder)
                    )

    @Slot(str, str)
    def _on_folder_change_requested(self, media_path: str, folder: str) -> None:
        """Handle folder change from context menu, resolving multi-select."""
        if media_path in self._selected_paths and len(self._selected_paths) > 1:
            paths = list(self._selected_paths)
        else:
            paths = [media_path]
        self.video_folder_change.emit(paths, folder)
