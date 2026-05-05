"""Vector icon set rendered via QPainter paths.

Each factory returns a QIcon that renders crisply at any size. No external
asset files required — everything is drawn programmatically.
"""

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)


_DEFAULT_COLOR = "#f0f0f5"


def _pixmap(size: int, color: str, draw) -> QPixmap:
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.SmoothPixmapTransform, True)
    qc = QColor(color)
    draw(p, size, qc)
    p.end()
    return pix


def _make(draw, color: str = _DEFAULT_COLOR, size: int = 28) -> QIcon:
    return QIcon(_pixmap(size, color, draw))


# ---------- Primitives ----------

def _fill(p: QPainter, color: QColor) -> None:
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(color))


def _stroke(p: QPainter, color: QColor, width: float = 2.0) -> None:
    pen = QPen(color)
    pen.setWidthF(width)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)


# ---------- Icons ----------

def play(color: str = _DEFAULT_COLOR, size: int = 28) -> QIcon:
    def draw(p, s, c):
        _fill(p, c)
        path = QPainterPath()
        # Right-pointing triangle, slightly padded from edges
        path.moveTo(s * 0.30, s * 0.20)
        path.lineTo(s * 0.80, s * 0.50)
        path.lineTo(s * 0.30, s * 0.80)
        path.closeSubpath()
        p.drawPath(path)
    return _make(draw, color, size)


def pause(color: str = _DEFAULT_COLOR, size: int = 28) -> QIcon:
    def draw(p, s, c):
        _fill(p, c)
        w = s * 0.14
        h = s * 0.55
        y = (s - h) / 2
        p.drawRoundedRect(QRectF(s * 0.30, y, w, h), 1.5, 1.5)
        p.drawRoundedRect(QRectF(s * 0.56, y, w, h), 1.5, 1.5)
    return _make(draw, color, size)


def stop(color: str = _DEFAULT_COLOR, size: int = 28) -> QIcon:
    def draw(p, s, c):
        _fill(p, c)
        side = s * 0.50
        off = (s - side) / 2
        p.drawRoundedRect(QRectF(off, off, side, side), 2, 2)
    return _make(draw, color, size)


def prev_track(color: str = _DEFAULT_COLOR, size: int = 28) -> QIcon:
    def draw(p, s, c):
        _fill(p, c)
        # Vertical bar on the left
        bar_w = s * 0.10
        bar_h = s * 0.55
        bar_y = (s - bar_h) / 2
        p.drawRoundedRect(QRectF(s * 0.22, bar_y, bar_w, bar_h), 1.5, 1.5)
        # Left-pointing triangle
        path = QPainterPath()
        path.moveTo(s * 0.78, bar_y)
        path.lineTo(s * 0.36, s / 2)
        path.lineTo(s * 0.78, bar_y + bar_h)
        path.closeSubpath()
        p.drawPath(path)
    return _make(draw, color, size)


def next_track(color: str = _DEFAULT_COLOR, size: int = 28) -> QIcon:
    def draw(p, s, c):
        _fill(p, c)
        bar_w = s * 0.10
        bar_h = s * 0.55
        bar_y = (s - bar_h) / 2
        p.drawRoundedRect(QRectF(s * 0.68, bar_y, bar_w, bar_h), 1.5, 1.5)
        path = QPainterPath()
        path.moveTo(s * 0.22, bar_y)
        path.lineTo(s * 0.64, s / 2)
        path.lineTo(s * 0.22, bar_y + bar_h)
        path.closeSubpath()
        p.drawPath(path)
    return _make(draw, color, size)


def rewind_10(color: str = _DEFAULT_COLOR, size: int = 28) -> QIcon:
    def draw(p, s, c):
        _fill(p, c)
        # Double left triangle (rewind)
        y_top = s * 0.25
        y_bot = s * 0.75
        y_mid = s * 0.50
        path = QPainterPath()
        path.moveTo(s * 0.50, y_top)
        path.lineTo(s * 0.18, y_mid)
        path.lineTo(s * 0.50, y_bot)
        path.closeSubpath()
        p.drawPath(path)
        path2 = QPainterPath()
        path2.moveTo(s * 0.82, y_top)
        path2.lineTo(s * 0.50, y_mid)
        path2.lineTo(s * 0.82, y_bot)
        path2.closeSubpath()
        p.drawPath(path2)
    return _make(draw, color, size)


