"""Main window — PySide6 dark-themed Super Video Downloader with history sidebar."""

import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone

from PySide6.QtCore import Qt, QRunnable, QThread, QThreadPool, Signal, Slot
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core.downloader import VideoDownloader
from core.platform_detect import detect_platform
from core.store import VideoData, VideoStore
from core.transcriber import NoAudioTrackError, has_audio_stream, transcribe_file
from ui.audio_player import AudioPlayer
from ui.console_panel import ConsolePanel
from ui.download_panel import DownloadPanel
from ui.help_panel import HelpPanel
from ui.history_panel import VideoHistoryPanel
from ui.local_transcribe_panel import LocalTranscribePanel
from ui.transcript_viewer import TranscriptViewer
from ui.video_player import VideoPlayer

DARK_STYLE = """
/* =========================================================
   Design tokens (keep in sync across the app)
   ---------------------------------------------------------
   bg-canvas:   #13131f   surface for the app chrome
   bg-surface:  #1c1c2e   main working surface
   bg-raised:   #242438   cards, inputs, inactive tabs
   bg-hover:    #2d2d46   hover state for raised surfaces
   border:      #2f3056   subtle dividers
   text:        #f0f0f5   primary text
   text-dim:    #9a9ab0   secondary text
   text-mute:   #64647d   tertiary / disabled
   accent:      #e94560   primary brand (pink/red)
   accent-hi:   #ff5b7a   hover accent
   accent-lo:   #b83548   pressed accent
   success:     #4caf50   positive state
   warn:        #f5a623   warning state
   ========================================================= */

QMainWindow, QWidget {
    background-color: #13131f;
    color: #f0f0f5;
    font-family: "Segoe UI", "Inter", "SF Pro Text", Roboto, sans-serif;
    font-size: 13px;
}
QWidget:focus { outline: none; }

QLabel {
    color: #f0f0f5;
    font-size: 13px;
}
QLabel#title {
    font-size: 22px;
    font-weight: 700;
    color: #e94560;
    letter-spacing: 0.3px;
    padding-bottom: 4px;
}
QLabel#sectionLabel {
    color: #9a9ab0;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 1px;
}

/* Inputs */
QLineEdit, QTextEdit, QPlainTextEdit {
    background-color: #1c1c2e;
    border: 1px solid #2f3056;
    border-radius: 8px;
    padding: 9px 12px;
    color: #f0f0f5;
    font-size: 13px;
    selection-background-color: #e94560;
    selection-color: #fff;
}
QLineEdit:hover, QTextEdit:hover, QPlainTextEdit:hover {
    border: 1px solid #3a3b66;
}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border: 1px solid #e94560;
    background-color: #1f1f35;
}
QLineEdit:disabled {
    background-color: #1a1a28;
    color: #64647d;
}

/* Radio */
QRadioButton, QCheckBox {
    color: #f0f0f5;
    spacing: 8px;
    font-size: 13px;
    padding: 2px 4px;
}
QRadioButton::indicator, QCheckBox::indicator {
    width: 16px;
    height: 16px;
}
QRadioButton::indicator:checked {
    background-color: #e94560;
    border: 2px solid #e94560;
    border-radius: 9px;
}
QRadioButton::indicator:unchecked {
    background-color: #1c1c2e;
    border: 2px solid #3a3b66;
    border-radius: 9px;
}
QRadioButton::indicator:unchecked:hover {
    border: 2px solid #e94560;
}
QCheckBox::indicator:checked {
    background-color: #e94560;
    border: 2px solid #e94560;
    border-radius: 3px;
}
QCheckBox::indicator:unchecked {
    background-color: #1c1c2e;
    border: 2px solid #3a3b66;
    border-radius: 3px;
}

/* Combo */
QComboBox {
    background-color: #1c1c2e;
    border: 1px solid #2f3056;
    border-radius: 8px;
    padding: 7px 14px;
    color: #f0f0f5;
    min-width: 120px;
}
QComboBox:hover {
    border: 1px solid #3a3b66;
}
QComboBox:focus {
    border: 1px solid #e94560;
}
QComboBox::drop-down {
    border: none;
    width: 26px;
}
QComboBox::down-arrow {
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid #9a9ab0;
    margin-right: 8px;
}
QComboBox QAbstractItemView {
    background-color: #1c1c2e;
    color: #f0f0f5;
    border: 1px solid #2f3056;
    border-radius: 6px;
    padding: 4px;
    selection-background-color: #e94560;
    outline: 0;
}

/* Buttons */
QPushButton {
    background-color: #242438;
    color: #f0f0f5;
    border: none;
    border-radius: 8px;
    padding: 9px 18px;
    font-size: 13px;
    font-weight: 600;
}
QPushButton:hover {
    background-color: #2d2d46;
}
QPushButton:pressed {
    background-color: #1a1a2e;
}
QPushButton:disabled {
    background-color: #1a1a28;
    color: #64647d;
}
QPushButton#startBtn {
    background-color: #e94560;
    color: white;
    font-size: 14px;
    font-weight: 700;
    padding: 13px;
    letter-spacing: 0.5px;
}
QPushButton#startBtn:hover {
    background-color: #ff5b7a;
}
QPushButton#startBtn:pressed {
    background-color: #b83548;
}
QPushButton#startBtn:disabled {
    background-color: #242438;
    color: #64647d;
}
QPushButton#transcribeBtn {
    background-color: #4caf50;
    color: white;
    font-size: 13px;
    font-weight: 600;
}
QPushButton#transcribeBtn:hover {
    background-color: #66bb6a;
}
QPushButton#transcribeBtn:disabled {
    background-color: #242438;
    color: #64647d;
}

/* Progress */
QProgressBar {
    background-color: #1c1c2e;
    border: 1px solid #2f3056;
    border-radius: 8px;
    text-align: center;
    color: #f0f0f5;
    font-weight: 600;
    height: 22px;
}
QProgressBar::chunk {
    background-color: #e94560;
    border-radius: 7px;
    margin: 1px;
}

/* Scrollbar */
QScrollBar:vertical {
    background: transparent;
    width: 10px;
    border-radius: 5px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #2f3056;
    border-radius: 5px;
    min-height: 40px;
}
QScrollBar::handle:vertical:hover {
    background: #3a3b66;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: transparent;
}
QScrollBar:horizontal {
    background: transparent;
    height: 10px;
    border-radius: 5px;
}
QScrollBar::handle:horizontal {
    background: #2f3056;
    border-radius: 5px;
    min-width: 40px;
}
QScrollBar::handle:horizontal:hover {
    background: #3a3b66;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
}

/* Splitter */
QSplitter::handle {
    background-color: transparent;
}
QSplitter::handle:horizontal {
    width: 6px;
}
QSplitter::handle:vertical {
    height: 6px;
}
QSplitter::handle:hover {
    background-color: #2f3056;
}

/* Tabs */
QTabWidget::pane {
    border: 1px solid #2f3056;
    border-radius: 10px;
    background-color: #1c1c2e;
    top: -1px;
}
QTabBar::tab {
    background-color: transparent;
    color: #9a9ab0;
    border: none;
    padding: 10px 20px;
    margin-right: 4px;
    font-size: 13px;
    font-weight: 600;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
}
QTabBar::tab:selected {
    background-color: #1c1c2e;
    color: #e94560;
    border-bottom: 2px solid #e94560;
}
QTabBar::tab:hover:!selected {
    color: #f0f0f5;
    background-color: #1a1a28;
}

/* Slider */
QSlider::groove:horizontal {
    background: #2f3056;
    height: 5px;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    background: #e94560;
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}
QSlider::handle:horizontal:hover {
    background: #ff5b7a;
}
QSlider::sub-page:horizontal {
    background: #e94560;
    border-radius: 3px;
}

/* Video widget */
QVideoWidget {
    background-color: #000;
    border-radius: 8px;
}

/* Menu */
QMenu {
    background-color: #1c1c2e;
    color: #f0f0f5;
    border: 1px solid #2f3056;
    border-radius: 8px;
    padding: 4px;
}
QMenu::item {
    padding: 7px 22px;
    border-radius: 4px;
}
QMenu::item:selected {
    background-color: #e94560;
}
QMenu::separator {
    height: 1px;
    background: #2f3056;
    margin: 4px 8px;
}

/* Tooltip */
QToolTip {
    background-color: #1c1c2e;
    color: #f0f0f5;
    border: 1px solid #2f3056;
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 12px;
}
"""


