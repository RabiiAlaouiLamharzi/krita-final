"""Shared hand-painted controls for gateway and survey windows."""

from PyQt5.QtCore import Qt, QPointF
from PyQt5.QtGui import QPainter, QPen, QColor
from PyQt5.QtWidgets import QAbstractButton


class WhiteDotToggle(QAbstractButton):
    """Circle with white outline; white dot when checked."""

    OUTER_R = 6.0
    INNER_R = 3.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setFixedSize(18, 18)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        cx = self.width() / 2.0
        cy = self.height() / 2.0
        p.setPen(QPen(QColor("#ffffff"), 1))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(cx, cy), self.OUTER_R, self.OUTER_R)
        if self.isChecked():
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#ffffff"))
            p.drawEllipse(QPointF(cx, cy), self.INNER_R, self.INNER_R)
        p.end()

    def sizeHint(self):
        return self.minimumSizeHint()
