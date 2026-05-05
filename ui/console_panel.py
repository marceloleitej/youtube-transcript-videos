"""Internal console panel — captures stdout/stderr into a dark text widget."""

import sys
import threading
from collections import deque

from PySide6.QtCore import QTimer, Slot
from PySide6.QtWidgets import (
    QHBoxLayout,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class StreamRedirector:
    """Redirects a stream (stdout/stderr) to a thread-safe buffer.

    NOT a QObject — never emits signals.  The ConsolePanel drains the
    buffer from the main thread via a QTimer.
    """

    def __init__(self, original_stream=None):
        self._original = original_stream
        # Bounded so a stalled UI thread (drain timer not firing) can't
        # let a runaway producer balloon memory. Oldest entries drop first.
        self._buffer: deque[str] = deque(maxlen=10000)
        self._lock = threading.Lock()

    def write(self, text: str):
        if text:
            with self._lock:
                self._buffer.append(text)
        if self._original:
            try:
                self._original.write(text)
            except Exception:
                pass

    def flush(self):
        if self._original:
            try:
                self._original.flush()
            except Exception:
                pass

    def drain(self) -> str:
        """Return and clear all buffered text (called from main thread)."""
        with self._lock:
            if not self._buffer:
                return ""
            text = "".join(self._buffer)
            self._buffer.clear()
            return text


class ConsolePanel(QWidget):
    """Read-only console panel with dark background and green monospace text."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self._stdout_redirector: StreamRedirector | None = None
        self._stderr_redirector: StreamRedirector | None = None
        self._orig_stdout = None
        self._orig_stderr = None
        self._timer: QTimer | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Top bar
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(0, 0, 0, 0)

        clear_btn = QPushButton("Limpar")
        clear_btn.setFixedWidth(80)
        clear_btn.clicked.connect(self._clear)
        top_bar.addWidget(clear_btn)
        top_bar.addStretch()
        layout.addLayout(top_bar)

        # Console text area
        self.text_area = QTextEdit()
        self.text_area.setReadOnly(True)
        # Cap the document to N blocks (~lines). Without this, every print()
        # / yt-dlp warning / subprocess line accumulates forever and the
        # QTextEdit's repaint cost grows linearly with content. After hours
        # of use the UI thread spends seconds on each paint and the process
        # eventually OOMs. Qt's maximumBlockCount drops oldest blocks for us.
        self.text_area.document().setMaximumBlockCount(5000)
        self.text_area.setUndoRedoEnabled(False)
        self.text_area.setStyleSheet(
            "QTextEdit { background-color: #0c0c14; color: #7dd87a; "
            "font-family: 'Consolas', 'Cascadia Code', 'Courier New', monospace; font-size: 12px; "
            "border: 1px solid #2f3056; border-radius: 8px; padding: 10px; }"
        )
        layout.addWidget(self.text_area, 1)

    def install(self):
        """Redirect sys.stdout and sys.stderr to this console."""
        self._orig_stdout = sys.stdout
        self._orig_stderr = sys.stderr

        self._stdout_redirector = StreamRedirector(self._orig_stdout)
        self._stderr_redirector = StreamRedirector(self._orig_stderr)

        sys.stdout = self._stdout_redirector
        sys.stderr = self._stderr_redirector

        # Drain buffers on the main thread every 100 ms
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._flush_buffers)
        self._timer.start(100)

    def uninstall(self):
        """Restore original sys.stdout and sys.stderr."""
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        if self._orig_stdout is not None:
            sys.stdout = self._orig_stdout
        if self._orig_stderr is not None:
            sys.stderr = self._orig_stderr
        self._stdout_redirector = None
        self._stderr_redirector = None

    def append(self, text: str):
        """Public method to append text to the console (main-thread only)."""
        self._append_text(text)

    @Slot()
    def _flush_buffers(self):
        """Drain redirector buffers and append to the text widget."""
        for redir in (self._stdout_redirector, self._stderr_redirector):
            if redir is not None:
                text = redir.drain()
                if text:
                    self._append_text(text)

    def _append_text(self, text: str):
        cursor = self.text_area.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.insertText(text)
        self.text_area.setTextCursor(cursor)
        self.text_area.ensureCursorVisible()

    @Slot()
    def _clear(self):
        self.text_area.clear()
