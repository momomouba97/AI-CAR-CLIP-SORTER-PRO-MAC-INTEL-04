from PySide6.QtCore import Qt, QRectF, Signal
from PySide6.QtGui import QPainter, QColor, QPen, QFont
from PySide6.QtWidgets import (QFrame, QLabel, QVBoxLayout, QHBoxLayout, QWidget, QPushButton, QLineEdit,
                               QFileDialog, QTableWidget, QAbstractItemView, QHeaderView, QSizePolicy)

from .theme import C


def card(layout_cls=QVBoxLayout, margins=16, spacing=10):
    f = QFrame()
    f.setObjectName("card")
    lay = layout_cls(f)
    lay.setContentsMargins(margins, margins, margins, margins)
    lay.setSpacing(spacing)
    return f, lay


def label(text="", name=None, wrap=False):
    l = QLabel(text)
    if name:
        l.setObjectName(name)
    l.setWordWrap(wrap)
    return l


def button(text, name=None, cb=None, enabled=True):
    b = QPushButton(text)
    if name:
        b.setObjectName(name)
    if cb:
        b.clicked.connect(cb)
    b.setEnabled(enabled)
    b.setCursor(Qt.PointingHandCursor)
    return b


def make_table(headers, stretch_col=0, select_rows=True, multi=True):
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.verticalHeader().setVisible(False)
    t.setAlternatingRowColors(True)
    t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    if select_rows:
        t.setSelectionBehavior(QAbstractItemView.SelectRows)
    t.setSelectionMode(QAbstractItemView.ExtendedSelection if multi else QAbstractItemView.SingleSelection)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
    t.horizontalHeader().setSectionResizeMode(stretch_col, QHeaderView.Stretch)
    t.setShowGrid(False)
    return t


class StatCard(QFrame):
    def __init__(self, title, color=C["primary"]):
        super().__init__()
        self.setObjectName("card")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(2)
        self.title = label(title, "muted")
        self.value = label("0", "statValue")
        self.value.setStyleSheet(f"color:{color};")
        lay.addWidget(self.title)
        lay.addWidget(self.value)

    def set(self, v):
        self.value.setText(str(v))

    def set_title(self, t):
        self.title.setText(t)


class BarChart(QWidget):
    """رسم بياني أعمدة متعدد السلاسل (بدون أي مكتبة خارجية)."""

    def __init__(self):
        super().__init__()
        self.labels, self.series, self.colors, self.names = [], {}, {}, {}
        self.setMinimumHeight(190)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_data(self, labels, series, colors, names):
        self.labels, self.series, self.colors, self.names = labels, series, colors, names
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        left, bottom, top = 30, 24, 22
        keys = list(self.series)
        maxv = max([max(v) if v else 0 for v in self.series.values()] + [1])
        p.setPen(QPen(QColor(C["border"]), 1))
        for i in range(5):
            y = top + (h - top - bottom) * i / 4
            p.drawLine(left, int(y), w - 6, int(y))
        p.setPen(QColor(C["muted"]))
        f = QFont(self.font())
        f.setPointSize(9)
        p.setFont(f)
        p.drawText(0, top - 6, str(maxv))
        n = max(1, len(self.labels))
        slot = (w - left - 6) / n
        bw = max(3.0, min(18.0, slot / (len(keys) + 1)))
        for i, lab in enumerate(self.labels):
            x0 = left + slot * i + (slot - bw * len(keys)) / 2
            for j, k in enumerate(keys):
                v = self.series[k][i]
                bh = (h - top - bottom) * v / maxv
                p.setBrush(QColor(self.colors.get(k, C["primary"])))
                p.setPen(Qt.NoPen)
                p.drawRoundedRect(QRectF(x0 + j * bw, h - bottom - bh, bw - 1, bh), 2, 2)
            p.setPen(QColor(C["muted"]))
            p.drawText(QRectF(left + slot * i, h - bottom + 3, slot, 16), Qt.AlignCenter, lab)
        # مفتاح الألوان
        x = left
        for k in keys:
            p.setBrush(QColor(self.colors.get(k, C["primary"])))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(QRectF(x, 4, 10, 10), 2, 2)
            p.setPen(QColor(C["muted"]))
            name = self.names.get(k, k)
            p.drawText(QRectF(x + 14, 0, 110, 18), Qt.AlignVCenter | Qt.AlignLeft, name)
            x += 120


class PathRow(QWidget):
    changed = Signal(str)

    def __init__(self, title, browse_text, open_text):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.title = label(title)
        self.title.setMinimumWidth(150)
        self.edit = QLineEdit()
        self.edit.editingFinished.connect(lambda: self.changed.emit(self.edit.text()))
        self.size = label("", "muted")
        self.size.setMinimumWidth(80)
        self.b1 = button(browse_text, cb=self._browse)
        self.b2 = button(open_text, cb=self._open)
        for w in (self.title, self.edit, self.size, self.b1, self.b2):
            lay.addWidget(w)
        lay.setStretch(1, 1)

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "", self.edit.text())
        if d:
            self.edit.setText(d)
            self.changed.emit(d)

    def _open(self):
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        import os
        os.makedirs(self.edit.text(), exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(self.edit.text()))   # يفتح في Finder على macOS