class DownloadWorker(QThread):
    """Background worker for download + optional transcription."""

    progress = Signal(float, str)
    finished = Signal(dict, str)  # (metadata_dict, transcription_text)
    error = Signal(str)

    def __init__(self, url, fmt, output_dir, transcribe, language, api_key,
                 cookies_file=""):
        super().__init__()
        self.url = url
        self.fmt = fmt
        self.output_dir = output_dir
        self.transcribe = transcribe
        self.language = language
        self.api_key = api_key
        self.cookies_file = cookies_file
        self._downloader = None

    def cancel(self):
        if self._downloader:
            self._downloader.cancel()

    def run(self):
        try:
            self._downloader = VideoDownloader(
                progress_callback=lambda pct, msg: self.progress.emit(
                    pct * 0.7 if self.transcribe else pct, msg
                ),
                cookies_file=self.cookies_file,
            )
            result = self._downloader.download(self.url, self.fmt, self.output_dir)

            metadata = {
                "url": self.url,
                "filepath": result["filepath"],
                "title": result["title"],
                "duration": result.get("duration", 0),
                "uploader": result.get("uploader", ""),
                "thumbnail": result.get("thumbnail", ""),
                "format": self.fmt,
                "language": self.language,
            }

            if not self.transcribe:
                self.progress.emit(1.0, "Concluído!")
                self.finished.emit(metadata, "")
                return

            self.progress.emit(0.7, "Iniciando transcrição...")

            text = transcribe_file(
                audio_path=result["filepath"],
                api_key=self.api_key,
                language=self.language,
                on_progress=lambda pct, msg: self.progress.emit(0.7 + pct * 0.3, msg),
            )

            self.progress.emit(1.0, "Concluído!")
            self.finished.emit(metadata, text)

        except Exception as e:
            self.error.emit(str(e))


