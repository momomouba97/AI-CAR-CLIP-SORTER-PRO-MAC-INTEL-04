"""صفحات: الملفات، المشاريع، الإعدادات، السجل."""
import os
import shutil
import threading
import time
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QHBoxLayout, QFormLayout, QCheckBox, QFileDialog, QMessageBox, QInputDialog,
                               QListWidget, QTextEdit)

from .. import __version__, APP_NAME
from ..config.paths import logs_dir, default_projects_dir
from ..core import ffmpeg_util
from ..core.i18n import T
from ..core.progress import fmt_size
from ..storage import project_store as store
from .pages_a import Page, spin, combo
from .theme import C
from .widgets import card, label, button, PathRow


def dir_size(path) -> int:
    total = 0
    for root, _d, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


# ============================================================ الملفات
class FilesPage(Page):
    sizes = Signal(dict)

    KEYS = (("source", "fp_source"), ("export", "fp_export"), ("moving", "fp_moving"),
            ("stopping", "fp_stopping"), ("excluded", "fp_excluded"), ("temp", "fp_temp"))

    def __init__(self, ctx):
        super().__init__(ctx)
        self.header("nav_files", "files_sub")
        cf, cl = card()
        self.rows = {}
        for k, tk in self.KEYS:
            r = PathRow(T(tk), T("browse"), T("open_finder"))
            r.changed.connect(lambda v, k=k: self._set(k, v))
            self.rows[k] = r
            cl.addWidget(r)
        self.disk = label("", "muted")
        cl.addWidget(self.disk)
        bar = QHBoxLayout()
        bar.addWidget(button(T("refresh_sizes"), None, self.compute))
        bar.addWidget(button(T("create_folders"), None, self.create))
        bar.addStretch()
        cl.addLayout(bar)
        cl.addWidget(label(T("files_note"), "muted", True))
        self.root.addWidget(cf)
        self.root.addStretch()
        self.sizes.connect(self._show_sizes)

    def _set(self, k, v):
        setattr(self.p.paths, k, v)
        self.ctx.save()

    def refresh(self):
        if not self.p:
            return
        for k, _ in self.KEYS:
            self.rows[k].edit.setText(getattr(self.p.paths, k))

    def showEvent(self, e):
        super().showEvent(e)
        self.refresh()
        self.compute()

    def create(self):
        self.p.ensure_dirs()
        self.compute()

    def compute(self):
        paths = {k: getattr(self.p.paths, k) for k, _ in self.KEYS}

        def work():
            out = {k: (dir_size(v) if os.path.isdir(v) else -1) for k, v in paths.items()}
            self.sizes.emit(out)
        threading.Thread(target=work, daemon=True).start()

    def _show_sizes(self, d):
        for k, v in d.items():
            self.rows[k].size.setText(fmt_size(v) if v >= 0 else "—")
        try:
            u = shutil.disk_usage(self.p.root if os.path.isdir(self.p.root) else Path.home())
            self.disk.setText(T("disk_info").format(free=fmt_size(u.free), total=fmt_size(u.total)))
        except OSError:
            pass


# ============================================================ المشاريع
class ProjectsPage(Page):
    def __init__(self, ctx):
        super().__init__(ctx)
        self.header("nav_projects", "projects_sub")
        cf, cl = card()
        self.current = label("", "h2")
        cl.addWidget(self.current)
        bar = QHBoxLayout()
        for text, name, cb in ((T("new_project"), "primary", self.new), (T("open_project"), None, self.open),
                               (T("save_project"), None, self.save), (T("duplicate_project"), None, self.duplicate),
                               (T("export_settings"), None, self.export_settings), (T("import_settings"), None, self.import_settings)):
            bar.addWidget(button(text, name, cb))
        cl.addLayout(bar)
        cl.addWidget(label(T("recent_projects"), "h2"))
        self.recent = QListWidget()
        self.recent.itemDoubleClicked.connect(lambda it: self._open(it.text()))
        cl.addWidget(self.recent, 1)
        self.root.addWidget(cf, 1)
        self.refresh()

    def refresh(self):
        if not self.p:
            return
        self.current.setText(f"{self.p.name}  —  {self.p.root}")
        self.recent.clear()
        for r in self.ctx.settings.recent:
            self.recent.addItem(r)

    def _open(self, path):
        try:
            self.ctx.save()
            self.ctx.open_project(path)
        except Exception as e:
            QMessageBox.warning(self, T("open_project"), str(e))

    def new(self):
        name, ok = QInputDialog.getText(self, T("new_project"), T("project_name"))
        if not (ok and name.strip()):
            return
        parent = QFileDialog.getExistingDirectory(self, T("choose_location"), str(default_projects_dir().parent))
        if not parent:
            return
        try:
            self.ctx.save()
            self.ctx.new_project(name.strip(), parent)
        except FileExistsError:
            QMessageBox.warning(self, T("new_project"), T("project_exists"))

    def open(self):
        d = QFileDialog.getExistingDirectory(self, T("open_project"), str(default_projects_dir().parent))
        if d:
            self._open(d)

    def save(self):
        self.ctx.save()
        self.ctx.log(T("project_saved"), "success")

    def duplicate(self):
        name, ok = QInputDialog.getText(self, T("duplicate_project"), T("project_name"), text=self.p.name + " copy")
        if not (ok and name.strip()):
            return
        try:
            self.ctx.save()
            self.ctx.set_project(store.duplicate_project(self.p, name.strip(), Path(self.p.root).parent))
        except FileExistsError:
            QMessageBox.warning(self, T("duplicate_project"), T("project_exists"))

    def export_settings(self):
        f, _ = QFileDialog.getSaveFileName(self, T("export_settings"), f"{self.p.name}_settings.json", "JSON (*.json)")
        if f:
            store.export_settings(self.p, f)

    def import_settings(self):
        f, _ = QFileDialog.getOpenFileName(self, T("import_settings"), "", "JSON (*.json)")
        if f:
            store.import_settings(self.p, f)
            self.ctx.projectChanged.emit()


