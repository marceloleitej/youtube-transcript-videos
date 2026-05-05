"""Download panel — URL input, format/mode selectors, progress bar."""

import os

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)


class DownloadPanel(QWidget):
    """Panel with all download controls extracted from the old MainWindow."""

    download_requested = Signal(str, str, bool, str)  # url, format, do_transcribe, language
    update_ytdlp_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cookies_file = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # Title
        title = QLabel("Super Video Downloader")
        title.setObjectName("title")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # URL input with paste-from-clipboard button
        layout.addWidget(QLabel("URL do Vídeo:"))
        url_row = QHBoxLayout()
        url_row.setSpacing(6)
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Cole a URL do video aqui (YouTube, TikTok, Instagram, Facebook)")
        url_row.addWidget(self.url_input, 1)
        self.paste_btn = QPushButton("Colar")
        self.paste_btn.setToolTip("Colar da area de transferencia (Ctrl+V)")
        self.paste_btn.setStyleSheet(
            "QPushButton { background-color: #242438; color: #f0f0f5; "
            "font-size: 12px; font-weight: 600; border-radius: 6px; padding: 8px 14px; }"
            "QPushButton:hover { background-color: #2d2d46; }"
        )
        self.paste_btn.clicked.connect(self._paste_from_clipboard)
        url_row.addWidget(self.paste_btn)
        layout.addLayout(url_row)

        # Mode: download only vs download+transcribe
        layout.addWidget(QLabel("Modo:"))
        mode_row = QHBoxLayout()
        self.mode_download = QRadioButton("Só Baixar")
        self.mode_transcribe = QRadioButton("Baixar + Transcrever")
        self.mode_download.setChecked(True)
        mode_group = QButtonGroup(self)
        mode_group.addButton(self.mode_download)
        mode_group.addButton(self.mode_transcribe)
        mode_row.addWidget(self.mode_download)
        mode_row.addWidget(self.mode_transcribe)
        mode_row.addStretch()
        layout.addLayout(mode_row)

        # Format: MP4 vs MP3
        layout.addWidget(QLabel("Formato:"))
        fmt_row = QHBoxLayout()
        self.fmt_mp4 = QRadioButton("Vídeo MP4")
        self.fmt_mp3 = QRadioButton("Áudio MP3")
        self.fmt_mp4.setChecked(True)
        fmt_group = QButtonGroup(self)
        fmt_group.addButton(self.fmt_mp4)
        fmt_group.addButton(self.fmt_mp3)
        fmt_row.addWidget(self.fmt_mp4)
        fmt_row.addWidget(self.fmt_mp3)
        fmt_row.addStretch()
        layout.addLayout(fmt_row)

        # Language (for transcription)
        lang_row = QHBoxLayout()
        self.lang_label = QLabel("Idioma (transcrição):")
        self.lang_combo = QComboBox()
        for label, code in [
            ("Auto (detectar)", "auto"),
            ("pt-BR", "pt-BR"), ("en", "en"), ("es", "es"), ("fr", "fr"),
            ("de", "de"), ("it", "it"), ("ja", "ja"), ("ko", "ko"), ("zh", "zh"),
        ]:
            self.lang_combo.addItem(label, code)
        lang_row.addWidget(self.lang_label)
        lang_row.addWidget(self.lang_combo)
        lang_row.addStretch()
        layout.addLayout(lang_row)

        # Cookies file (for YouTube anti-bot)
        cookies_row = QHBoxLayout()
        cookies_row.addWidget(QLabel("Cookies:"))
        self.cookies_label = QLabel("Nenhum")
        self.cookies_label.setStyleSheet("color: #e94560; font-size: 12px;")
        cookies_row.addWidget(self.cookies_label, 1)
        self.cookies_btn = QPushButton("Importar cookies.txt")
        self.cookies_btn.setToolTip(
            "Exporte cookies do seu navegador usando a extensão\n"
            "\"Get cookies.txt LOCALLY\" e importe o arquivo aqui."
        )
        self.cookies_btn.clicked.connect(self._import_cookies)
        cookies_row.addWidget(self.cookies_btn)
        self.cookies_clear_btn = QPushButton("Limpar")
        self.cookies_clear_btn.setFixedWidth(60)
        self.cookies_clear_btn.clicked.connect(self._clear_cookies)
        self.cookies_clear_btn.setVisible(False)
        cookies_row.addWidget(self.cookies_clear_btn)
        layout.addLayout(cookies_row)

        # Output directory
        dir_row = QHBoxLayout()
        dir_row.addWidget(QLabel("Salvar em:"))
        self.dir_input = QLineEdit()
        default_output = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output")
        self.dir_input.setText(default_output)
        dir_row.addWidget(self.dir_input, 1)
        self.dir_btn = QPushButton("Alterar")
        self.dir_btn.clicked.connect(self._choose_dir)
        dir_row.addWidget(self.dir_btn)
        layout.addLayout(dir_row)

        # Start button
        self.start_btn = QPushButton("INICIAR")
        self.start_btn.setObjectName("startBtn")
        self.start_btn.clicked.connect(self._on_start)
        layout.addWidget(self.start_btn)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1000)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("%p%")
        layout.addWidget(self.progress_bar)

        # Status label
        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)

        # Update yt-dlp button
        self.update_btn = QPushButton("Atualizar yt-dlp")
        self.update_btn.clicked.connect(self.update_ytdlp_requested.emit)
        layout.addWidget(self.update_btn)

        # Toggle transcription widgets visibility
        self.mode_download.toggled.connect(self._update_mode_visibility)
        self._update_mode_visibility()

        # Auto-load cookies.txt from app directory if exists
        auto_cookies = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cookies.txt")
        if os.path.isfile(auto_cookies):
            self._set_cookies_file(auto_cookies)

    def get_output_dir(self) -> str:
        return self.dir_input.text().strip() or "output"

    def get_cookies_file(self) -> str:
        """Return the path to the cookies.txt file, or empty string."""
        if self._cookies_file and os.path.isfile(self._cookies_file):
            return self._cookies_file
        return ""

    @Slot()
    def _paste_from_clipboard(self) -> None:
        text = QApplication.clipboard().text().strip()
        if text:
            self.url_input.setText(text)
            self.url_input.setFocus()

    def set_progress(self, pct: float, msg: str) -> None:
        self.progress_bar.setValue(int(pct * 1000))
        self.status_label.setText(msg)
        # Switch chunk color to green on completion, back to accent otherwise
        if pct >= 1.0:
            self.progress_bar.setStyleSheet(
                "QProgressBar::chunk { background-color: #4caf50; border-radius: 7px; margin: 1px; }"
            )
        else:
            self.progress_bar.setStyleSheet("")  # fall back to DARK_STYLE default

    def set_enabled(self, enabled: bool) -> None:
        self.start_btn.setEnabled(enabled)

    def reset(self) -> None:
        self.progress_bar.setValue(0)
        self.status_label.setText("")
        self.url_input.clear()

    def _set_cookies_file(self, path: str) -> None:
        self._cookies_file = path
        name = os.path.basename(path)
        self.cookies_label.setText(f"Carregado: {name}")
        self.cookies_label.setStyleSheet("color: #4caf50; font-size: 12px;")
        self.cookies_clear_btn.setVisible(True)

    @Slot()
    def _import_cookies(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Importar cookies.txt",
            "", "Cookie files (*.txt);;All files (*)",
        )
        if path:
            self._set_cookies_file(path)

    @Slot()
    def _clear_cookies(self):
        self._cookies_file = ""
        self.cookies_label.setText("Nenhum")
        self.cookies_label.setStyleSheet("color: #e94560; font-size: 12px;")
        self.cookies_clear_btn.setVisible(False)

    @Slot()
    def _update_mode_visibility(self):
        show = self.mode_transcribe.isChecked()
        self.lang_label.setVisible(show)
        self.lang_combo.setVisible(show)

    @Slot()
    def _choose_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Escolher pasta de destino", self.dir_input.text())
        if d:
            self.dir_input.setText(d)

    @Slot()
    def _on_start(self):
        url = self.url_input.text().strip()
        if not url:
            return
        fmt = "mp3" if self.fmt_mp3.isChecked() else "mp4"
        do_transcribe = self.mode_transcribe.isChecked()
        language = self.lang_combo.currentData() or "auto"
        self.download_requested.emit(url, fmt, do_transcribe, language)