class TranscribeWorker(QThread):
    """Background worker for transcribing an existing video."""

    progress = Signal(float, str)
    finished = Signal(str, str)  # (media_path, transcription_text)
    error = Signal(str)

    def __init__(self, media_path, language, api_key):
        super().__init__()
        self.media_path = media_path
        self.language = language
        self.api_key = api_key

    def run(self):
        try:
            text = transcribe_file(
                audio_path=self.media_path,
                api_key=self.api_key,
                language=self.language,
                on_progress=lambda pct, msg: self.progress.emit(pct, msg),
            )
            self.finished.emit(self.media_path, text)
        except Exception as e:
            self.error.emit(str(e))


class UpdateWorker(QThread):
    """Background worker to update yt-dlp via pip."""

    output = Signal(str)
    finished = Signal(bool)  # success

    def run(self):
        try:
            self.output.emit("=== Atualizando yt-dlp ===\n")
            python = sys.executable
            proc = subprocess.Popen(
                [python, "-m", "pip", "install", "--upgrade", "yt-dlp"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            for line in proc.stdout:
                self.output.emit(line)
            proc.wait()
            success = proc.returncode == 0
            self.output.emit(f"\n=== {'Sucesso' if success else 'Falhou'} (código {proc.returncode}) ===\n")
            self.finished.emit(success)
        except Exception as e:
            self.output.emit(f"\nErro: {e}\n")
            self.finished.emit(False)


class MainWindow(QMainWindow):
    def __init__(self, api_key: str = ""):
        super().__init__()
        self.api_key = api_key
        self._download_worker = None
        self._transcribe_worker = None
        self._update_worker = None
        self._current_media_path = ""

        self.setWindowTitle("Super Video Downloader")
        self.setMinimumSize(960, 700)
        self.resize(1050, 780)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(0)

        # Splitter: history sidebar (left) | main content (right)
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(6)

        # --- LEFT: History panel ---
        output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output")
        self.history_panel = VideoHistoryPanel(output_dir)
        self.history_panel.setMinimumWidth(280)
        self.history_panel.setMaximumWidth(400)
        splitter.addWidget(self.history_panel)

        # --- RIGHT: Tab widget + Transcript viewer in a vertical splitter ---
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        right_splitter = QSplitter(Qt.Vertical)
        right_splitter.setHandleWidth(6)

        # Tab widget (top)
        self.tab_widget = QTabWidget()

        self.download_panel = DownloadPanel()
        self.tab_widget.addTab(self.download_panel, "Download")

        self.video_player = VideoPlayer()
        self.tab_widget.addTab(self.video_player, "Player")

        self.audio_player = AudioPlayer()
        self.tab_widget.addTab(self.audio_player, "Musica")

        self.local_transcribe = LocalTranscribePanel()
        self.tab_widget.addTab(self.local_transcribe, "Transcrever Local")

        self.console_panel = ConsolePanel()
        self.tab_widget.addTab(self.console_panel, "Console")

        self.help_panel = HelpPanel()
        self.tab_widget.addTab(self.help_panel, "Ajuda")

        right_splitter.addWidget(self.tab_widget)

        # Transcript viewer (bottom, always visible)
        self.transcript_viewer = TranscriptViewer()
        right_splitter.addWidget(self.transcript_viewer)

        right_splitter.setStretchFactor(0, 2)
        right_splitter.setStretchFactor(1, 1)
        right_splitter.setSizes([500, 250])

        right_layout.addWidget(right_splitter)
        splitter.addWidget(right_widget)

        # Splitter proportions
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([300, 700])

        main_layout.addWidget(splitter)

        # --- Connect signals ---
        self.download_panel.download_requested.connect(self._on_download_requested)
        self.download_panel.update_ytdlp_requested.connect(self._on_update_ytdlp)
        self.history_panel.video_selected.connect(self._on_video_selected)
        self.history_panel.video_delete.connect(self._on_video_delete)
        self.history_panel.video_transcribe.connect(self._on_transcribe_from_history)
        self.history_panel.video_platform_change.connect(self._on_platform_change)
        self.history_panel.video_rename.connect(self._on_video_rename)
        self.history_panel.video_folder_change.connect(self._on_folder_change)
        self.video_player.bookmarks_changed.connect(self._on_bookmarks_changed)
        # _on_position_saved dispatches the JSON write to a background thread,
        # so a direct connection here is fine (no UI-thread disk I/O).
        self.video_player.position_saved.connect(self._on_position_saved)
        self.video_player.notes_changed.connect(self._on_notes_changed)
        self.audio_player.position_saved.connect(self._on_position_saved)
        self.audio_player.track_changed.connect(self._on_audio_track_changed)
        self.transcript_viewer.transcribe_requested.connect(self._on_transcribe_current)
        self.transcript_viewer.ai_summary_requested.connect(self._on_ai_summary)
        self.local_transcribe.transcribe_requested.connect(self._on_local_transcribe)

    # -- Download flow --

    def closeEvent(self, event):
        """Properly stop the media players so audio doesn't keep playing in background."""
        try:
            self.video_player.shutdown()
        except Exception:
            pass
        try:
            self.audio_player.shutdown()
        except Exception:
            pass
        super().closeEvent(event)

    @Slot(str, str, bool, str)
    def _on_download_requested(self, url: str, fmt: str, do_transcribe: bool,
                               language: str):
        if not url:
            QMessageBox.warning(self, "Aviso", "Cole a URL do vídeo primeiro.")
            return

        if do_transcribe and not self.api_key:
            QMessageBox.warning(self, "Aviso", "DEEPGRAM_API_KEY não configurada no .env")
            return

        output_dir = self.download_panel.get_output_dir()
        cookies_file = self.download_panel.get_cookies_file()

        self.download_panel.set_progress(0, "Iniciando...")
        self.download_panel.set_enabled(False)
        self.transcript_viewer.clear()

        self._download_worker = DownloadWorker(
            url, fmt, output_dir, do_transcribe, language, self.api_key,
            cookies_file=cookies_file,
        )
        self._download_worker.progress.connect(self._on_download_progress)
        self._download_worker.finished.connect(self._on_download_finished)
        self._download_worker.error.connect(self._on_download_error)
        self._download_worker.start()

    @Slot(float, str)
    def _on_download_progress(self, pct: float, msg: str):
        self.download_panel.set_progress(pct, msg)

    @Slot(dict, str)
    def _on_download_finished(self, metadata: dict, text: str):
        self.download_panel.set_enabled(True)
        self.download_panel.set_progress(1.0, f"Salvo em: {metadata['filepath']}")

        # Create and save VideoData
        filepath = metadata["filepath"]
        data = VideoData(
            video_id=uuid.uuid4().hex[:12],
            url=metadata["url"],
            title=metadata["title"],
            platform=detect_platform(metadata["url"]),
            media_file=os.path.basename(filepath),
            format=metadata["format"],
            duration_seconds=metadata.get("duration", 0) or 0,
            uploader=metadata.get("uploader", ""),
            thumbnail_url=metadata.get("thumbnail", ""),
            created_at=datetime.now(timezone.utc).isoformat(),
            transcription=text,
            transcribed_at=datetime.now(timezone.utc).isoformat() if text else "",
            language=metadata.get("language", ""),
        )
        VideoStore.save(filepath, data)

        # Refresh sidebar and show transcription
        self.history_panel.refresh()
        self._current_media_path = filepath

        if text:
            self.transcript_viewer.show_transcription_text(text)
        else:
            self.transcript_viewer.show_video(filepath, data)

    @Slot(str)
    def _on_download_error(self, msg: str):
        self.download_panel.set_enabled(True)
        self.download_panel.set_progress(0, "")
        if "nao possui faixa de audio" in msg.lower() or "não possui faixa de áudio" in msg.lower():
            QMessageBox.warning(self, "Video sem audio", msg)
        else:
            QMessageBox.critical(self, "Erro", msg)

    # -- History selection --

    @Slot(str)
    def _on_video_selected(self, media_path: str):
        self._current_media_path = media_path
        data = VideoStore.load(media_path)
        self.transcript_viewer.show_video(media_path, data)

        ext = os.path.splitext(media_path)[1].lower()
        start_ms = data.last_position_ms if data else 0

        if ext == ".mp3":
            # Route audio files to the dedicated music player.
            # Queue = all MP3s currently visible in history (respects filters).
            mp3_queue = self.history_panel.visible_media_paths(fmt="mp3")
            if not mp3_queue:
                mp3_queue = [media_path]
            start_index = mp3_queue.index(media_path) if media_path in mp3_queue else 0
            # Stop the video player to avoid phantom playback
            self.video_player.stop()
            self.audio_player.load_queue(mp3_queue, start_index, start_position_ms=start_ms)
            self.tab_widget.setCurrentWidget(self.audio_player)
            return

        # Video path — stop audio player to avoid two things playing
        self.audio_player.stop()
        bookmarks = data.bookmarks if data else []
        notes = data.notes if data else ""
        self.video_player.load_video(
            media_path, bookmarks=bookmarks,
            start_position_ms=start_ms, notes=notes,
        )
        self.tab_widget.setCurrentWidget(self.video_player)

    @Slot(str)
    def _on_audio_track_changed(self, media_path: str):
        """Audio player auto-advanced to a new track — sync the rest of the UI."""
        self._current_media_path = media_path
        data = VideoStore.load(media_path)
        self.transcript_viewer.show_video(media_path, data)
        self.history_panel.set_selected_path(media_path)
        # Lightweight refresh of visual selection
        for it in self.history_panel._items:
            it.set_selected(it.media_path == media_path)

    @Slot(str, list)
    def _on_bookmarks_changed(self, media_path: str, bookmarks: list):
        VideoStore.update_bookmarks(media_path, bookmarks)

    @Slot(str, int)
    def _on_position_saved(self, media_path: str, position_ms: int):
        # Run the read-modify-write on a background thread; the JSON sidecar
        # can be hundreds of KB when a transcript is present and blocking
        # the main thread here glitches playback.
        class _PosSaveRunnable(QRunnable):
            def __init__(self, mp: str, pos: int):
                super().__init__()
                self._mp = mp
                self._pos = pos
                self.setAutoDelete(True)
            def run(self):
                try:
                    VideoStore.update_position(self._mp, self._pos)
                except Exception:
                    pass
        QThreadPool.globalInstance().start(_PosSaveRunnable(media_path, position_ms))

    @Slot(str, str)
    def _on_notes_changed(self, media_path: str, notes: str):
        VideoStore.update_notes(media_path, notes)

    @Slot()
    def _on_ai_summary(self):
        transcript = self.transcript_viewer.current_transcription
        if not transcript.strip():
            QMessageBox.information(self, "Aviso", "Nao ha transcricao para analisar.")
            return
        title = ""
        if self._current_media_path:
            data = VideoStore.load(self._current_media_path)
            if data:
                title = data.title
        from ui.ai_summary_dialog import AISummaryDialog
        dlg = AISummaryDialog(transcript, title=title, parent=self)
        dlg.exec()

    # -- Delete --

    @Slot(str)
    def _on_video_delete(self, media_path: str):
        reply = QMessageBox.question(
            self, "Confirmar exclusão",
            f"Excluir este vídeo e seus dados?\n{os.path.basename(media_path)}",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        # Always release the player source before deleting to free file handle on Windows
        self.video_player.stop()

        try:
            VideoStore.delete_video(media_path)
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Não foi possível excluir:\n{e}")
            return

        if self._current_media_path == media_path:
            self._current_media_path = ""
            self.transcript_viewer.clear()
        self.history_panel.refresh()

    # -- Platform change --

    @Slot(str, str)
    def _on_platform_change(self, media_path: str, new_platform: str):
        VideoStore.update_platform(media_path, new_platform)
        self.history_panel.refresh()

    # -- Rename --

    @Slot(str, str)
    def _on_video_rename(self, media_path: str, new_title: str):
        # Release player so the file can be renamed on Windows
        is_current = self._current_media_path == media_path
        if is_current:
            self.video_player.stop()

        try:
            new_path = VideoStore.rename_video(media_path, new_title)
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Não foi possível renomear:\n{e}")
            return

        if is_current:
            self._current_media_path = new_path
            data = VideoStore.load(new_path)
            self.transcript_viewer.show_video(new_path, data)
            self.video_player.load_video(new_path)

        if is_current:
            self.history_panel.set_selected_path(new_path)
        self.history_panel.refresh()

    # -- Folder change --

    @Slot(list, str)
    def _on_folder_change(self, media_paths: list[str], folder: str):
        VideoStore.update_folder_bulk(media_paths, folder)
        self.history_panel.refresh()

    # -- Local file transcription --

    @Slot(str, str)
    def _on_local_transcribe(self, file_path: str, language: str):
        if not self.api_key:
            QMessageBox.warning(self, "Aviso", "DEEPGRAM_API_KEY não configurada no .env")
            return
        if not os.path.isfile(file_path):
            QMessageBox.warning(self, "Aviso", "Arquivo não encontrado.")
            return

        self.local_transcribe.set_enabled(False)
        self.local_transcribe.set_progress(0, "Transcrevendo...")
        self.transcript_viewer.clear()

        self._transcribe_worker = TranscribeWorker(file_path, language, self.api_key)
        self._transcribe_worker.progress.connect(self._on_local_transcribe_progress)
        self._transcribe_worker.finished.connect(self._on_local_transcribe_finished)
        self._transcribe_worker.error.connect(self._on_local_transcribe_error)
        self._transcribe_worker.start()

    @Slot(float, str)
    def _on_local_transcribe_progress(self, pct: float, msg: str):
        self.local_transcribe.set_progress(pct, msg)

    @Slot(str, str)
    def _on_local_transcribe_finished(self, media_path: str, text: str):
        self.local_transcribe.set_enabled(True)

        if not text.strip():
            self.local_transcribe.set_progress(0, "")
            title, msg = self._empty_transcription_reason(media_path)
            QMessageBox.warning(self, title, msg)
            return

        self.local_transcribe.set_progress(1.0, "Transcrição concluída!")
        self.transcript_viewer.show_transcription_text(text)
        self.transcript_viewer._current_media_path = media_path

    def _empty_transcription_reason(self, media_path: str) -> tuple[str, str]:
        """Diagnose why a transcription came back empty. Returns (title, message)."""
        has_audio = has_audio_stream(media_path) if media_path else None
        if has_audio is False:
            return (
                "Video sem audio",
                "Este video nao possui faixa de audio — nao ha nada para transcrever.\n\n"
                "Isso acontece com alguns videos do TikTok/Instagram que sao apenas visuais "
                "(sem fala nem musica).",
            )
        return (
            "Transcricao vazia",
            "A transcricao retornou vazia. Causas comuns:\n\n"
            "- O video tem apenas musica instrumental ou sons (sem fala)\n"
            "- O audio esta muito baixo ou com ruido excessivo\n"
            "- O idioma selecionado nao bate com a fala "
            "(tente \"Auto (detectar)\")",
        )

    @Slot(str)
    def _on_local_transcribe_error(self, msg: str):
        self.local_transcribe.set_enabled(True)
        self.local_transcribe.set_progress(0, "")
        if "nao possui faixa de audio" in msg.lower() or "não possui faixa de áudio" in msg.lower():
            QMessageBox.warning(self, "Video sem audio", msg)
        else:
            QMessageBox.critical(self, "Erro na transcrição", msg)

    # -- Update yt-dlp --

    @Slot()
    def _on_update_ytdlp(self):
        if self._update_worker and self._update_worker.isRunning():
            return
        # Switch to console tab
        self.tab_widget.setCurrentWidget(self.console_panel)
        self.download_panel.update_btn.setEnabled(False)

        self._update_worker = UpdateWorker()
        self._update_worker.output.connect(self.console_panel.append, Qt.QueuedConnection)
        self._update_worker.finished.connect(self._on_update_finished)
        self._update_worker.start()

    @Slot(bool)
    def _on_update_finished(self, success: bool):
        self.download_panel.update_btn.setEnabled(True)

    # -- Transcribe existing video --

    @Slot(str)
    def _on_transcribe_from_history(self, media_path: str):
        """Transcribe a video selected from the history context menu."""
        self._start_transcription(media_path)

    @Slot()
    def _on_transcribe_current(self):
        """Transcribe the currently selected video (button in TranscriptViewer)."""
        if self._current_media_path:
            self._start_transcription(self._current_media_path)

    def _start_transcription(self, media_path: str):
        if not self.api_key:
            QMessageBox.warning(self, "Aviso", "DEEPGRAM_API_KEY não configurada no .env")
            return

        if not os.path.isfile(media_path):
            QMessageBox.warning(self, "Aviso", "Arquivo de mídia não encontrado.")
            return

        # Only trust the saved language if a transcription already succeeded;
        # otherwise use the combo selection (default: auto-detect).
        data = VideoStore.load(media_path)
        if data and data.language and data.transcription:
            language = data.language
        else:
            language = self.download_panel.lang_combo.currentData() or "auto"

        self._current_media_path = media_path
        self.transcript_viewer.set_transcribing(True)
        self.download_panel.set_progress(0, "Transcrevendo...")

        self._transcribe_worker = TranscribeWorker(media_path, language, self.api_key)
        self._transcribe_worker.progress.connect(self._on_transcribe_progress)
        self._transcribe_worker.finished.connect(self._on_transcribe_finished)
        self._transcribe_worker.error.connect(self._on_transcribe_error)
        self._transcribe_worker.start()

    @Slot(float, str)
    def _on_transcribe_progress(self, pct: float, msg: str):
        self.download_panel.set_progress(pct, msg)

    @Slot(str, str)
    def _on_transcribe_finished(self, media_path: str, text: str):
        self.transcript_viewer.set_transcribing(False)

        if not text.strip():
            self.download_panel.set_progress(0, "")
            title, msg = self._empty_transcription_reason(media_path)
            QMessageBox.warning(self, title, msg)
            return

        self.download_panel.set_progress(1.0, "Transcrição concluída!")

        language = self.download_panel.lang_combo.currentData() or "auto"
        VideoStore.update_transcription(media_path, text, language)
        self.history_panel.refresh()

        # Update viewer if still looking at same video
        if self._current_media_path == media_path:
            updated = VideoStore.load(media_path)
            self.transcript_viewer.show_video(media_path, updated)

    @Slot(str)
    def _on_transcribe_error(self, msg: str):
        self.download_panel.set_progress(0, "")
        self.transcript_viewer.set_transcribing(False)
        if "nao possui faixa de audio" in msg.lower() or "não possui faixa de áudio" in msg.lower():
            QMessageBox.warning(self, "Video sem audio", msg)
        else:
            QMessageBox.critical(self, "Erro na transcrição", msg)