def forward_10(color: str = _DEFAULT_COLOR, size: int = 28) -> QIcon:
    def draw(p, s, c):
        _fill(p, c)
        y_top = s * 0.25
        y_bot = s * 0.75
        y_mid = s * 0.50
        path = QPainterPath()
        path.moveTo(s * 0.18, y_top)
        path.lineTo(s * 0.50, y_mid)
        path.lineTo(s * 0.18, y_bot)
        path.closeSubpath()
        p.drawPath(path)
        path2 = QPainterPath()
        path2.moveTo(s * 0.50, y_top)
        path2.lineTo(s * 0.82, y_mid)
        path2.lineTo(s * 0.50, y_bot)
        path2.closeSubpath()
        p.drawPath(path2)
    return _make(draw, color, size)


def star(color: str = _DEFAULT_COLOR, size: int = 28) -> QIcon:
    def draw(p, s, c):
        _fill(p, c)
        import math
        cx, cy = s / 2, s / 2
        outer = s * 0.40
        inner = s * 0.17
        path = QPainterPath()
        for i in range(10):
            angle = math.pi / 2 - (math.pi / 5) * i
            r = outer if i % 2 == 0 else inner
            x = cx + r * math.cos(angle)
            y = cy - r * math.sin(angle)
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)
        path.closeSubpath()
        p.drawPath(path)
    return _make(draw, color, size)


def fullscreen(color: str = _DEFAULT_COLOR, size: int = 28) -> QIcon:
    def draw(p, s, c):
        _stroke(p, c, s * 0.09)
        m = s * 0.20  # margin
        arm = s * 0.18
        # Top-left corner
        p.drawLine(QPointF(m, m + arm), QPointF(m, m))
        p.drawLine(QPointF(m, m), QPointF(m + arm, m))
        # Top-right
        p.drawLine(QPointF(s - m - arm, m), QPointF(s - m, m))
        p.drawLine(QPointF(s - m, m), QPointF(s - m, m + arm))
        # Bottom-left
        p.drawLine(QPointF(m, s - m - arm), QPointF(m, s - m))
        p.drawLine(QPointF(m, s - m), QPointF(m + arm, s - m))
        # Bottom-right
        p.drawLine(QPointF(s - m, s - m - arm), QPointF(s - m, s - m))
        p.drawLine(QPointF(s - m, s - m), QPointF(s - m - arm, s - m))
    return _make(draw, color, size)


def shuffle(color: str = _DEFAULT_COLOR, size: int = 28) -> QIcon:
    def draw(p, s, c):
        _stroke(p, c, s * 0.07)
        # Two arrows crossing (classic shuffle glyph)
        # Arrow 1: top-left to bottom-right with curve
        path1 = QPainterPath()
        path1.moveTo(s * 0.15, s * 0.30)
        path1.cubicTo(
            s * 0.40, s * 0.30,
            s * 0.45, s * 0.70,
            s * 0.78, s * 0.70,
        )
        p.drawPath(path1)
        # Arrow head at end of path1
        _fill(p, c)
        path1_head = QPainterPath()
        path1_head.moveTo(s * 0.78, s * 0.70)
        path1_head.lineTo(s * 0.70, s * 0.64)
        path1_head.lineTo(s * 0.70, s * 0.76)
        path1_head.closeSubpath()
        # extend to form arrowhead
        path1_head = QPainterPath()
        path1_head.moveTo(s * 0.88, s * 0.70)
        path1_head.lineTo(s * 0.73, s * 0.63)
        path1_head.lineTo(s * 0.73, s * 0.77)
        path1_head.closeSubpath()
        p.drawPath(path1_head)

        # Arrow 2: bottom-left to top-right with curve
        _stroke(p, c, s * 0.07)
        path2 = QPainterPath()
        path2.moveTo(s * 0.15, s * 0.70)
        path2.cubicTo(
            s * 0.40, s * 0.70,
            s * 0.45, s * 0.30,
            s * 0.78, s * 0.30,
        )
        p.drawPath(path2)
        _fill(p, c)
        path2_head = QPainterPath()
        path2_head.moveTo(s * 0.88, s * 0.30)
        path2_head.lineTo(s * 0.73, s * 0.23)
        path2_head.lineTo(s * 0.73, s * 0.37)
        path2_head.closeSubpath()
        p.drawPath(path2_head)
    return _make(draw, color, size)


def repeat(color: str = _DEFAULT_COLOR, size: int = 28) -> QIcon:
    def draw(p, s, c):
        _stroke(p, c, s * 0.07)
        # Circular arrow — arc with arrowheads
        rect = QRectF(s * 0.18, s * 0.18, s * 0.64, s * 0.64)
        # Top arc (left to right)
        p.drawArc(rect, 40 * 16, 130 * 16)
        # Bottom arc
        p.drawArc(rect, 220 * 16, 130 * 16)
        # Arrowheads
        _fill(p, c)
        # Right arrowhead (end of top arc)
        ah1 = QPainterPath()
        ah1.moveTo(s * 0.82, s * 0.42)
        ah1.lineTo(s * 0.70, s * 0.35)
        ah1.lineTo(s * 0.76, s * 0.50)
        ah1.closeSubpath()
        p.drawPath(ah1)
        # Left arrowhead (end of bottom arc)
        ah2 = QPainterPath()
        ah2.moveTo(s * 0.18, s * 0.58)
        ah2.lineTo(s * 0.30, s * 0.65)
        ah2.lineTo(s * 0.24, s * 0.50)
        ah2.closeSubpath()
        p.drawPath(ah2)
    return _make(draw, color, size)


