"""Dialog for AI-powered summarization via Gemini with streaming output."""

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
)

from core.ai_summary import DEFAULT_MODEL, PROMPTS, list_models, summarize_stream


class _SummaryWorker(QThread):
    chunk = Signal(str)
    done = Signal()
    error = Signal(str)

    def __init__(self, transcript: str, mode: str, question: str, model: str):
        super().__init__()
        self.transcript = transcript
        self.mode = mode
        self.question = question
        self.model = model

    def run(self):
        try:
            for c in summarize_stream(self.transcript, self.mode, self.question, self.model):
                self.chunk.emit(c)
            self.done.emit()
        except Exception as e:
            self.error.emit(str(e))


class AISummaryDialog(QDialog):
    """Modal dialog that streams a Gemini-generated summary/chapters/Q&A."""

    def __init__(self, transcript: str, title: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Analise com IA (Gemini)")
        self.setMinimumSize(620, 500)
        self.resize(760, 640)
        self._transcript = transcript
        self._worker: _SummaryWorker | None = None
        self._accumulated = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # Video title
        if title:
            title_lbl = QLabel(f"<b>{title}</b>")
            title_lbl.setStyleSheet("color: #f0f0f5; font-size: 14px;")
            layout.addWidget(title_lbl)

        # Mode + model selectors
        top = QHBoxLayout()
        top.setSpacing(8)

        top.addWidget(QLabel("Modo:"))
        self.mode_combo = QComboBox()
        for key, (label, _) in PROMPTS.items():
            self.mode_combo.addItem(label, key)
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        top.addWidget(self.mode_combo)

        top.addSpacing(12)
        top.addWidget(QLabel("Modelo:"))
        self.model_combo = QComboBox()
        self.model_combo.setMinimumWidth(200)
        top.addWidget(self.model_combo)

        top.addStretch()
        layout.addLayout(top)

        # Question input (only for Q&A)
        self.question_edit = QLineEdit()
        self.question_edit.setPlaceholderText("Digite uma pergunta sobre o video...")
        self.question_edit.setVisible(False)
        layout.addWidget(self.question_edit)

        # Output
        self.output = QTextBrowser()
        self.output.setOpenExternalLinks(True)
        self.output.setStyleSheet(
            "QTextBrowser { background-color: #1c1c2e; color: #f0f0f5; "
            "border: 1px solid #2f3056; border-radius: 8px; padding: 12px; "
            "font-size: 13px; }"
        )
        layout.addWidget(self.output, 1)

        # Status with spinner
        from ui.spinner import Spinner
        status_row = QHBoxLayout()
        self.spinner = Spinner(color="#e94560", size=16)
        status_row.addWidget(self.spinner)
        self.status_lbl = QLabel("")
        self.status_lbl.setStyleSheet("color: #9a9ab0; font-size: 11px;")
        status_row.addWidget(self.status_lbl)
        status_row.addStretch()
        layout.addLayout(status_row)

        # Buttons
        btns = QHBoxLayout()
        btns.setSpacing(8)

        self.run_btn = QPushButton("Gerar")
        self.run_btn.setObjectName("startBtn")
        self.run_btn.clicked.connect(self._start)
        btns.addWidget(self.run_btn)

        self.copy_btn = QPushButton("Copiar")
        self.copy_btn.clicked.connect(self._copy)
        self.copy_btn.setEnabled(False)
        btns.addWidget(self.copy_btn)

        self.save_btn = QPushButton("Salvar .md")
        self.save_btn.clicked.connect(self._save)
        self.save_btn.setEnabled(False)
        btns.addWidget(self.save_btn)

        btns.addStretch()
        self.close_btn = QPushButton("Fechar")
        self.close_btn.clicked.connect(self.reject)
        btns.addWidget(self.close_btn)
        layout.addLayout(btns)

        self._load_models_async()

    def _load_models_async(self) -> None:
        # Populate with defaults immediately, then refresh
        self.model_combo.addItem(DEFAULT_MODEL)
        self.status_lbl.setText("Carregando modelos...")
        try:
            models = list_models()
        except Exception:
            models = [DEFAULT_MODEL]
        self.model_combo.clear()
        for m in models:
            self.model_combo.addItem(m)
        idx = self.model_combo.findText(DEFAULT_MODEL)
        if idx >= 0:
            self.model_combo.setCurrentIndex(idx)
        self.status_lbl.setText("")

    def _on_mode_changed(self):
        mode = self.mode_combo.currentData()
        self.question_edit.setVisible(mode == "qa")

    def _start(self):
        if self._worker and self._worker.isRunning():
            return
        mode = self.mode_combo.currentData()
        question = self.question_edit.text().strip() if mode == "qa" else ""
        if mode == "qa" and not question:
            QMessageBox.warning(self, "Atencao", "Digite uma pergunta.")
            return

        self._accumulated = ""
        self.output.clear()
        self.run_btn.setEnabled(False)
        self.copy_btn.setEnabled(False)
        self.save_btn.setEnabled(False)
        self.spinner.start()
        self.status_lbl.setText("Gerando com Gemini...")

        self._worker = _SummaryWorker(
            self._transcript,
            mode,
            question,
            self.model_combo.currentText(),
        )
        self._worker.chunk.connect(self._on_chunk)
        self._worker.done.connect(self._on_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_chunk(self, text: str):
        self._accumulated += text
        # Render markdown progressively
        self.output.setMarkdown(self._accumulated)
        sb = self.output.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_done(self):
        self.run_btn.setEnabled(True)
        self.copy_btn.setEnabled(True)
        self.save_btn.setEnabled(True)
        self.spinner.stop()
        self.status_lbl.setStyleSheet("color: #4caf50; font-size: 11px;")
        self.status_lbl.setText("Concluido.")

    def _on_error(self, msg: str):
        self.run_btn.setEnabled(True)
        self.spinner.stop()
        self.status_lbl.setStyleSheet("color: #9a9ab0; font-size: 11px;")
        self.status_lbl.setText("")
        QMessageBox.critical(self, "Erro", msg)

    def _copy(self):
        QApplication.clipboard().setText(self._accumulated)
        self.status_lbl.setText("Copiado.")

    def _save(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Salvar resumo", "resumo.md", "Markdown (*.md);;Text (*.txt)"
        )
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self._accumulated)
            self.status_lbl.setText(f"Salvo em {path}")
