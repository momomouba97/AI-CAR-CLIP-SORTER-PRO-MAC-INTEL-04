from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import (QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QStackedWidget, QButtonGroup,
                               QProgressBar, QPushButton)

from .. import APP_SHORT, __version__
from ..core.i18n import T
from .pages_a import DashboardPage, ImportPage, ScenesPage, ExportPage
from .pages_b import SorterPage, UploadPage, WorkflowPage
from .pages_c import FilesPage, ProjectsPage, SettingsPage, LogPage
from .theme import icon, C
from .widgets import label, button

NAV = [("dashboard", DashboardPage), ("import", ImportPage), ("scenes", ScenesPage), ("export", ExportPage),
       ("sorter", SorterPage), ("upload", UploadPage), ("workflow", WorkflowPage), ("files", FilesPage),
       ("projects", ProjectsPage), ("log", LogPage), ("settings", SettingsPage)]


class MainWindow(QMainWindow):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.setWindowTitle(f"{APP_SHORT} ULTIMATE")
        self.resize(1280, 820)
        self.setMinimumSize(980, 640)
        central = QWidget()
        self.setCentralWidget(central)
        outer = QHBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        side = QWidget()
        side.setObjectName("sidebar")
        side.setFixedWidth(220)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(12, 16, 12, 12)
        sl.setSpacing(4)
        sl.addWidget(label("🚗 " + APP_SHORT, "h2"))
        sl.addWidget(label(f"ULTIMATE v{__version__}", "muted"))
        sl.addSpacing(12)
        self.stack = QStackedWidget()
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.pages = {}
        for i, (key, cls) in enumerate(NAV):
            page = cls(ctx)
            self.pages[key] = page
            self.stack.addWidget(page)
            b = QPushButton("  " + T("nav_" + key))
            b.setObjectName("nav")
            b.setCheckable(True)
            b.setIcon(icon(key, C["muted"]))
            b.setIconSize(QSize(20, 20))
            b.setCursor(Qt.PointingHandCursor)
            b.toggled.connect(lambda on, b=b, k=key: b.setIcon(icon(k, "#ffffff" if on else C["muted"])))
            b.clicked.connect(lambda _=False, i=i: self.stack.setCurrentIndex(i))
            self.group.addButton(b)
            sl.addWidget(b)
            if i == 0:
                b.setChecked(True)
        sl.addStretch()
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)
        rl.addWidget(self.stack, 1)
        bar = QWidget()
        bar.setStyleSheet(f"background:{C['sidebar']};")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(16, 8, 16, 8)
        self.task = label(T("idle"), "muted")
        self.task.setMinimumWidth(110)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setTextVisible(False)
        self.detail = label("", "muted")
        self.pause = button(T("pause"), None, self._pause)
        self.cancel = button(T("cancel"), "danger", ctx.cancel)
        for w, s in ((self.task, 0), (self.bar, 3), (self.detail, 3), (self.pause, 0), (self.cancel, 0)):
            bl.addWidget(w, s)
        rl.addWidget(bar)
        outer.addWidget(side)
        outer.addWidget(right, 1)
        ctx.progressChanged.connect(self._progress)
        ctx.busyChanged.connect(self._busy)
        self._busy(False)
        for p in self.pages.values():
            p.refresh()

    def _pause(self):
        self.pause.setText(T("resume") if self.ctx.toggle_pause() else T("pause"))

    def _busy(self, busy):
        self.pause.setEnabled(busy)
        self.cancel.setEnabled(busy)
        if not busy:
            self.bar.setRange(0, 1000)
            self.bar.setValue(0)
            self.task.setText(T("idle"))
            self.detail.setText("")
            self.pause.setText(T("pause"))

    def _progress(self, task, frac, detail):
        if task == "idle":
            return
        self.task.setText(Tx_task(task))
        if frac < 0:                       # لا نسبة دقيقة ⇒ شريط متحرك (لا نعرض نسبة وهمية)
            self.bar.setRange(0, 0)
        else:
            self.bar.setRange(0, 1000)
            self.bar.setValue(int(frac * 1000))
        self.detail.setText(detail)

    def closeEvent(self, e):
        self.ctx.save()
        super().closeEvent(e)


def Tx_task(task):
    from ..core.i18n import Tx
    return Tx("task_" + task, task)