def repeat_one(color: str = _DEFAULT_COLOR, size: int = 28) -> QIcon:
    def draw(p, s, c):
        repeat_icon = repeat(color, size).pixmap(size, size)
        p.drawPixmap(0, 0, repeat_icon)
        _fill(p, c)
        f = QFont()
        f.setBold(True)
        f.setPointSizeF(s * 0.30)
        p.setFont(f)
        p.setPen(c)
        p.drawText(QRectF(0, 0, s, s), Qt.AlignCenter, "1")
    return _make(draw, color, size)


def volume(color: str = _DEFAULT_COLOR, size: int = 28) -> QIcon:
    def draw(p, s, c):
        _fill(p, c)
        # Speaker body — trapezoid with rectangular back
        path = QPainterPath()
        path.moveTo(s * 0.18, s * 0.38)
        path.lineTo(s * 0.18, s * 0.62)
        path.lineTo(s * 0.32, s * 0.62)
        path.lineTo(s * 0.48, s * 0.82)
        path.lineTo(s * 0.48, s * 0.18)
        path.lineTo(s * 0.32, s * 0.38)
        path.closeSubpath()
        p.drawPath(path)
        # Sound waves
        _stroke(p, c, s * 0.06)
        p.drawArc(QRectF(s * 0.50, s * 0.32, s * 0.18, s * 0.36), -60 * 16, 120 * 16)
        p.drawArc(QRectF(s * 0.58, s * 0.22, s * 0.28, s * 0.56), -60 * 16, 120 * 16)
    return _make(draw, color, size)


def music_note(color: str = _DEFAULT_COLOR, size: int = 28) -> QIcon:
    """Eighth note glyph."""
    def draw(p, s, c):
        _fill(p, c)
        # Note head (ellipse)
        p.drawEllipse(QRectF(s * 0.18, s * 0.60, s * 0.26, s * 0.20))
        # Stem
        p.drawRoundedRect(
            QRectF(s * 0.42, s * 0.18, s * 0.06, s * 0.52), 1, 1
        )
        # Flag
        path = QPainterPath()
        path.moveTo(s * 0.48, s * 0.18)
        path.cubicTo(
            s * 0.78, s * 0.28,
            s * 0.80, s * 0.48,
            s * 0.58, s * 0.52,
        )
        path.lineTo(s * 0.58, s * 0.40)
        path.cubicTo(
            s * 0.74, s * 0.38,
            s * 0.66, s * 0.30,
            s * 0.48, s * 0.28,
        )
        path.closeSubpath()
        p.drawPath(path)
    return _make(draw, color, size)


def check(color: str = _DEFAULT_COLOR, size: int = 28) -> QIcon:
    """Checkmark."""
    def draw(p, s, c):
        _stroke(p, c, s * 0.14)
        path = QPainterPath()
        path.moveTo(s * 0.22, s * 0.52)
        path.lineTo(s * 0.42, s * 0.72)
        path.lineTo(s * 0.78, s * 0.30)
        p.drawPath(path)
    return _make(draw, color, size)


def circle_dot(color: str = _DEFAULT_COLOR, size: int = 28, filled: bool = False) -> QIcon:
    """Empty circle (filled=False) or filled dot."""
    def draw(p, s, c):
        if filled:
            _fill(p, c)
        else:
            _stroke(p, c, s * 0.14)
        p.drawEllipse(QRectF(s * 0.25, s * 0.25, s * 0.50, s * 0.50))
    return _make(draw, color, size)


def bookmarks_menu(color: str = _DEFAULT_COLOR, size: int = 28) -> QIcon:
    """Star in a filled rounded box — signals 'bookmarks menu'."""
    def draw(p, s, c):
        import math
        # Star only (simpler, clearer)
        _fill(p, c)
        cx, cy = s / 2, s / 2
        outer = s * 0.38
        inner = s * 0.16
        path = QPainterPath()
        for i in range(10):
            angle = math.pi / 2 - (math.pi / 5) * i
            r = outer if i % 2 == 0 else inner
            x = cx + r * math.cos(angle)
            y = cy - r * math.sin(angle)
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)
        path.closeSubpath()
        p.drawPath(path)
    return _make(draw, color, size)
