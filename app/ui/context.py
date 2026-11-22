"""سياق التطبيق المشترك بين الصفحات: المشروع، المهام الخلفية، السجل، التقدم."""
import logging
import traceback

from PySide6.QtCore import QObject, QThread, Signal, QTimer

from ..config.schema import AppSettings
from ..config.settings import save_settings
from ..core import ffmpeg_util
from ..core.hooks import Hooks, Cancelled
from ..core.i18n import T
from ..core.project import Project
from ..exporter import exporter
from ..security.keychain import SecretStore
from ..storage import project_store as store
from ..uploader import manager as upl
from ..uploader.youtube import YouTubePlatform

log = logging.getLogger("aiccs")


class Worker(QThread):
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, fn, hooks):
        super().__init__()
        self.fn, self.hooks = fn, hooks

    def run(self):
        try:
            self.done.emit(self.fn(self.hooks))
        except Cancelled:
            self.failed.emit("__cancelled__")
        except Exception as e:
            log.error("Task failed:\n%s", traceback.format_exc())
            self.failed.emit(str(e) or e.__class__.__name__)


class Ctx(QObject):
    projectChanged = Signal()
    statsChanged = Signal()
    logAdded = Signal(str, str)
    progressChanged = Signal(str, float, str)
    busyChanged = Signal(bool)
    languageChanged = Signal()

    def __init__(self, settings: AppSettings):
        super().__init__()
        self.settings = settings
        self.project: Project | None = None
        self.secrets = SecretStore()
        self.platform = YouTubePlatform(self.secrets)
        self.busy = False
        self.hooks: Hooks | None = None
        self._worker = None
        self.logAdded.connect(self._record)
        self.autosave = QTimer(self)
        self.autosave.timeout.connect(self.save)
        self.autosave.start(30000)

    # ---------- المشروع ----------
    @property
    def ffmpeg(self) -> str:
        return ffmpeg_util.find_ffmpeg()

    def save(self):
        if self.project:
            try:
                store.save_project(self.project)
            except Exception as e:
                log.error("Save failed: %s", e)

    def set_project(self, p: Project):
        self.project = p
        p.ensure_dirs()
        exporter.cleanup_partials(p)
        s = self.settings
        s.last_project = p.root
        s.recent = [p.root] + [r for r in s.recent if r != p.root][:9]
        save_settings(s)
        self.projectChanged.emit()
        self.statsChanged.emit()

    def open_project(self, path):
        self.set_project(store.load_project(path))

    def new_project(self, name, parent):
        self.set_project(store.create_project(name, parent))

    def set_language(self, lang):
        self.settings.language = lang
        save_settings(self.settings)
        self.languageChanged.emit()

    # ---------- السجل ----------
    def log(self, msg, level="info"):
        self.logAdded.emit(level, msg)

    def _record(self, level, msg):
        getattr(log, {"error": "error", "warning": "warning"}.get(level, "info"))(msg)
        if self.project:
            self.project.log_event(level, msg)

    # ---------- المهام الخلفية ----------
    def run_task(self, name, fn, on_done=None, on_fail=None):
        if self.busy:
            self.log(T("busy_msg"), "warning")
            return False
        hooks = Hooks(log=lambda l, m: self.logAdded.emit(l, m),
                      progress=lambda t, f, d: self.progressChanged.emit(t, -1.0 if f is None else float(f), d))
        w = Worker(fn, hooks)
        self.hooks, self._worker, self.busy = hooks, w, True
        self.busyChanged.emit(True)
        self.log(f"▶ {name}")

        def finish():
            self.busy = False
            self.busyChanged.emit(False)
            self.progressChanged.emit("idle", 0.0, "")
            self.save()
            self.statsChanged.emit()

        def ok(res):
            finish()
            if on_done:
                on_done(res)

        def bad(msg):
            finish()
            if msg == "__cancelled__":
                self.log(T("cancelled"), "warning")
            else:
                self.log(f"{name}: {msg}", "error")
            if on_fail:
                on_fail(msg)
        w.done.connect(ok)
        w.failed.connect(bad)
        w.start()
        return True

    def cancel(self):
        if self.hooks:
            self.hooks.cancel.set()

    def toggle_pause(self):
        if self.hooks:
            if self.hooks.paused.is_set():
                self.hooks.paused.clear()
            else:
                self.hooks.paused.set()
            return self.hooks.paused.is_set()
        return False

    # ---------- عمليات مركبة (تُستخدم من عدة صفحات) ----------
    def export_pending(self, then=None):
        p = self.project
        clips = [c for c in p.clips if not c.exported]
        if not clips:
            self.log(T("nothing_to_export"), "warning")
            return False

        def fn(h):
            return exporter.export_clips(self.ffmpeg, p, clips, h, self.save)

        def done(r):
            self.log(T("export_done").format(done=r["done"], failed=r["failed"]), "success" if not r["failed"] else "warning")
            if then:
                then()
        return self.run_task(T("export"), fn, done)

    def upload_clips(self, clips, then=None):
        p = self.project
        try:
            upl.assert_allowed(p, self.platform)
        except Exception as e:
            self.log(f"{T('upload_blocked')}: {e}", "warning")
            return False

        def fn(h):
            return upl.run_uploads(p, self.platform, clips, h, self.save)

        def done(r):
            self.log(T("upload_done").format(ok=r["ok"], failed=r["failed"]), "success" if not r["failed"] else "warning")
            if then:
                then()
        return self.run_task(T("upload"), fn, done)

    def after_analysis(self):
        """التصدير التلقائي ثم الرفع التلقائي بعد التحليل، حسب إعدادات المستخدم."""
        p = self.project
        if not p.export.auto_export:
            return

        def maybe_upload():
            if p.upload.enabled and p.upload.consent and p.upload.after_export:
                self.upload_clips(upl.select_clips(p))
        self.export_pending(then=maybe_upload)
