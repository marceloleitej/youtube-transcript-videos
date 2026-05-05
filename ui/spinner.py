"""Lightweight animated spinner widget for loading states."""

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget


class Spinner(QWidget):
    """Simple circular spinner with 8 ticks fading around.

    Usage: spinner.start() / spinner.stop(). Auto-hides when stopped.
    """

    def __init__(self, color: str = "#e94560", size: int = 24, parent=None):
        super().__init__(parent)
        self._color = QColor(color)
        self._size = size
        self.setFixedSize(size, size)
        self._angle = 0
        self._timer = QTimer(self)
        self._timer.setInterval(80)
        self._timer.timeout.connect(self._tick)
        self.setVisible(False)

    def start(self):
        self.setVisible(True)
        self._timer.start()

    def stop(self):
        self._timer.stop()
        self.setVisible(False)

    def _tick(self):
        self._angle = (self._angle + 45) % 360
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        s = min(self.width(), self.height())
        cx, cy = s / 2, s / 2
        r_outer = s * 0.42
        r_inner = s * 0.22
        tick_w = max(2.0, s * 0.10)

        from math import pi, cos, sin
        for i in range(8):
            angle_deg = self._angle + i * 45
            angle = angle_deg * pi / 180
            alpha = int(255 * (i / 8.0) ** 1.5) + 30
            alpha = min(255, alpha)
            color = QColor(self._color)
            color.setAlpha(alpha)
            pen = QPen(color)
            pen.setWidthF(tick_w)
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            x1 = cx + r_inner * cos(angle)
            y1 = cy + r_inner * sin(angle)
            x2 = cx + r_outer * cos(angle)
            y2 = cy + r_outer * sin(angle)
            p.drawLine(int(x1), int(y1), int(x2), int(y2))
        p.end()
