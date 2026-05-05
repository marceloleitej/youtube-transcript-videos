"""Transcript viewer — displays transcription text with action buttons."""

import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class TranscriptViewer(QWidget):
    """Read-only text area for viewing transcriptions with action buttons."""

    transcribe_requested = Signal()
    ai_summary_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_media_path = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Header row with spinner
        header_row = QHBoxLayout()
        header_row.setSpacing(8)
        self.header_label = QLabel("Transcrição:")
        header_row.addWidget(self.header_label)
        from ui.spinner import Spinner
        self.spinner = Spinner(color="#e94560", size=18)
        header_row.addWidget(self.spinner)
        header_row.addStretch()
        layout.addLayout(header_row)

        # Text area
        self.text_area = QTextEdit()
        self.text_area.setReadOnly(True)
        self.text_area.setMinimumHeight(120)
        self.text_area.setPlaceholderText("Selecione um vídeo no histórico ou faça um novo download...")
        layout.addWidget(self.text_area, 1)

        # Buttons row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self.copy_btn = QPushButton("Copiar Texto")
        self.copy_btn.clicked.connect(self._copy_text)
        btn_row.addWidget(self.copy_btn)

        self.save_btn = QPushButton("Salvar .txt")
        self.save_btn.clicked.connect(self._save_text)
        btn_row.addWidget(self.save_btn)

        self.transcribe_btn = QPushButton("Transcrever")
        self.transcribe_btn.setObjectName("transcribeBtn")
        self.transcribe_btn.clicked.connect(self.transcribe_requested.emit)
        btn_row.addWidget(self.transcribe_btn)

        self.ai_btn = QPushButton("Analisar com IA")
        self.ai_btn.setToolTip("Gerar resumo, capitulos ou Q&A com Gemini")
        self.ai_btn.setStyleSheet(
            "QPushButton { background-color: #5b4ae8; color: white; "
            "font-size: 13px; font-weight: 600; border-radius: 6px; "
            "padding: 8px 14px; }"
            "QPushButton:hover { background-color: #6e5eff; }"
        )
        self.ai_btn.clicked.connect(self.ai_summary_requested.emit)
        btn_row.addWidget(self.ai_btn)

        btn_row.addStretch()
        layout.addLayout(btn_row)

        # Initial state
        self.clear()

    def show_video(self, media_path: str, data) -> None:
        """Display transcription for a video. data is a VideoData instance."""
        self._current_media_path = media_path

        if data and data.transcription:
            self.text_area.setPlainText(data.transcription)
            self.copy_btn.setVisible(True)
            self.save_btn.setVisible(True)
            self.transcribe_btn.setVisible(False)
            self.ai_btn.setVisible(True)
        else:
            self.text_area.clear()
            self.text_area.setPlaceholderText("Este vídeo ainda não foi transcrito.")
            self.copy_btn.setVisible(False)
            self.save_btn.setVisible(False)
            self.transcribe_btn.setVisible(True)
            self.ai_btn.setVisible(False)

    def show_transcription_text(self, text: str) -> None:
        """Show transcription text directly (e.g. after a new download+transcribe)."""
        if text:
            self.text_area.setPlainText(text)
            self.copy_btn.setVisible(True)
            self.save_btn.setVisible(True)
            self.transcribe_btn.setVisible(False)
            self.ai_btn.setVisible(True)

    def clear(self) -> None:
        """Reset to empty state."""
        self._current_media_path = ""
        self.text_area.clear()
        self.text_area.setPlaceholderText("Selecione um vídeo no histórico ou faça um novo download...")
        self.copy_btn.setVisible(False)
        self.save_btn.setVisible(False)
        self.transcribe_btn.setVisible(False)
        self.ai_btn.setVisible(False)

    @property
    def current_transcription(self) -> str:
        return self.text_area.toPlainText()

    def set_transcribing(self, active: bool) -> None:
        """Toggle UI state during transcription."""
        self.transcribe_btn.setEnabled(not active)
        if active:
            self.text_area.setPlainText("Transcrevendo...")
            self.spinner.start()
        else:
            self.spinner.stop()

    def _copy_text(self) -> None:
        text = self.text_area.toPlainText()
        if text:
            QApplication.clipboard().setText(text)

    def _save_text(self) -> None:
        text = self.text_area.toPlainText()
        if not text:
            return
        default_name = ""
        if self._current_media_path:
            default_name = os.path.splitext(os.path.basename(self._current_media_path))[0] + ".txt"
        path, _ = QFileDialog.getSaveFileName(
            self, "Salvar transcrição", default_name, "Text Files (*.txt)"
        )
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