# ============================================================ الإعدادات
class SettingsPage(Page):
    def __init__(self, ctx):
        super().__init__(ctx)
        self.header("nav_settings")
        cf, cl = card()
        form = QFormLayout()
        self.lang = combo([("العربية", "ar"), ("English", "en")], ctx.settings.language)
        self.lang.currentIndexChanged.connect(lambda: self.ctx.set_language(self.lang.currentData()))
        form.addRow(T("language"), self.lang)
        self.copy = QCheckBox(T("copy_instead"))
        self.assist = QCheckBox(T("assist_on"))
        self.moving = spin(0.001, 1, 0.04, 0.005, 3)
        self.stopping = spin(0.0, 1, 0.005, 0.001, 3)
        self.minconf = spin(0.5, 1, 0.75, 0.05, 2)
        form.addRow("", self.copy)
        form.addRow("", self.assist)
        form.addRow(T("moving_thr"), self.moving)
        form.addRow(T("stopping_thr"), self.stopping)
        form.addRow(T("min_conf"), self.minconf)
        cl.addLayout(form)
        cl.addWidget(label(T("assist_note"), "muted", True))
        for w, a in ((self.copy, "copy_instead_of_move"), (self.assist, "assist")):
            w.toggled.connect(lambda v, a=a: self._set(a, v))
        for w, a in ((self.moving, "moving_thr"), (self.stopping, "stopping_thr"), (self.minconf, "assist_min_conf")):
            w.valueChanged.connect(lambda v, a=a: self._set(a, v))
        self.sys = label("", "muted", True)
        cl.addWidget(self.sys)
        bar = QHBoxLayout()
        bar.addWidget(button(T("open_logs"), None, lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(logs_dir())))))
        bar.addStretch()
        cl.addLayout(bar)
        self.root.addWidget(cf)
        self.root.addStretch()
        self._loading = False
        self.refresh()

    def _set(self, a, v):
        if not self._loading and self.p:
            setattr(self.p.sort, a, v)

    def refresh(self):
        if not self.p:
            return
        self._loading = True
        s = self.p.sort
        self.copy.setChecked(s.copy_instead_of_move)
        self.assist.setChecked(s.assist)
        self.moving.setValue(s.moving_thr)
        self.stopping.setValue(s.stopping_thr)
        self.minconf.setValue(s.assist_min_conf)
        self._loading = False
        try:
            ff = ffmpeg_util.find_ffmpeg()
            ver = ffmpeg_util.ffmpeg_version(ff)
        except Exception as e:
            ver = f"FFmpeg: {e}"
        self.sys.setText(f"{APP_NAME} v{__version__}\n{ver}\nKeychain: {self.ctx.secrets.backend_name()}")


# ============================================================ السجل
class LogPage(Page):
    COLORS = {"info": C["text"], "success": C["success"], "warning": C["warning"], "error": C["error"]}

    def __init__(self, ctx):
        super().__init__(ctx)
        self.header("nav_log")
        self.view = QTextEdit()
        self.view.setReadOnly(True)
        self.root.addWidget(self.view, 1)
        bar = QHBoxLayout()
        bar.addWidget(button(T("clear"), None, self.view.clear))
        bar.addStretch()
        self.root.addLayout(bar)
        ctx.logAdded.connect(self.add)

    def add(self, level, msg):
        col = self.COLORS.get(level, C["text"])
        esc = msg.replace("&", "&amp;").replace("<", "&lt;")
        self.view.append(f'<span style="color:{C["muted"]}">[{time.strftime("%H:%M:%S")}]</span> '
                         f'<span style="color:{col}">{esc}</span>')
