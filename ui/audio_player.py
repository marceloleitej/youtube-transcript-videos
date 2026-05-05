"""Dedicated audio / music player — queue, auto-advance, prev/next, shuffle/repeat."""

import os
import random

from PySide6.QtCore import Qt, QSize, QTimer, Signal, Slot
from PySide6.QtGui import QKeySequence, QPixmap, QShortcut

from core.audio_engine import AudioEngine, MediaStatus, State
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from core.store import VideoStore
from core.thumbnails import thumb_path
from ui import icons


SPEEDS = [0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0]


def _fmt_time(ms: int) -> str:
    if ms < 0:
        ms = 0
    total_s = ms // 1000
    h, rem = divmod(total_s, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


class AudioPlayer(QWidget):
    """Music-style player with queue, auto-advance, shuffle, and repeat modes."""

    position_saved = Signal(str, int)   # media_path, position_ms
    track_changed = Signal(str)         # media_path — fired on auto-advance or jump

    def __init__(self, parent=None):
        super().__init__(parent)
        self._queue: list[str] = []          # ordered media paths
        self._queue_meta: dict[str, object] = {}  # path -> VideoData (cached)
        self._shuffled_order: list[int] = []  # permutation of queue indices (or [])
        self._current_index: int = -1
        self._current_media_path: str = ""
        self._repeat_mode: str = "off"       # "off" | "all" | "one"
        self._shuffle_on: bool = False
        self._seeking = False
        self._pending_start_ms = 0
        self._last_saved_position = 0
        self._last_time_label_sec = -1  # throttle time-label updates to ~1 Hz

        # Persist positions on a long interval; the audio thread is tight and
        # syncing JSON to disk every few seconds is one of the causes of stutter.
        self._save_timer = QTimer(self)
        self._save_timer.setInterval(15000)
        self._save_timer.timeout.connect(self._save_position_now)

        self._build_ui()
        self._setup_player()
        self._setup_shortcuts()
        self._update_ui_for_empty_queue()

    # ---------- UI build ----------

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        # --- Left column ---
        left = QVBoxLayout()
        left.setContentsMargins(12, 12, 12, 12)
        left.setSpacing(10)

        # Header: thumb + title/uploader
        header = QFrame()
        header.setObjectName("audioHeader")
        header.setStyleSheet(
            "#audioHeader { background-color: #1c1c2e; border-radius: 10px; padding: 14px; }"
        )
        h = QHBoxLayout(header)
        h.setContentsMargins(14, 14, 14, 14)
        h.setSpacing(14)

        self.thumb_label = QLabel()
        self.thumb_label.setFixedSize(140, 140)
        self.thumb_label.setAlignment(Qt.AlignCenter)
        self.thumb_label.setStyleSheet(
            "background-color: #0a1128; border-radius: 8px;"
        )
        self.thumb_label.setPixmap(icons.music_note("#3a3b66").pixmap(56, 56))
        h.addWidget(self.thumb_label)

        info_col = QVBoxLayout()
        info_col.setSpacing(4)
        info_col.addStretch()

        self.track_title = QLabel("Selecione um audio no historico")
        self.track_title.setStyleSheet(
            "font-size: 20px; font-weight: 700; color: #f0f0f5;"
        )
        self.track_title.setWordWrap(True)
        info_col.addWidget(self.track_title)

        self.track_uploader = QLabel("")
        self.track_uploader.setStyleSheet("font-size: 13px; color: #9a9ab0;")
        info_col.addWidget(self.track_uploader)

        self.track_position_label = QLabel("")
        self.track_position_label.setStyleSheet("font-size: 11px; color: #64647d;")
        info_col.addWidget(self.track_position_label)

        info_col.addStretch()
        h.addLayout(info_col, 1)
        left.addWidget(header)

        # Seek row
        seek_row = QHBoxLayout()
        seek_row.setSpacing(8)
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
        seek_row.addWidget(self.pos_slider, 1)
        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setStyleSheet("font-size: 12px; color: #ccc; min-width: 100px;")
        seek_row.addWidget(self.time_label)
        left.addLayout(seek_row)

        # Controls
        ctrl_btn_style = (
            "QPushButton { background-color: #242438; color: #f0f0f5; "
            "font-size: 14px; font-weight: 600; border-radius: 6px; padding: 8px 14px; }"
            "QPushButton:hover { background-color: #2d2d46; }"
            "QPushButton:disabled { color: #555; background-color: #1c1c2e; }"
            "QPushButton:checked { background-color: #e94560; color: white; }"
        )

        controls = QHBoxLayout()
        controls.setSpacing(8)
        controls.setContentsMargins(0, 0, 0, 0)

        icon_size_lg = QSize(22, 22)
        icon_size_md = QSize(18, 18)

        self.prev_btn = QPushButton()
        self.prev_btn.setIcon(icons.prev_track())
        self.prev_btn.setIconSize(icon_size_lg)
        self.prev_btn.setFixedSize(48, 44)
        self.prev_btn.setStyleSheet(ctrl_btn_style)
        self.prev_btn.setToolTip("Anterior (Ctrl+Left)")
        self.prev_btn.clicked.connect(self.play_previous)
        controls.addWidget(self.prev_btn)

        self.play_btn = QPushButton()
        self.play_btn.setIcon(icons.play())
        self.play_btn.setIconSize(QSize(26, 26))
        self.play_btn.setFixedSize(60, 44)
        self.play_btn.setStyleSheet(
            "QPushButton { background-color: #e94560; color: white; "
            "border-radius: 22px; padding: 6px; }"
            "QPushButton:hover { background-color: #ff5b7a; }"
            "QPushButton:disabled { background-color: #2a2a4a; color: #666; }"
        )
        self.play_btn.clicked.connect(self._toggle_play)
        controls.addWidget(self.play_btn)

        self.next_btn = QPushButton()
        self.next_btn.setIcon(icons.next_track())
        self.next_btn.setIconSize(icon_size_lg)
        self.next_btn.setFixedSize(48, 44)
        self.next_btn.setStyleSheet(ctrl_btn_style)
        self.next_btn.setToolTip("Proximo (Ctrl+Right)")
        self.next_btn.clicked.connect(self.play_next)
        controls.addWidget(self.next_btn)

        controls.addSpacing(12)

        self.shuffle_btn = QPushButton()
        self.shuffle_btn.setIcon(icons.shuffle())
        self.shuffle_btn.setIconSize(icon_size_md)
        self.shuffle_btn.setFixedSize(42, 36)
        self.shuffle_btn.setCheckable(True)
        self.shuffle_btn.setStyleSheet(ctrl_btn_style)
        self.shuffle_btn.setToolTip("Aleatorio")
        self.shuffle_btn.toggled.connect(self._on_shuffle_toggled)
        controls.addWidget(self.shuffle_btn)

        self.repeat_btn = QPushButton()
        self.repeat_btn.setIcon(icons.repeat())
        self.repeat_btn.setIconSize(icon_size_md)
        self.repeat_btn.setFixedSize(42, 36)
        self.repeat_btn.setStyleSheet(ctrl_btn_style)
        self.repeat_btn.setToolTip("Repetir: desligado")
        self.repeat_btn.clicked.connect(self._cycle_repeat)
        controls.addWidget(self.repeat_btn)

        controls.addSpacing(12)

        self.speed_combo = QComboBox()
        for s in SPEEDS:
            self.speed_combo.addItem(f"{s}x", s)
        self.speed_combo.setCurrentIndex(SPEEDS.index(1.0))
        self.speed_combo.setFixedWidth(76)
        self.speed_combo.setStyleSheet(
            "QComboBox { background-color: #242438; color: #f0f0f5; "
            "border-radius: 4px; padding: 4px 8px; font-size: 12px; }"
        )
        self.speed_combo.currentIndexChanged.connect(self._on_speed_changed)
        controls.addWidget(self.speed_combo)

        controls.addStretch()

        vol_icon = QLabel()
        vol_icon.setPixmap(icons.volume().pixmap(16, 16))
        vol_icon.setStyleSheet("padding: 0 2px;")
        controls.addWidget(vol_icon)

        self.vol_slider = QSlider(Qt.Horizontal)
        self.vol_slider.setRange(0, 100)
        self.vol_slider.setValue(80)
        self.vol_slider.setFixedWidth(110)
        self.vol_slider.valueChanged.connect(self._on_volume_changed)
        self.vol_slider.setStyleSheet(
            "QSlider::groove:horizontal { height: 4px; background: #242438; border-radius: 2px; }"
            "QSlider::handle:horizontal { background: #f0f0f5; width: 12px; height: 12px; "
            "margin: -4px 0; border-radius: 6px; }"
            "QSlider::sub-page:horizontal { background: #4caf50; border-radius: 2px; }"
        )
        controls.addWidget(self.vol_slider)

        left.addLayout(controls)
        left.addStretch()

        root.addLayout(left, 1)

        # --- Right: queue panel ---
        queue_panel = QFrame()
        queue_panel.setObjectName("queuePanel")
        queue_panel.setMinimumWidth(240)
        queue_panel.setMaximumWidth(360)
        queue_panel.setStyleSheet(
            "#queuePanel { background-color: #1c1c2e; border-radius: 8px; }"
        )
        q_v = QVBoxLayout(queue_panel)
        q_v.setContentsMargins(10, 10, 10, 10)
        q_v.setSpacing(6)

        q_header = QLabel("Fila de reproducao")
        q_header.setStyleSheet(
            "font-size: 14px; font-weight: 700; color: #e94560; "
            "padding-bottom: 4px;"
        )
        q_v.addWidget(q_header)

        self.queue_list = QListWidget()
        self.queue_list.setStyleSheet(
            "QListWidget { background-color: #0a1128; border: none; border-radius: 4px; "
            "color: #f0f0f5; font-size: 12px; }"
            "QListWidget::item { padding: 6px 8px; border-radius: 4px; }"
            "QListWidget::item:hover { background-color: #242438; }"
            "QListWidget::item:selected { background-color: #e94560; color: white; }"
        )
        self.queue_list.itemDoubleClicked.connect(self._on_queue_double_clicked)
        q_v.addWidget(self.queue_list, 1)

        self.queue_count_label = QLabel("")
        self.queue_count_label.setStyleSheet("color: #64647d; font-size: 11px;")
        q_v.addWidget(self.queue_count_label)

        root.addWidget(queue_panel)

    def _setup_player(self) -> None:
        # Custom engine: ffmpeg subprocess + sounddevice / PortAudio. Keeps
        # audio playback off the Python GIL path entirely, with a ~1s ring
        # buffer that absorbs UI/main-thread stalls without glitching.
        self.player = AudioEngine(self)
        self.audio_output = self.player  # volume/mute now live on the engine
        self.player.setVolume(0.8)
        self.player.positionChanged.connect(self._on_position_changed)
        self.player.durationChanged.connect(self._on_duration_changed)
        self.player.playbackStateChanged.connect(self._on_state_changed)
        self.player.mediaStatusChanged.connect(self._on_media_status_changed)

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
        sc("Ctrl+Left", self.play_previous)
        sc("Ctrl+Right", self.play_next)
        sc("M", self._toggle_mute)

    # ---------- Public API ----------

    def load_queue(
        self,
        media_paths: list[str],
        start_index: int = 0,
        start_position_ms: int = 0,
    ) -> None:
        """Load a fresh queue and start playing at start_index."""
        self._save_position_now()
        self._queue = list(media_paths)
        self._populate_queue_meta()
        self._current_index = -1
        self._current_media_path = ""
        self._rebuild_shuffle_order(preserve_current=False)

        if not self._queue:
            self._update_ui_for_empty_queue()
            self.player.stop()
            return

        idx = max(0, min(start_index, len(self._queue) - 1))
        self._pending_start_ms = max(0, int(start_position_ms or 0))
        self._load_at(idx)

    def refresh_queue(self, media_paths: list[str]) -> None:
        """Update the queue without disrupting the currently-playing track if possible."""
        new_paths = list(media_paths)
        if not new_paths:
            self.stop()
            self._queue = []
            self._queue_meta.clear()
            self._update_ui_for_empty_queue()
            return

        if self._current_media_path and self._current_media_path in new_paths:
            self._queue = new_paths
            self._populate_queue_meta()
            self._current_index = new_paths.index(self._current_media_path)
            self._rebuild_shuffle_order(preserve_current=True)
            self._rebuild_queue_list()
        else:
            # Current track gone from queue — load first of new queue
            self._queue = new_paths
            self._populate_queue_meta()
            self._rebuild_shuffle_order(preserve_current=False)
            self._load_at(0)

    def _populate_queue_meta(self) -> None:
        """Read all queue JSON sidecars once and cache. Avoids N reads per track change."""
        new_meta: dict[str, object] = {}
        for p in self._queue:
            cached = self._queue_meta.get(p)
            new_meta[p] = cached if cached is not None else VideoStore.load(p)
        self._queue_meta = new_meta

    def stop(self) -> None:
        self._save_position_now()
        self._save_timer.stop()
        self.player.stop()
        self.player.setSource("")
        self._current_media_path = ""
        self._current_index = -1
        self._queue = []
        self._shuffled_order = []
        self.queue_list.clear()
        self._update_ui_for_empty_queue()

    def shutdown(self) -> None:
        try:
            self._save_timer.stop()
            self._save_position_now()
            self.player.shutdown()
        except Exception:
            pass

    # ---------- Internal ----------

    def _load_at(self, index: int) -> None:
        if not (0 <= index < len(self._queue)):
            return
        self._save_position_now()

        path = self._queue[index]
        data = self._queue_meta.get(path)
        if data is None:
            data = VideoStore.load(path)
            self._queue_meta[path] = data
        prev_index = self._current_index
        self._current_index = index
        self._current_media_path = path
        self._last_saved_position = 0

        # Populate header
        self.track_title.setText(data.title if data and data.title else os.path.basename(path))
        uploader = (data.uploader if data else "") or ""
        self.track_uploader.setText(uploader)
        self.track_position_label.setText(
            f"Faixa {index + 1} de {len(self._queue)}"
        )

        # Thumbnail
        output_dir = os.path.dirname(path)
        vid = (data.video_id if data else "") or ""
        tp = thumb_path(output_dir, vid) if vid else ""
        pix: QPixmap | None = None
        if tp and os.path.isfile(tp):
            pix = QPixmap(tp)
        if pix and not pix.isNull():
            pix = pix.scaled(
                140, 140, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
            )
            self.thumb_label.setPixmap(pix)
        else:
            self.thumb_label.setPixmap(icons.music_note("#3a3b66").pixmap(56, 56))

        # Resume position (either explicit pending or from data)
        if self._pending_start_ms <= 0 and data and data.last_position_ms > 0:
            self._pending_start_ms = int(data.last_position_ms)

        self.player.setSource(path)
        self.player.setPlaybackRate(self.speed_combo.currentData())
        self.pos_slider.setValue(0)
        self.time_label.setText("00:00 / 00:00")
        self._last_time_label_sec = -1

        self._enable_controls(True)
        # Smart update: only repaint the two affected rows. Full rebuild walks
        # the whole queue (N items, N style passes) on every skip which caused
        # a visible playback glitch on large queues.
        if self.queue_list.count() == len(self._queue):
            self._update_queue_row(prev_index)
            self._update_queue_row(index)
            if 0 <= index < self.queue_list.count():
                self.queue_list.setCurrentRow(index)
        else:
            self._rebuild_queue_list()
        self.track_changed.emit(path)

    def _rebuild_shuffle_order(self, preserve_current: bool) -> None:
        if not self._shuffle_on or not self._queue:
            self._shuffled_order = []
            return
        order = list(range(len(self._queue)))
        random.shuffle(order)
        if preserve_current and 0 <= self._current_index < len(self._queue):
            order.remove(self._current_index)
            order.insert(0, self._current_index)
        self._shuffled_order = order

    def _next_queue_index(self) -> int | None:
        if not self._queue:
            return None
        if self._repeat_mode == "one":
            return self._current_index
        if self._shuffle_on and self._shuffled_order:
            try:
                pos = self._shuffled_order.index(self._current_index)
            except ValueError:
                pos = -1
            pos += 1
            if pos >= len(self._shuffled_order):
                if self._repeat_mode == "all":
                    return self._shuffled_order[0]
                return None
            return self._shuffled_order[pos]
        # Sequential
        nxt = self._current_index + 1
        if nxt >= len(self._queue):
            if self._repeat_mode == "all":
                return 0
            return None
        return nxt

    def _prev_queue_index(self) -> int | None:
        if not self._queue:
            return None
        if self._shuffle_on and self._shuffled_order:
            try:
                pos = self._shuffled_order.index(self._current_index)
            except ValueError:
                pos = 0
            pos -= 1
            if pos < 0:
                if self._repeat_mode == "all":
                    return self._shuffled_order[-1]
                return None
            return self._shuffled_order[pos]
        prev = self._current_index - 1
        if prev < 0:
            if self._repeat_mode == "all":
                return len(self._queue) - 1
            return None
        return prev

    @Slot()
    def play_next(self) -> None:
        nxt = self._next_queue_index()
        if nxt is None:
            return
        self._load_at(nxt)
        self.player.play()

    @Slot()
    def play_previous(self) -> None:
        # If more than 3s into track, restart it; else go to prev
        if self.player.position() > 3000:
            self.player.setPosition(0)
            return
        prev = self._prev_queue_index()
        if prev is None:
            self.player.setPosition(0)
            return
        self._load_at(prev)
        self.player.play()

    def _format_queue_row(self, i: int) -> str:
        path = self._queue[i]
        data = self._queue_meta.get(path)
        title = data.title if data and data.title else os.path.basename(path)
        dur = int(data.duration_seconds) if data and data.duration_seconds else 0
        dur_str = f"  \u00B7  {_fmt_time(dur * 1000)}" if dur > 0 else ""
        prefix = "\u25B6  " if i == self._current_index else f"{i + 1:>2}. "
        return f"{prefix}{title}{dur_str}"

    def _update_queue_row(self, i: int) -> None:
        if not (0 <= i < self.queue_list.count()):
            return
        item = self.queue_list.item(i)
        if item is not None:
            item.setText(self._format_queue_row(i))

    def _rebuild_queue_list(self) -> None:
        self.queue_list.blockSignals(True)
        self.queue_list.clear()
        for i, path in enumerate(self._queue):
            item = QListWidgetItem(self._format_queue_row(i))
            item.setData(Qt.UserRole, path)
            self.queue_list.addItem(item)
        if 0 <= self._current_index < self.queue_list.count():
            self.queue_list.setCurrentRow(self._current_index)
        self.queue_count_label.setText(f"{len(self._queue)} faixa(s)")
        self.queue_list.blockSignals(False)

    def _update_ui_for_empty_queue(self) -> None:
        self.track_title.setText("Selecione um audio no historico")
        self.track_uploader.setText("")
        self.track_position_label.setText("")
        self.thumb_label.setPixmap(icons.music_note("#3a3b66").pixmap(56, 56))
        self.time_label.setText("00:00 / 00:00")
        self.pos_slider.setRange(0, 0)
        self.queue_count_label.setText("Fila vazia")
        self._enable_controls(False)

    def _enable_controls(self, enabled: bool) -> None:
        self.play_btn.setEnabled(enabled)
        self.prev_btn.setEnabled(enabled)
        self.next_btn.setEnabled(enabled)
        self.pos_slider.setEnabled(enabled)

    # ---------- Slots ----------

    @Slot()
    def _toggle_play(self) -> None:
        if not self.player.source():
            return
        if self.player.playbackState() == State.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    @Slot()
    def _toggle_mute(self) -> None:
        self.audio_output.setMuted(not self.audio_output.isMuted())

    @Slot(int)
    def _on_speed_changed(self, idx: int) -> None:
        rate = self.speed_combo.itemData(idx)
        self.player.setPlaybackRate(float(rate))

    @Slot(int)
    def _on_volume_changed(self, value: int) -> None:
        self.audio_output.setVolume(value / 100.0)
        if self.audio_output.isMuted() and value > 0:
            self.audio_output.setMuted(False)

    @Slot(int)
    def _on_position_changed(self, position: int) -> None:
        if not self._seeking:
            self.pos_slider.setValue(position)
        # Time label only needs second-granularity updates; refreshing the
        # QLabel on every positionChanged (30+ Hz on some backends) fights
        # with the audio thread for UI repaints.
        sec = position // 1000
        if sec != self._last_time_label_sec:
            self._last_time_label_sec = sec
            dur = self.player.duration()
            self.time_label.setText(f"{_fmt_time(position)} / {_fmt_time(dur)}")

    @Slot(int)
    def _on_duration_changed(self, duration: int) -> None:
        self.pos_slider.setRange(0, duration)

    @Slot()
    def _on_seek_start(self) -> None:
        self._seeking = True

    @Slot()
    def _on_seek_end(self) -> None:
        self._seeking = False
        self.player.setPosition(self.pos_slider.value())

    def seek_relative(self, delta_ms: int) -> None:
        if not self.player.source():
            return
        dur = self.player.duration()
        new_pos = max(0, self.player.position() + delta_ms)
        if dur > 0:
            new_pos = min(new_pos, dur)
        self.player.setPosition(new_pos)

    @Slot()
    def _on_state_changed(self) -> None:
        if self.player.playbackState() == State.PlayingState:
            self.play_btn.setIcon(icons.pause())
            self._save_timer.start()
        else:
            self.play_btn.setIcon(icons.play())
            self._save_timer.stop()
            self._save_position_now()

    @Slot(object)
    def _on_media_status_changed(self, status) -> None:
        ready = status in (
            MediaStatus.LoadedMedia,
            MediaStatus.BufferedMedia,
            MediaStatus.BufferingMedia,
        )
        if ready and self._pending_start_ms > 0:
            self.player.setPosition(self._pending_start_ms)
            self._pending_start_ms = 0

        if status == MediaStatus.EndOfMedia:
            self._handle_end_of_media()

    def _handle_end_of_media(self) -> None:
        # Track finished — save position as 0 (watched fully)
        if self._current_media_path:
            self.position_saved.emit(self._current_media_path, 0)
            self._last_saved_position = 0

        if self._repeat_mode == "one":
            self.player.setPosition(0)
            self.player.play()
            return

        nxt = self._next_queue_index()
        if nxt is None:
            self.player.stop()
            return
        self._load_at(nxt)
        self.player.play()

    @Slot()
    def _on_shuffle_toggled(self, on: bool) -> None:
        self._shuffle_on = on
        self._rebuild_shuffle_order(preserve_current=True)

    @Slot()
    def _cycle_repeat(self) -> None:
        self._repeat_mode = {"off": "all", "all": "one", "one": "off"}[self._repeat_mode]
        if self._repeat_mode == "off":
            self.repeat_btn.setIcon(icons.repeat())
            self.repeat_btn.setToolTip("Repetir: desligado")
            self.repeat_btn.setProperty("active", False)
        elif self._repeat_mode == "all":
            # Use the accent color variant to indicate active
            self.repeat_btn.setIcon(icons.repeat("#e94560"))
            self.repeat_btn.setToolTip("Repetir: fila toda")
            self.repeat_btn.setProperty("active", True)
        else:  # one
            self.repeat_btn.setIcon(icons.repeat_one("#e94560"))
            self.repeat_btn.setToolTip("Repetir: uma faixa")
            self.repeat_btn.setProperty("active", True)
        self.repeat_btn.style().unpolish(self.repeat_btn)
        self.repeat_btn.style().polish(self.repeat_btn)

    @Slot(QListWidgetItem)
    def _on_queue_double_clicked(self, item: QListWidgetItem) -> None:
        row = self.queue_list.row(item)
        if 0 <= row < len(self._queue):
            self._load_at(row)
            self.player.play()

    # ---------- Position persistence ----------

    def _save_position_now(self) -> None:
        if not self._current_media_path:
            return
        pos = self.player.position()
        dur = self.player.duration()
        if dur > 0 and pos >= dur - 10000:
            pos = 0
        if pos == self._last_saved_position:
            return
        self._last_saved_position = pos
        self.position_saved.emit(self._current_media_path, int(pos))
