"""Embedded video/audio player with speed control, keyboard shortcuts, and bookmarks."""

import os

from PySide6.QtCore import Qt, QSize, QTimer, QUrl, QEvent, Signal, Slot
from PySide6.QtGui import QCursor, QKeySequence, QShortcut
from PySide6.QtMultimedia import QAudioOutput, QMediaDevices, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from core.store import VideoStore
from ui import icons

from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSlider,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


def _fmt_time(ms: int) -> str:
    """Format milliseconds as mm:ss or hh:mm:ss."""
    if ms < 0:
        ms = 0
    total_s = ms // 1000
    h, rem = divmod(total_s, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


SPEEDS = [0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0]


class BookmarkDialog(QDialog):
    """Dialog to create or edit a bookmark — asks for name and category."""

    def __init__(
        self,
        existing_categories: list[str],
        title: str = "Novo marcador",
        initial_name: str = "",
        initial_category: str = "",
        time_label: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumSize(380, 160)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        if time_label:
            lbl = QLabel(f"Tempo: <b>{time_label}</b>")
            lbl.setStyleSheet("color: #9a9ab0; font-size: 12px;")
            layout.addWidget(lbl)

        form = QFormLayout()
        form.setSpacing(8)

        self.name_edit = QLineEdit(initial_name)
        self.name_edit.setPlaceholderText("Nome do marcador")
        form.addRow("Nome:", self.name_edit)

        self.category_combo = QComboBox()
        self.category_combo.setEditable(True)
        self.category_combo.addItem("")  # empty = no category
        for c in existing_categories:
            self.category_combo.addItem(c)
        if initial_category:
            idx = self.category_combo.findText(initial_category)
            if idx >= 0:
                self.category_combo.setCurrentIndex(idx)
            else:
                self.category_combo.setEditText(initial_category)
        self.category_combo.lineEdit().setPlaceholderText("(sem categoria)")
        form.addRow("Categoria:", self.category_combo)

        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.name_edit.setFocus()
        self.name_edit.selectAll()

    def values(self) -> tuple[str, str]:
        return self.name_edit.text().strip(), self.category_combo.currentText().strip()


class VideoPlayer(QWidget):
    """Embedded media player with playback controls, speed, shortcuts, bookmarks."""

    bookmarks_changed = Signal(str, list)  # media_path, bookmarks list
    position_saved = Signal(str, int)       # media_path, position_ms
    notes_changed = Signal(str, str)        # media_path, notes text

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_audio_only = False
        self._seeking = False
        self._current_media_path = ""
        self._bookmarks: list[dict] = []
        self._is_fullscreen = False
        self._fs_shortcuts: list[QShortcut] = []
        self._fs_controls_wrapper: QWidget | None = None
        self._video_parent_layout = None
        # Collapse state per bookmark category (default collapsed = False = expanded)
        self._bookmark_cat_collapsed: dict[str, bool] = {}
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._hide_fs_controls)

        # Poll cursor position while in fullscreen (QVideoWidget on Windows
        # swallows mouse events, so we can't rely on filters alone).
        self._cursor_poll_timer = QTimer(self)
        self._cursor_poll_timer.setInterval(150)
        self._cursor_poll_timer.timeout.connect(self._poll_cursor)
        self._last_cursor_pos = None

        # Resume-position state
        self._pending_start_ms = 0
        self._last_saved_position = 0
        self._save_timer = QTimer(self)
        self._save_timer.setInterval(5000)  # flush every 5s during playback
        self._save_timer.timeout.connect(self._save_position_now)

        # Notes debounce — flush 1.5s after typing stops
        self._notes_save_timer = QTimer(self)
        self._notes_save_timer.setSingleShot(True)
        self._notes_save_timer.setInterval(1500)
        self._notes_save_timer.timeout.connect(self._flush_notes)
        self._suppress_notes_signal = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # --- Video display area with side bookmarks ---
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(8)

        video_container = QVBoxLayout()
        video_container.setContentsMargins(0, 0, 0, 0)
        video_container.setSpacing(0)
        self._video_parent_layout = video_container

        self.video_widget = QVideoWidget()
        self.video_widget.setMinimumHeight(240)
        self.video_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        video_container.addWidget(self.video_widget, 1)

        self.audio_label = QLabel("Audio MP3")
        self.audio_label.setAlignment(Qt.AlignCenter)
        self.audio_label.setStyleSheet(
            "font-size: 22px; font-weight: 600; color: #e94560; "
            "background-color: #1c1c2e; border-radius: 10px; padding: 60px 20px;"
        )
        self.audio_label.setVisible(False)
        video_container.addWidget(self.audio_label, 1)

        self.placeholder = QLabel("Selecione um video para reproduzir")
        self.placeholder.setAlignment(Qt.AlignCenter)
        self.placeholder.setStyleSheet(
            "font-size: 15px; color: #8585a0; padding: 60px;"
        )
        video_container.addWidget(self.placeholder, 1)

        body.addLayout(video_container, 1)

        # Bookmarks panel (right side)
        self.bookmarks_panel = self._build_bookmarks_panel()
        body.addWidget(self.bookmarks_panel)
        self.bookmarks_panel.setVisible(False)

        layout.addLayout(body, 1)

        # --- Controls bar (in its own widget so we can reparent it to fullscreen) ---
        self.controls_bar = QWidget()
        self.controls_bar.setLayout(self._build_controls())
        layout.addWidget(self.controls_bar)

        # Shortcut hint bar (grouped visually with separators)
        def _kbd(text):
            return (
                f"<span style='background:#242438;color:#f0f0f5;"
                f"border-radius:3px;padding:1px 6px;font-weight:600;"
                f"font-family:Consolas,monospace;'>&nbsp;{text}&nbsp;</span>"
            )
        self.hint_label = QLabel(
            f"{_kbd('Space')} play/pause &nbsp;&nbsp; "
            f"{_kbd('\u2190')}{_kbd('\u2192')} +/- 5s &nbsp;&nbsp; "
            f"{_kbd('J')}{_kbd('L')} +/- 10s &nbsp;&nbsp; "
            f"{_kbd('B')} marcador &nbsp;&nbsp; "
            f"{_kbd('F')} tela cheia &nbsp;&nbsp; "
            f"{_kbd('&lt;')}{_kbd('&gt;')} velocidade &nbsp;&nbsp; "
            f"{_kbd('M')} mute"
        )
        self.hint_label.setTextFormat(Qt.RichText)
        self.hint_label.setStyleSheet("font-size: 11px; color: #9a9ab0; padding: 6px 10px;")
        self.hint_label.setWordWrap(True)
        layout.addWidget(self.hint_label)

        # --- Media objects ---
        self.audio_output = QAudioOutput()
        self.audio_output.setVolume(0.8)

        self.player = QMediaPlayer()
        self.player.setAudioOutput(self.audio_output)
        self.player.setVideoOutput(self.video_widget)
        self.player.positionChanged.connect(self._on_position_changed)
        self.player.durationChanged.connect(self._on_duration_changed)
        self.player.playbackStateChanged.connect(self._on_state_changed)
        self.player.mediaStatusChanged.connect(self._on_media_status_changed)

        # Rebind to default audio device when it changes (e.g. DAC unplugged/replugged).
        # Without this, QAudioOutput keeps pointing to the old (gone) device and the
        # video plays silently until the app is restarted.
        self._media_devices = QMediaDevices(self)
        self._media_devices.audioOutputsChanged.connect(self._rebind_default_audio_device)

        self._setup_shortcuts()
        self._show_placeholder()

    # --- Layout builders ---

    def _build_bookmarks_panel(self) -> QWidget:
        """Side panel with two tabs: Marcadores (bookmarks) and Anotacoes (notes)."""
        panel = QFrame()
        panel.setObjectName("bookmarksPanel")
        panel.setMinimumWidth(220)
        panel.setMaximumWidth(320)
        panel.setStyleSheet(
            "#bookmarksPanel { background-color: #1c1c2e; border-radius: 8px; }"
        )

        outer = QVBoxLayout(panel)
        outer.setContentsMargins(6, 6, 6, 6)
        outer.setSpacing(0)

        tabs = QTabWidget()
        tabs.setStyleSheet(
            "QTabWidget::pane { border: none; background: transparent; }"
            "QTabBar::tab { background: transparent; color: #9a9ab0; "
            "padding: 6px 12px; font-size: 12px; font-weight: 600; }"
            "QTabBar::tab:selected { color: #e94560; border-bottom: 2px solid #e94560; }"
            "QTabBar::tab:hover:!selected { color: #f0f0f5; }"
        )

        # --- Marcadores tab ---
        bm_page = QWidget()
        bm_v = QVBoxLayout(bm_page)
        bm_v.setContentsMargins(4, 6, 4, 4)
        bm_v.setSpacing(6)

        self.bookmarks_list = QListWidget()
        # Windows-style multi-select with Ctrl / Shift
        self.bookmarks_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.bookmarks_list.setStyleSheet(
            "QListWidget { background-color: #0a1128; border: none; border-radius: 4px; "
            "color: #f0f0f5; font-size: 12px; }"
            "QListWidget::item { padding: 6px 8px; border-radius: 4px; }"
            "QListWidget::item:hover { background-color: #242438; }"
            "QListWidget::item:selected { background-color: #e94560; color: white; }"
        )
        self.bookmarks_list.itemDoubleClicked.connect(self._on_bookmark_activated)
        self.bookmarks_list.itemClicked.connect(self._on_bookmark_item_clicked)
        self.bookmarks_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.bookmarks_list.customContextMenuRequested.connect(self._on_bookmark_context_menu)
        bm_v.addWidget(self.bookmarks_list, 1)

        add_btn = QPushButton("+ Adicionar marcador (B)")
        add_btn.setStyleSheet(
            "QPushButton { background-color: #242438; color: #f0f0f5; "
            "border-radius: 4px; padding: 6px; font-size: 11px; }"
            "QPushButton:hover { background-color: #e94560; }"
        )
        add_btn.clicked.connect(self.add_bookmark_at_current)
        bm_v.addWidget(add_btn)

        tabs.addTab(bm_page, "Marcadores")
        tabs.setTabIcon(0, icons.star())

        # --- Anotacoes tab ---
        notes_page = QWidget()
        notes_v = QVBoxLayout(notes_page)
        notes_v.setContentsMargins(4, 6, 4, 4)
        notes_v.setSpacing(4)

        self.notes_edit = QTextEdit()
        self.notes_edit.setPlaceholderText("Suas anotacoes sobre este video...")
        self.notes_edit.setStyleSheet(
            "QTextEdit { background-color: #0a1128; color: #f0f0f5; "
            "border: none; border-radius: 4px; padding: 8px; font-size: 12px; }"
        )
        self.notes_edit.textChanged.connect(self._on_notes_changed)
        notes_v.addWidget(self.notes_edit, 1)

        self.notes_status = QLabel("")
        self.notes_status.setStyleSheet("color: #64647d; font-size: 10px; padding: 2px;")
        notes_v.addWidget(self.notes_status)

        tabs.addTab(notes_page, "Anotacoes")

        outer.addWidget(tabs)
        return panel

    def _build_controls(self) -> QHBoxLayout:
        _btn_style = (
            "QPushButton { background-color: #242438; color: #f0f0f5; "
            "font-size: 13px; font-weight: 600; border-radius: 6px; padding: 6px 10px; }"
            "QPushButton:hover { background-color: #e94560; }"
            "QPushButton:disabled { color: #555; background-color: #1c1c2e; }"
        )

        controls = QHBoxLayout()
        controls.setSpacing(8)
        controls.setContentsMargins(12, 8, 12, 8)

        icon_size = QSize(18, 18)

        self.back_btn = QPushButton()
        self.back_btn.setIcon(icons.rewind_10())
        self.back_btn.setIconSize(icon_size)
        self.back_btn.setText(" 10s")
        self.back_btn.setFixedHeight(36)
        self.back_btn.setStyleSheet(_btn_style)
        self.back_btn.setToolTip("Voltar 10s (J)")
        self.back_btn.clicked.connect(lambda: self.seek_relative(-10000))
        controls.addWidget(self.back_btn)

        self.play_btn = QPushButton()
        self.play_btn.setIcon(icons.play())
        self.play_btn.setIconSize(QSize(20, 20))
        self.play_btn.setFixedSize(56, 36)
        self.play_btn.setStyleSheet(
            "QPushButton { background-color: #e94560; color: white; "
            "border-radius: 6px; padding: 4px; }"
            "QPushButton:hover { background-color: #ff5b7a; }"
            "QPushButton:disabled { background-color: #2a2a4a; }"
        )
        self.play_btn.setToolTip("Play / Pause (Space)")
        self.play_btn.clicked.connect(self._toggle_play)
        controls.addWidget(self.play_btn)

        self.fwd_btn = QPushButton()
        self.fwd_btn.setIcon(icons.forward_10())
        self.fwd_btn.setIconSize(icon_size)
        self.fwd_btn.setText("10s ")
        self.fwd_btn.setLayoutDirection(Qt.RightToLeft)  # text left, icon right
        self.fwd_btn.setFixedHeight(36)
        self.fwd_btn.setStyleSheet(_btn_style)
        self.fwd_btn.setToolTip("Avancar 10s (L)")
        self.fwd_btn.clicked.connect(lambda: self.seek_relative(10000))
        controls.addWidget(self.fwd_btn)

        self.stop_btn = QPushButton()
        self.stop_btn.setIcon(icons.stop())
        self.stop_btn.setIconSize(icon_size)
        self.stop_btn.setFixedSize(42, 36)
        self.stop_btn.setStyleSheet(_btn_style)
        self.stop_btn.setToolTip("Parar")
        self.stop_btn.clicked.connect(self.stop)
        controls.addWidget(self.stop_btn)

        # Position slider
        self.pos_slider = QSlider(Qt.Horizontal)
        self.pos_slider.setRange(0, 0)
        self.pos_slider.sliderPressed.connect(self._on_seek_start)
        self.pos_slider.sliderReleased.connect(self._on_seek_end)
        self.pos_slider.setStyleSheet(
            "QSlider::groove:horizontal { height: 6px; background: #242438; border-radius: 3px; }"
            "QSlider::handle:horizontal { background: #e94560; width: 14px; height: 14px; "
            "margin: -4px 0; border-radius: 7px; }"
            "QSlider::sub-page:horizontal { background: #e94560; border-radius: 3px; }"
        )
        controls.addWidget(self.pos_slider, 1)

        # Time label
        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setStyleSheet("font-size: 12px; color: #ccc; min-width: 100px;")
        controls.addWidget(self.time_label)

        # Speed control
        self.speed_combo = QComboBox()
        for s in SPEEDS:
            self.speed_combo.addItem(f"{s}x", s)
        self.speed_combo.setCurrentIndex(SPEEDS.index(1.0))
        self.speed_combo.setFixedWidth(72)
        self.speed_combo.setStyleSheet(
            "QComboBox { background-color: #242438; color: #f0f0f5; "
            "border-radius: 4px; padding: 4px 8px; font-size: 12px; }"
        )
        self.speed_combo.currentIndexChanged.connect(self._on_speed_changed)
        controls.addWidget(self.speed_combo)

        # Bookmarks button (popup menu)
        self.bm_btn = QPushButton()
        self.bm_btn.setIcon(icons.bookmarks_menu())
        self.bm_btn.setIconSize(icon_size)
        self.bm_btn.setFixedSize(42, 36)
        self.bm_btn.setStyleSheet(_btn_style)
        self.bm_btn.setToolTip("Marcadores (B para adicionar no tempo atual)")
        self.bm_btn.clicked.connect(self._show_bookmarks_menu)
        controls.addWidget(self.bm_btn)

        # Volume icon (decorative)
        vol_icon = QLabel()
        vol_icon.setPixmap(icons.volume().pixmap(16, 16))
        vol_icon.setStyleSheet("padding: 0 2px;")
        controls.addWidget(vol_icon)

        self.vol_slider = QSlider(Qt.Horizontal)
        self.vol_slider.setRange(0, 100)
        self.vol_slider.setValue(80)
        self.vol_slider.setFixedWidth(90)
        self.vol_slider.valueChanged.connect(self._on_volume_changed)
        self.vol_slider.setStyleSheet(
            "QSlider::groove:horizontal { height: 4px; background: #242438; border-radius: 2px; }"
            "QSlider::handle:horizontal { background: #f0f0f5; width: 12px; height: 12px; "
            "margin: -4px 0; border-radius: 6px; }"
            "QSlider::sub-page:horizontal { background: #4caf50; border-radius: 2px; }"
        )
        controls.addWidget(self.vol_slider)

        # Fullscreen toggle
        self.fs_btn = QPushButton()
        self.fs_btn.setIcon(icons.fullscreen())
        self.fs_btn.setIconSize(icon_size)
        self.fs_btn.setFixedSize(42, 36)
        self.fs_btn.setStyleSheet(_btn_style)
        self.fs_btn.setToolTip("Tela cheia (F)")
        self.fs_btn.clicked.connect(self.toggle_fullscreen)
        controls.addWidget(self.fs_btn)

        return controls

    # --- Keyboard shortcuts ---

    def _setup_shortcuts(self) -> None:
        def sc(key: str, fn):
            s = QShortcut(QKeySequence(key), self)
            s.setContext(Qt.WidgetWithChildrenShortcut)
            s.activated.connect(fn)
            return s

        sc("Space", self._toggle_play)
        sc("K", self._toggle_play)
        sc("Left", lambda: self.seek_relative(-5000))
        sc("Right", lambda: self.seek_relative(5000))
        sc("Shift+Left", lambda: self.seek_relative(-10000))
        sc("Shift+Right", lambda: self.seek_relative(10000))
        sc("J", lambda: self.seek_relative(-10000))
        sc("L", lambda: self.seek_relative(10000))
        sc("M", self._toggle_mute)
        sc("<", self._speed_down)
        sc(",", self._speed_down)   # < without shift on some layouts
        sc(">", self._speed_up)
        sc(".", self._speed_up)
        sc("B", self.add_bookmark_at_current)
        sc("F", self.toggle_fullscreen)
        sc("Escape", self._exit_fullscreen_if_active)
        sc("Up", lambda: self._nudge_volume(5))
        sc("Down", lambda: self._nudge_volume(-5))

    # --- Public API ---

    def load_video(
        self,
        media_path: str,
        bookmarks: list[dict] | None = None,
        start_position_ms: int = 0,
        notes: str = "",
    ) -> None:
        """Load a local media file with optional bookmarks, resume position, and notes."""
        # Save the current position and any pending notes before switching
        self._save_position_now()
        self._flush_notes()

        self.player.stop()
        self._current_media_path = media_path or ""
        self._bookmarks = list(bookmarks) if bookmarks else []
        self._pending_start_ms = max(0, int(start_position_ms or 0))
        self._last_saved_position = 0
        self._refresh_bookmarks_list()

        # Load notes without triggering the save cycle
        self._suppress_notes_signal = True
        self.notes_edit.setPlainText(notes or "")
        self._suppress_notes_signal = False
        self.notes_status.setText("")

        if not media_path or not os.path.isfile(media_path):
            self._show_placeholder()
            self.bookmarks_panel.setVisible(False)
            return

        ext = os.path.splitext(media_path)[1].lower()
        self._is_audio_only = ext == ".mp3"

        self.video_widget.setVisible(not self._is_audio_only)
        self.audio_label.setVisible(self._is_audio_only)
        self.placeholder.setVisible(False)
        self.bookmarks_panel.setVisible(True)

        if self._is_audio_only:
            self.audio_label.setText(f"Audio MP3\n{os.path.basename(media_path)}")

        self.player.setSource(QUrl.fromLocalFile(media_path))
        self.player.setPlaybackRate(self.speed_combo.currentData())
        self.play_btn.setIcon(icons.play())
        self.pos_slider.setValue(0)
        self.time_label.setText("00:00 / 00:00")

    @Slot()
    def _on_notes_changed(self) -> None:
        if self._suppress_notes_signal or not self._current_media_path:
            return
        self.notes_status.setStyleSheet("color: #f5a623; font-size: 10px; padding: 2px;")
        self.notes_status.setText("digitando...")
        self._notes_save_timer.start()

    def _flush_notes(self) -> None:
        """Emit notes_changed if there's a pending edit."""
        if not self._current_media_path:
            return
        if not self._notes_save_timer.isActive() and not self.notes_status.text().startswith("digitando"):
            return
        self._notes_save_timer.stop()
        text = self.notes_edit.toPlainText()
        self.notes_changed.emit(self._current_media_path, text)
        self.notes_status.setStyleSheet("color: #4caf50; font-size: 10px; padding: 2px;")
        self.notes_status.setText("salvo")

    def _save_position_now(self) -> None:
        if not self._current_media_path:
            return
        pos = self.player.position()
        dur = self.player.duration()
        # Near the end, reset to 0 so user sees it as "watched, start over"
        if dur > 0 and pos >= dur - 10000:
            pos = 0
        if pos == self._last_saved_position:
            return
        self._last_saved_position = pos
        self.position_saved.emit(self._current_media_path, int(pos))

    def shutdown(self) -> None:
        """Stop playback and release all resources. Call this on app close."""
        try:
            self._flush_notes()
        except Exception:
            pass
        try:
            self._hide_timer.stop()
            self._cursor_poll_timer.stop()
            self._save_timer.stop()
            self._notes_save_timer.stop()
        except Exception:
            pass
        if self._is_fullscreen:
            try:
                self._exit_fullscreen()
            except Exception:
                pass
        if self._fs_controls_wrapper is not None:
            try:
                self._fs_controls_wrapper.deleteLater()
            except Exception:
                pass
            self._fs_controls_wrapper = None
        try:
            self.player.stop()
            self.player.setVideoOutput(None)
            self.player.setAudioOutput(None)
            self.player.setSource(QUrl())
            self.audio_output.deleteLater()
        except Exception:
            pass

    @Slot()
    def _rebind_default_audio_device(self) -> None:
        # Replace the audio output with a fresh one bound to the current default
        # device. Reusing the same QAudioOutput via setDevice() is unreliable on
        # the Windows MF backend after the device was unplugged.
        try:
            was_muted = self.audio_output.isMuted()
            volume = self.audio_output.volume()
            position = self.player.position()
            was_playing = self.player.playbackState() == QMediaPlayer.PlayingState

            new_output = QAudioOutput(QMediaDevices.defaultAudioOutput())
            new_output.setVolume(volume)
            new_output.setMuted(was_muted)
            self.player.setAudioOutput(new_output)
            old = self.audio_output
            self.audio_output = new_output
            try:
                old.deleteLater()
            except Exception:
                pass

            # Some backends lose the playback position on output swap.
            if position > 0:
                self.player.setPosition(position)
            if was_playing:
                self.player.play()
        except Exception:
            pass

    @Slot()
    def toggle_fullscreen(self) -> None:
        """Move the video + controls into a top-level fullscreen window (and back)."""
        if self._is_audio_only:
            return
        if not self._is_fullscreen:
            self._enter_fullscreen()
        else:
            self._exit_fullscreen()

    # -------------------------------------------------------------------
    # Fullscreen — uses the native QVideoWidget.setFullScreen() API with
    # the widget re-parented to top-level (parent=None). This is the
    # pattern documented as reliable on Qt forums; see:
    # https://forum.qt.io/topic/159760/qvideowidget-setfullscreen-true-is-not-working-properly
    # -------------------------------------------------------------------

    def _enter_fullscreen(self) -> None:
        if self._is_audio_only or self.player.source().isEmpty():
            return
        if self._is_fullscreen:
            return

        # 1. Remove video_widget from its layout and make it top-level
        if self._video_parent_layout is not None:
            self._video_parent_layout.removeWidget(self.video_widget)
        self.video_widget.setParent(None)

        # 2. Use Qt's native setFullScreen API on the video widget itself
        self.video_widget.setFullScreen(True)
        self.video_widget.show()
        self.video_widget.setFocus()

        # 3. Register shortcuts on the video widget (now top-level)
        self._fs_shortcuts: list[QShortcut] = []
        for key, fn in [
            ("F", self.toggle_fullscreen),
            ("Escape", self._exit_fullscreen),
            ("Space", self._toggle_play),
            ("K", self._toggle_play),
            ("Left", lambda: self.seek_relative(-5000)),
            ("Right", lambda: self.seek_relative(5000)),
            ("Shift+Left", lambda: self.seek_relative(-10000)),
            ("Shift+Right", lambda: self.seek_relative(10000)),
            ("J", lambda: self.seek_relative(-10000)),
            ("L", lambda: self.seek_relative(10000)),
            ("M", self._toggle_mute),
            ("Up", lambda: self._nudge_volume(5)),
            ("Down", lambda: self._nudge_volume(-5)),
            ("B", self.add_bookmark_at_current),
            (",", self._speed_down),
            (".", self._speed_up),
        ]:
            s = QShortcut(QKeySequence(key), self.video_widget)
            s.activated.connect(fn)
            self._fs_shortcuts.append(s)

        # 4. Create a FRESH top-level wrapper window for the controls bar.
        # Per Qt forum research, toggling Qt.Widget <-> Qt.Tool flags on the
        # same widget corrupts visibility after the first cycle. Instead, we
        # create a brand-new wrapper each time and move controls_bar INTO it
        # (controls_bar itself never has its flags changed).
        self._fs_controls_wrapper = QWidget()
        self._fs_controls_wrapper.setWindowFlags(
            Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint
        )
        self._fs_controls_wrapper.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self._fs_controls_wrapper.setStyleSheet(
            "QWidget { background-color: rgba(10, 10, 20, 235); border-radius: 10px; }"
        )
        self._fs_controls_wrapper.setMouseTracking(True)
        wrapper_layout = QVBoxLayout(self._fs_controls_wrapper)
        wrapper_layout.setContentsMargins(4, 4, 4, 4)
        wrapper_layout.setSpacing(0)

        # Move controls_bar into the wrapper (reparent the widget, not its flags)
        self.layout().removeWidget(self.controls_bar)
        wrapper_layout.addWidget(self.controls_bar)
        self.controls_bar.show()

        self._fs_controls_wrapper.enterEvent = lambda e: self._hide_timer.stop()
        self._fs_controls_wrapper.leaveEvent = lambda e: self._restart_hide_timer()
        self._fs_controls_wrapper.show()

        # 5. Mouse tracking: global filter + cursor polling
        QApplication.instance().installEventFilter(self)
        self._last_cursor_pos = QCursor.pos()
        self._cursor_poll_timer.start()

        self._is_fullscreen = True
        QTimer.singleShot(0, self._reposition_fs_controls)
        QTimer.singleShot(0, self._restart_hide_timer)

    def _exit_fullscreen(self) -> None:
        if not self._is_fullscreen:
            return

        self._hide_timer.stop()
        self._cursor_poll_timer.stop()
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)

        # 1. Move controls_bar back to main layout, destroy the FS wrapper
        if self._fs_controls_wrapper is not None:
            self._fs_controls_wrapper.layout().removeWidget(self.controls_bar)
            self._fs_controls_wrapper.hide()
            self._fs_controls_wrapper.deleteLater()
            self._fs_controls_wrapper = None
        self.controls_bar.setFixedWidth(16777215)
        self.controls_bar.setCursor(Qt.ArrowCursor)
        self.layout().insertWidget(1, self.controls_bar)
        self.controls_bar.show()

        # 2. Exit native fullscreen on the video widget
        self.video_widget.setFullScreen(False)

        # 3. Drop fullscreen shortcuts (will be recreated on next entry)
        for s in getattr(self, "_fs_shortcuts", []):
            s.setParent(None)
            s.deleteLater()
        self._fs_shortcuts = []

        # 4. Re-insert video_widget back into its original layout
        if self._video_parent_layout is not None:
            self._video_parent_layout.insertWidget(0, self.video_widget, 1)
        self.video_widget.setVisible(not self._is_audio_only)
        self.video_widget.show()

        self._is_fullscreen = False

    @Slot()
    def _exit_fullscreen_if_active(self) -> None:
        if self._is_fullscreen:
            self._exit_fullscreen()

    def _reposition_fs_controls(self) -> None:
        """Anchor FS controls wrapper to the bottom of the fullscreen video (global coords)."""
        if not self._is_fullscreen or self._fs_controls_wrapper is None:
            return
        geom = self.video_widget.geometry()
        margin = 24
        target_width = min(1200, geom.width() - margin * 2)
        self._fs_controls_wrapper.setFixedWidth(target_width)
        self._fs_controls_wrapper.adjustSize()
        x = geom.x() + (geom.width() - target_width) // 2
        y = geom.y() + geom.height() - self._fs_controls_wrapper.height() - margin
        self._fs_controls_wrapper.move(x, y)
        self._fs_controls_wrapper.raise_()

    def _restart_hide_timer(self) -> None:
        self._hide_timer.start(3000)
        if self._is_fullscreen and self._fs_controls_wrapper is not None:
            self._fs_controls_wrapper.show()
            self._fs_controls_wrapper.raise_()
            self.video_widget.setCursor(Qt.ArrowCursor)

    @Slot()
    def _hide_fs_controls(self) -> None:
        if not self._is_fullscreen or self._fs_controls_wrapper is None:
            return
        self._fs_controls_wrapper.hide()
        self.video_widget.setCursor(Qt.BlankCursor)

    def eventFilter(self, obj, event):
        if self._is_fullscreen:
            et = event.type()
            if et in (QEvent.MouseMove, QEvent.HoverMove, QEvent.MouseButtonPress):
                self._restart_hide_timer()
        return super().eventFilter(obj, event)

    @Slot()
    def _poll_cursor(self):
        """Detect cursor movement even when events are swallowed by QVideoWidget."""
        if not self._is_fullscreen:
            return
        pos = QCursor.pos()
        if self._last_cursor_pos is None or pos != self._last_cursor_pos:
            self._last_cursor_pos = pos
            self._restart_hide_timer()

    def stop(self) -> None:
        """Stop playback and reset."""
        if self._is_fullscreen:
            self._exit_fullscreen()
        self._save_position_now()
        self._flush_notes()
        self._save_timer.stop()
        self.player.stop()
        self.player.setSource(QUrl())
        self._current_media_path = ""
        self._bookmarks = []
        self._pending_start_ms = 0
        self._refresh_bookmarks_list()
        self.play_btn.setIcon(icons.play())
        self.pos_slider.setRange(0, 0)
        self.time_label.setText("00:00 / 00:00")
        self.bookmarks_panel.setVisible(False)
        self._show_placeholder()

    def seek_relative(self, delta_ms: int) -> None:
        if self.player.source().isEmpty():
            return
        new_pos = max(0, self.player.position() + delta_ms)
        dur = self.player.duration()
        if dur > 0:
            new_pos = min(new_pos, dur)
        self.player.setPosition(new_pos)

    @Slot()
    def _show_bookmarks_menu(self) -> None:
        """Popup menu with existing bookmarks + 'add new'. Works in fullscreen too."""
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background-color: #1c1c2e; color: #f0f0f5; border: 1px solid #2f3056; "
            "border-radius: 8px; padding: 4px; }"
            "QMenu::item { padding: 7px 22px; border-radius: 4px; }"
            "QMenu::item:selected { background-color: #e94560; }"
            "QMenu::separator { height: 1px; background: #2f3056; margin: 4px 8px; }"
        )

        add_action = menu.addAction("+ Adicionar marcador no tempo atual")

        seek_actions: dict = {}
        if self._bookmarks:
            menu.addSeparator()
            # Group by category — show category submenus when categories exist
            groups: dict[str, list[dict]] = {}
            for bk in self._bookmarks:
                cat = (bk.get("category") or "").strip()
                groups.setdefault(cat, []).append(bk)

            ordered_cats = sorted(k for k in groups if k)
            if "" in groups:
                ordered_cats.append("")

            for cat in ordered_cats:
                if cat:
                    submenu = menu.addMenu(f"\u2605 {cat}")
                    submenu.setStyleSheet(menu.styleSheet())
                    target = submenu
                else:
                    menu.addSeparator()
                    target = menu
                for bk in groups[cat]:
                    label = f"{_fmt_time(bk['time_ms'])}  \u00B7  {bk['name']}"
                    act = target.addAction(label)
                    seek_actions[act] = bk["time_ms"]
        else:
            info = menu.addAction("(nenhum marcador ainda)")
            info.setEnabled(False)

        # Open menu ABOVE the button — in fullscreen the controls are at the
        # bottom edge of the screen, so a downward-opening menu is cut off.
        btn = self.bm_btn
        menu_size = menu.sizeHint()
        btn_top_left = btn.mapToGlobal(btn.rect().topLeft())
        pos_above = btn_top_left.__class__(
            btn_top_left.x(),
            btn_top_left.y() - menu_size.height() - 4,
        )
        chosen = menu.exec(pos_above)
        if chosen is None:
            return
        if chosen == add_action:
            self.add_bookmark_at_current()
        elif chosen in seek_actions:
            t = seek_actions[chosen]
            self.player.setPosition(int(t))
            if self.player.playbackState() != QMediaPlayer.PlayingState:
                self.player.play()

    @Slot()
    def add_bookmark_at_current(self) -> None:
        if not self._current_media_path:
            return
        current_ms = self.player.position()
        suggested = f"Marcador {len(self._bookmarks) + 1}"

        dlg = BookmarkDialog(
            existing_categories=self._known_bookmark_categories(),
            title="Novo marcador",
            initial_name=suggested,
            initial_category="",
            time_label=_fmt_time(current_ms),
            parent=self,
        )
        if dlg.exec() != QDialog.Accepted:
            return
        name, category = dlg.values()
        if not name:
            return

        self._bookmarks.append({
            "name": name,
            "time_ms": int(current_ms),
            "category": category,
        })
        self._bookmarks.sort(key=lambda b: b["time_ms"])
        self._refresh_bookmarks_list()
        self._emit_bookmarks_changed()

    def _known_bookmark_categories(self) -> list[str]:
        """Union of categories from this video's bookmarks + all other videos."""
        local = {(b.get("category") or "").strip() for b in self._bookmarks}
        local.discard("")
        # Add categories from other videos in the same output dir
        if self._current_media_path:
            output_dir = os.path.dirname(self._current_media_path)
            try:
                for c in VideoStore.list_bookmark_categories(output_dir):
                    if c:
                        local.add(c)
            except Exception:
                pass
        return sorted(local)

    # --- Internal UI helpers ---

    def _show_placeholder(self):
        self.video_widget.setVisible(False)
        self.audio_label.setVisible(False)
        self.placeholder.setVisible(True)

    def _refresh_bookmarks_list(self) -> None:
        """Populate the list grouped by category.

        Header items are clickable (but not selectable) to collapse/expand
        their bookmark group. Collapse state is preserved in self._bookmark_cat_collapsed.
        """
        from PySide6.QtGui import QColor, QFont

        self.bookmarks_list.clear()

        # Group by category
        groups: dict[str, list[tuple[int, dict]]] = {}
        for i, b in enumerate(self._bookmarks):
            cat = (b.get("category") or "").strip()
            groups.setdefault(cat, []).append((i, b))

        # Render: named categories alphabetical, then uncategorized last
        ordered_cats = sorted(k for k in groups if k)
        if "" in groups:
            ordered_cats.append("")

        for cat in ordered_cats:
            collapsed = self._bookmark_cat_collapsed.get(cat, False)
            display = cat if cat else "Sem categoria"
            arrow = "\u25B6" if collapsed else "\u25BC"

            header = QListWidgetItem(f"  {arrow} {display}  ({len(groups[cat])})")
            # Non-selectable but clickable (ItemIsEnabled without ItemIsSelectable)
            header.setFlags(Qt.ItemIsEnabled)
            header.setData(Qt.UserRole + 2, cat)  # marker that this is a header
            color_hex = "#e94560" if cat else "#64647d"
            header.setForeground(QColor(color_hex))
            f = QFont()
            f.setBold(True)
            f.setPointSize(9)
            header.setFont(f)
            self.bookmarks_list.addItem(header)

            for idx, b in groups[cat]:
                item = QListWidgetItem(
                    f"    {_fmt_time(b['time_ms'])}  \u00B7  {b['name']}"
                )
                item.setData(Qt.UserRole, b["time_ms"])
                item.setData(Qt.UserRole + 1, idx)  # store index into _bookmarks
                self.bookmarks_list.addItem(item)
                # setHidden only works after the item is attached to the list
                if collapsed:
                    item.setHidden(True)

    def _emit_bookmarks_changed(self) -> None:
        if self._current_media_path:
            self.bookmarks_changed.emit(self._current_media_path, list(self._bookmarks))

    @Slot(QListWidgetItem)
    def _on_bookmark_item_clicked(self, item: QListWidgetItem) -> None:
        """Single click toggles collapse on category headers, nothing on bookmarks."""
        cat = item.data(Qt.UserRole + 2)
        if cat is None:
            return  # regular bookmark — handled by doubleClick
        # Toggle collapse state for this category
        current = self._bookmark_cat_collapsed.get(cat, False)
        self._bookmark_cat_collapsed[cat] = not current
        self._refresh_bookmarks_list()

    @Slot(QListWidgetItem)
    def _on_bookmark_activated(self, item: QListWidgetItem) -> None:
        # Ignore headers
        if item.data(Qt.UserRole + 2) is not None:
            return
        t = item.data(Qt.UserRole)
        if t is not None:
            self.player.setPosition(int(t))
            if self.player.playbackState() != QMediaPlayer.PlayingState:
                self.player.play()

    def _selected_bookmark_indices(self) -> list[int]:
        """Return indices (into self._bookmarks) of all currently selected items."""
        indices: list[int] = []
        for item in self.bookmarks_list.selectedItems():
            idx = item.data(Qt.UserRole + 1)
            if idx is not None:
                indices.append(idx)
        return sorted(set(indices))

    @Slot(object)
    def _on_bookmark_context_menu(self, pos) -> None:
        item = self.bookmarks_list.itemAt(pos)
        if item is None:
            return

        # If the clicked item isn't selected, use just it; otherwise use the full selection
        clicked_idx = item.data(Qt.UserRole + 1)
        if clicked_idx is None:  # Header item — no actions
            return

        selected = self._selected_bookmark_indices()
        if clicked_idx not in selected:
            selected = [clicked_idx]
        multi = len(selected) > 1

        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background-color: #1c1c2e; color: #f0f0f5; border: 1px solid #2f3056; border-radius: 8px; padding: 4px; }"
            "QMenu::item { padding: 7px 22px; border-radius: 4px; }"
            "QMenu::item:selected { background-color: #e94560; }"
            "QMenu::separator { height: 1px; background: #2f3056; margin: 4px 8px; }"
        )

        act_go = None
        act_rename = None
        if not multi:
            act_go = menu.addAction("Ir para este marcador")
            act_rename = menu.addAction("Renomear / categoria")

        # "Move to category" submenu — works for single AND multi selection
        cats = self._known_bookmark_categories()
        move_menu = menu.addMenu(
            f"Mover para categoria  ({len(selected)} item{'s' if multi else ''})"
            if multi else "Mover para categoria"
        )
        move_menu.setStyleSheet(menu.styleSheet())
        move_actions: dict = {}
        for cat in cats:
            a = move_menu.addAction(cat)
            move_actions[a] = cat
        if cats:
            move_menu.addSeparator()
        act_new_cat = move_menu.addAction("+ Nova categoria...")
        act_remove_cat = move_menu.addAction("Remover categoria (sem categoria)")

        menu.addSeparator()
        act_delete = menu.addAction(
            f"Excluir {len(selected)} marcadores" if multi else "Excluir"
        )

        action = menu.exec(self.bookmarks_list.mapToGlobal(pos))
        if action is None:
            return

        if action == act_go and not multi:
            self._on_bookmark_activated(item)
            return
        if action == act_rename and not multi:
            bk = self._bookmarks[selected[0]]
            dlg = BookmarkDialog(
                existing_categories=cats,
                title="Editar marcador",
                initial_name=bk.get("name", ""),
                initial_category=bk.get("category", ""),
                time_label=_fmt_time(bk["time_ms"]),
                parent=self,
            )
            if dlg.exec() == QDialog.Accepted:
                name, category = dlg.values()
                if name:
                    bk["name"] = name
                    bk["category"] = category
                    self._refresh_bookmarks_list()
                    self._emit_bookmarks_changed()
            return

        if action in move_actions:
            self._apply_category_to(selected, move_actions[action])
        elif action == act_new_cat:
            new_cat, ok = QInputDialog.getText(
                self, "Nova categoria", "Nome da categoria:",
            )
            if ok and new_cat.strip():
                self._apply_category_to(selected, new_cat.strip())
        elif action == act_remove_cat:
            self._apply_category_to(selected, "")
        elif action == act_delete:
            # Delete in reverse order so indices stay valid
            for idx in sorted(selected, reverse=True):
                del self._bookmarks[idx]
            self._refresh_bookmarks_list()
            self._emit_bookmarks_changed()

    def _apply_category_to(self, indices: list[int], category: str) -> None:
        """Set a category on the given bookmark indices and persist."""
        for idx in indices:
            if 0 <= idx < len(self._bookmarks):
                self._bookmarks[idx]["category"] = category
        self._refresh_bookmarks_list()
        self._emit_bookmarks_changed()

    # --- Player slots ---

    @Slot()
    def _toggle_play(self):
        if self.player.source().isEmpty():
            return
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    @Slot()
    def _toggle_mute(self):
        self.audio_output.setMuted(not self.audio_output.isMuted())

    def _speed_up(self):
        idx = min(self.speed_combo.currentIndex() + 1, self.speed_combo.count() - 1)
        self.speed_combo.setCurrentIndex(idx)

    def _speed_down(self):
        idx = max(self.speed_combo.currentIndex() - 1, 0)
        self.speed_combo.setCurrentIndex(idx)

    def _nudge_volume(self, delta: int):
        self.vol_slider.setValue(max(0, min(100, self.vol_slider.value() + delta)))

    @Slot(int)
    def _on_position_changed(self, position: int):
        if not self._seeking:
            self.pos_slider.setValue(position)
        dur = self.player.duration()
        self.time_label.setText(f"{_fmt_time(position)} / {_fmt_time(dur)}")

    @Slot(int)
    def _on_duration_changed(self, duration: int):
        self.pos_slider.setRange(0, duration)

    @Slot()
    def _on_seek_start(self):
        self._seeking = True

    @Slot()
    def _on_seek_end(self):
        self._seeking = False
        self.player.setPosition(self.pos_slider.value())

    @Slot(int)
    def _on_volume_changed(self, value: int):
        self.audio_output.setVolume(value / 100.0)
        if self.audio_output.isMuted() and value > 0:
            self.audio_output.setMuted(False)

    @Slot(int)
    def _on_speed_changed(self, idx: int):
        rate = self.speed_combo.itemData(idx)
        self.player.setPlaybackRate(float(rate))

    @Slot()
    def _on_state_changed(self):
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.play_btn.setIcon(icons.pause())
            self._save_timer.start()
        else:
            self.play_btn.setIcon(icons.play())
            self._save_timer.stop()
            # Paused or stopped: snapshot position
            self._save_position_now()

    @Slot()
    def _on_media_status_changed(self, status):
        # Apply the pending resume position as soon as the media is loaded.
        # Qt6 may emit LoadedMedia, BufferedMedia or BufferingMedia depending on
        # source type — handle all "ready-ish" statuses.
        ready = status in (
            QMediaPlayer.LoadedMedia,
            QMediaPlayer.BufferedMedia,
            QMediaPlayer.BufferingMedia,
        )
        if ready:
            if self._pending_start_ms > 0:
                self.player.setPosition(self._pending_start_ms)
                self._pending_start_ms = 0
