"""Local file transcription panel — drag-and-drop or browse for a local video/audio file."""

import os

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class DropArea(QLabel):
    """A label that accepts drag-and-drop of media files."""

    file_dropped = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setAlignment(Qt.AlignCenter)
        self.setText("Arraste um arquivo de video/audio aqui\n\n(.mp4  .mp3  .m4a  .wav  .ogg  .webm)")
        self.setMinimumHeight(120)
        self.setStyleSheet(
            "QLabel { background-color: #1c1c2e; border: 2px dashed #2f3056; "
            "border-radius: 10px; color: #9a9ab0; font-size: 14px; padding: 28px; }"
        )

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    ext = os.path.splitext(url.toLocalFile())[1].lower()
                    if ext in (".mp4", ".mp3", ".m4a", ".wav", ".ogg", ".webm", ".flac", ".mkv"):
                        event.acceptProposedAction()
                        self.setStyleSheet(
                            "QLabel { background-color: #242438; border: 2px dashed #e94560; "
                            "border-radius: 10px; color: #e94560; font-size: 14px; padding: 28px; }"
                        )
                        return
        event.ignore()

    def dragLeaveEvent(self, event):
        self.setStyleSheet(
            "QLabel { background-color: #1c1c2e; border: 2px dashed #2f3056; "
            "border-radius: 10px; color: #9a9ab0; font-size: 14px; padding: 28px; }"
        )

    def dropEvent(self, event):
        self.setStyleSheet(
            "QLabel { background-color: #242438; border: 2px dashed #4caf50; "
            "border-radius: 10px; color: #4caf50; font-size: 14px; padding: 28px; }"
        )
        for url in event.mimeData().urls():
            if url.isLocalFile():
                self.file_dropped.emit(url.toLocalFile())
                return


class LocalTranscribePanel(QWidget):
    """Panel for transcribing a local video/audio file."""

    transcribe_requested = Signal(str, str)  # file_path, language

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        # Title
        title = QLabel("Transcrever Arquivo Local")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            "font-size: 22px; font-weight: 700; color: #e94560; "
            "letter-spacing: 0.3px; padding-bottom: 4px;"
        )
        layout.addWidget(title)

        # Drop area
        self.drop_area = DropArea()
        self.drop_area.file_dropped.connect(self._on_file_dropped)
        layout.addWidget(self.drop_area)

        # File path row
        file_row = QHBoxLayout()
        file_row.addWidget(QLabel("Arquivo:"))
        self.file_input = QLineEdit()
        self.file_input.setPlaceholderText("Caminho do arquivo de video/audio...")
        self.file_input.setReadOnly(True)
        file_row.addWidget(self.file_input, 1)
        self.browse_btn = QPushButton("Procurar")
        self.browse_btn.clicked.connect(self._browse_file)
        file_row.addWidget(self.browse_btn)
        layout.addLayout(file_row)

        # Language row
        lang_row = QHBoxLayout()
        lang_row.addWidget(QLabel("Idioma:"))
        self.lang_combo = QComboBox()
        for label, code in [
            ("Auto (detectar)", "auto"),
            ("pt-BR", "pt-BR"), ("en", "en"), ("es", "es"), ("fr", "fr"),
            ("de", "de"), ("it", "it"), ("ja", "ja"), ("ko", "ko"), ("zh", "zh"),
        ]:
            self.lang_combo.addItem(label, code)
        lang_row.addWidget(self.lang_combo)
        lang_row.addStretch()
        layout.addLayout(lang_row)

        # Transcribe button
        self.start_btn = QPushButton("TRANSCREVER")
        self.start_btn.setObjectName("startBtn")
        self.start_btn.clicked.connect(self._on_start)
        layout.addWidget(self.start_btn)

        # Progress
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1000)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("%p%")
        layout.addWidget(self.progress_bar)

        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)

        layout.addStretch()

    def set_progress(self, pct: float, msg: str) -> None:
        self.progress_bar.setValue(int(pct * 1000))
        self.status_label.setText(msg)

    def set_enabled(self, enabled: bool) -> None:
        self.start_btn.setEnabled(enabled)
        self.browse_btn.setEnabled(enabled)

    @Slot(str)
    def _on_file_dropped(self, path: str):
        self.file_input.setText(path)
        self.drop_area.setText(f"Arquivo carregado:\n{os.path.basename(path)}")

    @Slot()
    def _browse_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Selecionar arquivo de video/audio", "",
            "Media files (*.mp4 *.mp3 *.m4a *.wav *.ogg *.webm *.flac *.mkv);;All files (*)",
        )
        if path:
            self.file_input.setText(path)
            self.drop_area.setText(f"Arquivo carregado:\n{os.path.basename(path)}")

    @Slot()
    def _on_start(self):
        path = self.file_input.text().strip()
        if not path:
            return
        language = self.lang_combo.currentData() or "auto"
        self.transcribe_requested.emit(path, language)
