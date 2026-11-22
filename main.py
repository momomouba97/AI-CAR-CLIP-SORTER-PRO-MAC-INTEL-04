import logging
import logging.handlers
import os
import sys
import tempfile
import traceback
from pathlib import Path

from app import APP_SHORT, __version__


def setup_logging():
    from app.config.paths import logs_dir
    h = logging.handlers.RotatingFileHandler(logs_dir() / "app.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(h)
    sys.excepthook = lambda t, v, tb: logging.getLogger("aiccs").error("Unhandled:\n%s", "".join(traceback.format_exception(t, v, tb)))


def selftest() -> int:
    """فحص ذاتي للحزمة: يعمل داخل ملف .app نفسه في GitHub Actions."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from app.core import ffmpeg_util
    from app.core.hooks import Hooks
    from app.core.project import Project, VideoRec
    from app.config.schema import SortCfg
    from app.exporter import exporter
    from app.sorter import assist
    from app.splitter import splitter
    from app.video import info
    import subprocess
    steps = []

    def ok(name):
        steps.append(name)
        print(f"[selftest] OK  {name}", flush=True)
    ff = ffmpeg_util.find_ffmpeg()
    ok("ffmpeg: " + ffmpeg_util.ffmpeg_version(ff))
    if "libx264" not in ffmpeg_util.available_encoders(ff):
        print("[selftest] FAIL libx264 missing")
        return 1
    ok("libx264 encoder")
    tmp = Path(tempfile.mkdtemp(prefix="aiccs_selftest_"))
    os.environ["AICCS_HOME"] = str(tmp / "home")
    ins, n = [], 0
    for c in ("red", "blue"):
        ins += ["-f", "lavfi", "-t", "2", "-i", f"color=c={c}:s=320x240:r=25"]
    src = tmp / "src.mp4"
    subprocess.run([ff, "-y", "-loglevel", "error", *ins, "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0[v]",
                    "-map", "[v]", "-pix_fmt", "yuv420p", "-c:v", "libx264", str(src)], check=True)
    meta = info.probe(str(src))
    ok(f"opencv probe ({meta['duration']:.1f}s)")
    p = Project("selftest", str(tmp / "proj"))
    p.ensure_dirs()
    v = VideoRec(str(src), **meta)
    p.add_video(v)
    segs = splitter.analyze_video(v, p.analysis, Hooks())
    if len(segs) != 2:
        print(f"[selftest] FAIL expected 2 scenes, got {len(segs)}")
        return 1
    ok("PySceneDetect: 2 scenes")
    splitter.set_scenes(v, segs)
    splitter.plan_clips(p, v)
    r = exporter.export_clips(ff, p, p.clips, Hooks())
    if r["done"] != 2 or r["failed"]:
        print(f"[selftest] FAIL export {r}")
        return 1
    ok("FFmpeg export: 2 clips")
    sg = assist.suggest(p.clips[0].file, SortCfg())
    ok(f"motion assist ({sg.label or 'uncertain'})")
    from app.security.keychain import SecretStore
    kb = SecretStore().backend_name()
    if sys.platform == "darwin" and "macOS" not in kb:
        print("[selftest] FAIL macOS Keychain backend not available:", kb)
        return 1
    ok("keychain backend: " + kb)
    import ssl
    import hashlib
    ssl.create_default_context()
    hashlib.sha256(b"x").hexdigest()
    ok("ssl/openssl works: " + ssl.OPENSSL_VERSION)
    import cryptography.exceptions  # noqa  (يكشف تعارض libcrypto داخل الحزمة)
    import google.auth.crypt.es  # noqa
    import googleapiclient.discovery  # noqa
    import google_auth_oauthlib.flow  # noqa
    ok("google api client + cryptography importable")
    from PySide6.QtWidgets import QApplication
    from app.config.schema import AppSettings
    from app.core import i18n
    from app.ui.context import Ctx
    from app.ui.main_window import MainWindow
    from app.ui import theme
    app = QApplication([])
    app.setStyleSheet(theme.stylesheet())
    for lang in ("ar", "en"):
        i18n.set_lang(lang)
        ctx = Ctx(AppSettings(language=lang))
        ctx.set_project(p)
        w = MainWindow(ctx)
        for i in range(w.stack.count()):
            w.stack.setCurrentIndex(i)
            app.processEvents()
        w.close()
    if i18n.MISSING:
        print("[selftest] FAIL missing translations:", sorted(i18n.MISSING))
        return 1
    ok("UI builds in Arabic and English (all 11 pages)")
    print(f"[selftest] PASSED {len(steps)} checks")
    return 0


def main():
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    setup_logging()
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication, QMessageBox
    from app.config.paths import default_projects_dir, resource_path
    from app.config.settings import load_settings
    from app.core import i18n
    from app.storage import project_store as store
    from app.ui import theme
    from app.ui.context import Ctx
    from app.ui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName(APP_SHORT)
    app.setStyleSheet(theme.stylesheet())
    icon_file = resource_path("assets/icon.png")
    if icon_file.exists():
        app.setWindowIcon(QIcon(str(icon_file)))
    settings = load_settings()
    i18n.set_lang(settings.language)
    ctx = Ctx(settings)
    holder = {}

    def show_window():
        i18n.set_lang(ctx.settings.language)
        app.setLayoutDirection(Qt.RightToLeft if ctx.settings.language == "ar" else Qt.LeftToRight)
        old = holder.get("w")
        w = MainWindow(ctx)
        holder["w"] = w
        w.show()
        if old:
            old.close()
            old.deleteLater()

    try:
        if settings.last_project and Path(settings.last_project).exists():
            ctx.open_project(settings.last_project)
        else:
            raise FileNotFoundError
    except Exception:
        base = default_projects_dir()
        base.mkdir(parents=True, exist_ok=True)
        name, i = "My First Project", 1
        while (base / name).exists():
            i += 1
            name = f"My Project {i}"
        ctx.new_project(name, base)
    show_window()
    ctx.languageChanged.connect(show_window)
    if ctx.project.workflow_state.get("status") in ("running", "paused"):
        ctx.log("A previous workflow was interrupted. Open the Workflow page to resume.", "warning")
    code = app.exec()
    ctx.save()
    sys.exit(code)


if __name__ == "__main__":
    main()
