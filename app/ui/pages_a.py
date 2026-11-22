"""صفحات: لوحة التحكم، الاستيراد، المشاهد، التصدير."""
import time
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout, QComboBox,
                               QDoubleSpinBox, QSpinBox, QLineEdit, QCheckBox, QFileDialog, QMessageBox,
                               QListWidget, QTableWidgetItem)

from ..core.i18n import T, Tx
from ..core.progress import fmt_size, fmt_duration
from ..core.project import VideoRec
from ..core.ffmpeg_util import available_encoders
from ..exporter import exporter
from ..splitter import splitter
from ..video import info
from .player import PlayerBox
from .theme import C
from .widgets import StatCard, BarChart, card, label, button, make_table, PathRow


class Page(QWidget):
    def __init__(self, ctx):
        super().__init__()
        self.setObjectName("page")
        self.ctx = ctx
        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(24, 20, 24, 20)
        self.root.setSpacing(14)
        ctx.projectChanged.connect(self.refresh)

    @property
    def p(self):
        return self.ctx.project

    def header(self, title_key, sub_key=None):
        self.root.addWidget(label(T(title_key), "h1"))
        if sub_key:
            self.root.addWidget(label(T(sub_key), "muted", True))

    def refresh(self):
        pass


def spin(lo, hi, val, step=1, dec=None):
    w = QDoubleSpinBox() if dec is not None else QSpinBox()
    if dec is not None:
        w.setDecimals(dec)
    w.setRange(lo, hi)
    w.setSingleStep(step)
    w.setValue(val)
    return w


def combo(items, current=None):
    c = QComboBox()
    for text, data in items:
        c.addItem(text, data)
    if current is not None:
        i = c.findData(current)
        c.setCurrentIndex(max(0, i))
    return c


# ============================================================ لوحة التحكم
class DashboardPage(Page):
    CARDS = [("videos", "st_videos", C["primary"]), ("scenes", "st_scenes", C["primary"]),
             ("exported", "st_exported", C["success"]), ("processed", "st_processed", C["success"]),
             ("moving", "st_moving", C["success"]), ("stopping", "st_stopping", C["warning"]),
             ("excluded", "st_excluded", C["error"]), ("uploaded", "st_uploaded", C["primary"]),
             ("storage", "st_storage", C["warning"]), ("pending", "st_pending", C["muted"])]

    def __init__(self, ctx):
        super().__init__(ctx)
        self.header("nav_dashboard")
        self.sub = label("", "muted")
        self.root.addWidget(self.sub)
        g = QGridLayout()
        g.setSpacing(12)
        self.cards = {}
        for i, (k, tk, col) in enumerate(self.CARDS):
            c = StatCard(T(tk), col)
            self.cards[k] = c
            g.addWidget(c, i // 5, i % 5)
        self.root.addLayout(g)
        row = QHBoxLayout()
        row.setSpacing(12)
        cf, cl = card()
        top = QHBoxLayout()
        top.addWidget(label(T("work_stats"), "h2"))
        top.addStretch()
        self.period = combo([(T("daily"), "daily"), (T("weekly"), "weekly")], "daily")
        self.period.currentIndexChanged.connect(self.refresh)
        top.addWidget(self.period)
        cl.addLayout(top)
        self.chart = BarChart()
        cl.addWidget(self.chart)
        af, al = card()
        al.addWidget(label(T("recent_ops"), "h2"))
        self.activity = QListWidget()
        al.addWidget(self.activity)
        row.addWidget(cf, 3)
        row.addWidget(af, 2)
        self.root.addLayout(row, 1)
        ctx.statsChanged.connect(self.refresh)

    def refresh(self):
        if not self.p:
            return
        st = self.p.stats()
        for k, c in self.cards.items():
            c.set(fmt_size(st[k]) if k == "storage" else st[k])
        self.sub.setText(f"{T('project')}: {self.p.name}")
        labels, series = self.p.series(self.period.currentData())
        self.chart.set_data(labels, series, {"exported": C["primary"], "sorted": C["success"], "uploaded": C["warning"]},
                            {"exported": T("st_exported"), "sorted": T("sorted_n"), "uploaded": T("st_uploaded")})
        self.activity.clear()
        for e in reversed(self.p.activity[-14:]):
            self.activity.addItem(f"{time.strftime('%H:%M:%S', time.localtime(e['ts']))}  {e['msg']}")


# ============================================================ الاستيراد والتحليل
class ImportPage(Page):
    def __init__(self, ctx):
        super().__init__(ctx)
        self.header("nav_import", "import_sub")
        row = QHBoxLayout()
        row.setSpacing(12)
        lf, ll = card()
        bar = QHBoxLayout()
        bar.addWidget(button(T("add_videos"), "primary", self.add_videos))
        bar.addWidget(button(T("add_folder"), None, self.add_folder))
        bar.addWidget(button(T("remove"), None, self.remove))
        bar.addStretch()
        ll.addLayout(bar)
        self.table = make_table([T("c_name"), T("c_duration"), T("c_res"), T("c_fps"), T("c_scenes"), T("c_status")])
        ll.addWidget(self.table, 1)
        bar2 = QHBoxLayout()
        bar2.addWidget(button(T("analyze_sel"), None, lambda: self.analyze(True)))
        bar2.addWidget(button(T("analyze_all"), "success", lambda: self.analyze(False)))
        self.auto = QCheckBox(T("auto_export_after"))
        self.auto.toggled.connect(lambda v: setattr(self.p.export, "auto_export", v))
        bar2.addStretch()
        bar2.addWidget(self.auto)
        ll.addLayout(bar2)
        rf, rl = card()
        rl.addWidget(label(T("analysis_settings"), "h2"))
        form = QFormLayout()
        self.f = {}
        self.f["mode"] = combo([(T("mode_scene"), "scene"), (T("mode_fixed"), "fixed"), (T("mode_auto_short"), "auto_short")])
        self.f["detector"] = combo([("ContentDetector", "content"), ("AdaptiveDetector", "adaptive")])
        self.f["threshold"] = spin(5, 100, 27, 1, 1)
        self.f["adaptive_threshold"] = spin(1, 10, 3, 0.1, 1)
        self.f["min_scene_len"] = spin(0, 600, 1, 0.5, 1)
        self.f["max_scene_len"] = spin(0, 3600, 0, 1, 1)
        self.f["target_len"] = spin(0, 3600, 0, 1, 1)
        self.f["fixed_len"] = spin(1, 3600, 10, 1, 1)
        self.f["min_valid_len"] = spin(0.1, 10, 0.3, 0.1, 1)
        self.f["prefix"] = QLineEdit()
        titles = {"mode": "f_mode", "detector": "f_detector", "threshold": "f_threshold",
                  "adaptive_threshold": "f_adaptive", "min_scene_len": "f_min_len", "max_scene_len": "f_max_len",
                  "target_len": "f_target", "fixed_len": "f_fixed", "min_valid_len": "f_min_valid", "prefix": "f_prefix"}
        for k, w in self.f.items():
            form.addRow(T(titles[k]), w)
            sig = w.currentIndexChanged if isinstance(w, QComboBox) else (w.textChanged if isinstance(w, QLineEdit) else w.valueChanged)
            sig.connect(lambda *_a, k=k: self._write())
        rl.addLayout(form)
        rl.addWidget(label(T("zero_off"), "muted", True))
        rl.addStretch()
        row.addWidget(lf, 3)
        row.addWidget(rf, 2)
        self.root.addLayout(row, 1)
        self._loading = False
        self.refresh()

    def _write(self):
        if self._loading or not self.p:
            return
        a = self.p.analysis
        for k, w in self.f.items():
            v = w.currentData() if isinstance(w, QComboBox) else (w.text() if isinstance(w, QLineEdit) else w.value())
            setattr(a, k, v)

    def refresh(self):
        if not self.p:
            return
        self._loading = True
        for k, w in self.f.items():
            v = getattr(self.p.analysis, k)
            if isinstance(w, QComboBox):
                w.setCurrentIndex(max(0, w.findData(v)))
            elif isinstance(w, QLineEdit):
                w.setText(str(v))
            else:
                w.setValue(v)
        self.auto.setChecked(self.p.export.auto_export)
        self._loading = False
        self.table.setRowCount(0)
        for v in self.p.videos:
            r = self.table.rowCount()
            self.table.insertRow(r)
            vals = [v.name, fmt_duration(v.duration), f"{v.width}×{v.height}", f"{v.fps:.2f}", len(v.scenes), Tx("vs_" + v.status, v.status)]
            for c, val in enumerate(vals):
                self.table.setItem(r, c, QTableWidgetItem(str(val)))

    # ----- إجراءات -----
    def _add(self, paths):
        known = {v.path for v in self.p.videos}
        paths = [x for x in paths if x not in known]
        if not paths:
            return

        def fn(h):
            out, bad = [], []
            for i, path in enumerate(paths):
                h.check()
                h.progress("import", i / len(paths), f"{i + 1}/{len(paths)} • {Path(path).name}")
                try:
                    out.append(VideoRec(path, status="imported", **info.probe(path)))
                except info.CorruptVideoError as e:
                    bad.append(str(e))
            return out, bad

        def done(res):
            ok, bad = res
            for v in ok:
                self.p.add_video(v)
            for b in bad:
                self.ctx.log(f"{T('corrupt_skipped')}: {b}", "error")
            self.ctx.log(T("imported_n").format(n=len(ok)), "success")
            self.refresh()
        self.ctx.run_task(T("import"), fn, done)

    def add_videos(self):
        exts = " ".join("*" + e for e in sorted(info.VIDEO_EXTS))
        files, _ = QFileDialog.getOpenFileNames(self, T("add_videos"), self.p.paths.source, f"Video ({exts})")
        if files:
            self._add(files)

    def add_folder(self):
        d = QFileDialog.getExistingDirectory(self, T("add_folder"), self.p.paths.source)
        if d:
            self._add(info.scan_folder(d))

    def remove(self):
        rows = sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True)
        if not rows:
            return
        if QMessageBox.question(self, T("remove"), T("remove_confirm")) != QMessageBox.Yes:
            return
        for r in rows:                      # إزالة من المشروع فقط؛ لا نلمس الملفات الأصلية
            v = self.p.videos.pop(r)
            self.p.clips = [c for c in self.p.clips if c.source != v.path or c.exported]
        self.ctx.statsChanged.emit()
        self.refresh()

    def analyze(self, selected_only):
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        vids = [self.p.videos[r] for r in rows] if selected_only and rows else list(self.p.videos)
        if not vids:
            self.ctx.log(T("no_videos"), "warning")
            return
        cfg = self.p.analysis

        def fn(h):
            for i, v in enumerate(vids):
                h.check()
                if not v.duration:
                    meta = info.probe(v.path)
                    v.duration, v.fps, v.width, v.height, v.size = meta["duration"], meta["fps"], meta["width"], meta["height"], meta["size"]
                segs = splitter.analyze_video(v, cfg, h)
                splitter.set_scenes(v, segs)
                splitter.plan_clips(self.p, v)
                h.log(f"{v.name}: {len(segs)} {T('scenes_found')}", "success")
            return len(vids)

        def done(_):
            self.refresh()
            self.ctx.after_analysis()
        self.ctx.run_task(T("analyze"), fn, done)


# ============================================================ المشاهد
class ScenesPage(Page):
    def __init__(self, ctx):
        super().__init__(ctx)
        self.header("nav_scenes", "scenes_sub")
        top = QHBoxLayout()
        self.video_box = QComboBox()
        self.video_box.currentIndexChanged.connect(self.load_scenes)
        top.addWidget(label(T("video") + ":"))
        top.addWidget(self.video_box, 1)
        self.root.addLayout(top)
        row = QHBoxLayout()
        row.setSpacing(12)
        lf, ll = card()
        self.table = make_table(["✓", "#", T("c_start"), T("c_end"), T("c_duration")], stretch_col=4)
        self.table.cellClicked.connect(self._clicked)
        self.table.itemDoubleClicked.connect(lambda _i: self.preview())
        ll.addWidget(self.table, 1)
        bar = QHBoxLayout()
        for text, name, cb in ((T("preview"), None, self.preview), (T("toggle_keep"), None, self.toggle_keep),
                               (T("delete_scenes"), None, self.delete), (T("merge_scenes"), None, self.merge),
                               (T("reanalyze"), None, self.reanalyze)):
            bar.addWidget(button(text, name, cb))
        ll.addLayout(bar)
        bar2 = QHBoxLayout()
        bar2.addWidget(button(T("export_clips"), "primary", self.export_clips))
        self.info = label("", "muted")
        bar2.addWidget(self.info, 1)
        ll.addLayout(bar2)
        rf, rl = card()
        rl.addWidget(label(T("preview"), "h2"))
        self.player = PlayerBox()
        rl.addWidget(self.player, 1)
        row.addWidget(lf, 3)
        row.addWidget(rf, 2)
        self.root.addLayout(row, 1)
        self.refresh()

    def showEvent(self, e):
        super().showEvent(e)
        self.refresh()

    def hideEvent(self, e):
        self.player.pause()
        super().hideEvent(e)

    def refresh(self):
        if not self.p:
            return
        cur = self.video_box.currentData()
        self.video_box.blockSignals(True)
        self.video_box.clear()
        for v in self.p.videos:
            self.video_box.addItem(v.name, v.path)
        i = self.video_box.findData(cur)
        self.video_box.setCurrentIndex(max(0, i))
        self.video_box.blockSignals(False)
        self.load_scenes()

    @property
    def video(self):
        return self.p.video(self.video_box.currentData()) if self.p and self.video_box.currentData() else None

    def load_scenes(self):
        self.table.setRowCount(0)
        v = self.video
        if not v:
            return
        for n, sc in enumerate(v.scenes, 1):
            r = self.table.rowCount()
            self.table.insertRow(r)
            vals = ["✔" if sc.keep else "✘", n, fmt_duration(sc.start), fmt_duration(sc.end), f"{sc.duration:.1f}s"]
            for c, val in enumerate(vals):
                self.table.setItem(r, c, QTableWidgetItem(str(val)))
        kept = sum(1 for s in v.scenes if s.keep)
        self.info.setText(T("scene_counts").format(total=len(v.scenes), kept=kept))
        self.player.load(v.path)

    def _rows(self):
        return sorted({i.row() for i in self.table.selectedIndexes()})

    def _clicked(self, row, col):
        if col == 0 and self.video:
            self.video.scenes[row].keep = not self.video.scenes[row].keep
            self.video.scenes_manual = True
            self.load_scenes()

    def preview(self):
        rows, v = self._rows(), self.video
        if rows and v:
            s = v.scenes[rows[0]]
            self.player.play_range(s.start, s.end)

    def toggle_keep(self):
        v = self.video
        for r in self._rows():
            v.scenes[r].keep = not v.scenes[r].keep
        if v:
            v.scenes_manual = True
        self.load_scenes()

    def delete(self):
        v, rows = self.video, self._rows()
        if not v or not rows:
            return
        if QMessageBox.question(self, T("delete_scenes"), T("delete_scenes_confirm")) != QMessageBox.Yes:
            return
        for r in reversed(rows):
            del v.scenes[r]
        v.scenes_manual = True
        self.load_scenes()
        self.ctx.statsChanged.emit()

    def merge(self):
        v, rows = self.video, self._rows()
        if not v or len(rows) < 2:
            return
        try:
            v.scenes = splitter.merge_scenes(v.scenes, rows)
        except ValueError:
            QMessageBox.warning(self, T("merge_scenes"), T("merge_adjacent"))
            return
        v.scenes_manual = True
        self.load_scenes()
        self.ctx.statsChanged.emit()

    def reanalyze(self):
        v = self.video
        if not v:
            return

        def fn(h):
            segs = splitter.analyze_video(v, self.p.analysis, h)
            splitter.set_scenes(v, segs)
            return len(segs)
        self.ctx.run_task(T("reanalyze"), fn, lambda _r: self.load_scenes())

    def export_clips(self):
        for v in self.p.videos:
            splitter.plan_clips(self.p, v)
        self.player.release()
        self.ctx.export_pending(then=self.load_scenes)


# ============================================================ التصدير
class ExportPage(Page):
    def __init__(self, ctx):
        super().__init__(ctx)
        self.header("nav_export", "export_sub")
        cf, cl = card()
        form = QFormLayout()
        self.f = {}
        self.f["profile"] = combo([(k, k) for k in exporter.PROFILES])
        self.f["container"] = combo([("MP4", "mp4"), ("MOV", "mov")])
        self.f["codec"] = combo([("H.264", "h264"), ("H.265 (HEVC)", "h265")])
        self.f["crf"] = spin(0, 51, 23)
        self.f["speed"] = combo([(x, x) for x in ("ultrafast", "veryfast", "faster", "fast", "medium", "slow", "slower")])
        self.f["bitrate_k"] = spin(0, 100000, 0, 100)
        self.f["fps"] = spin(0, 240, 0)
        self.f["height"] = combo([(T("original"), 0), ("2160p", 2160), ("1440p", 1440), ("1080p", 1080), ("720p", 720), ("480p", 480)])
        self.f["keep_audio"] = QCheckBox(T("keep_audio"))
        self.f["audio_codec"] = combo([("AAC", "aac"), ("Copy", "copy")])
        self.f["audio_bitrate_k"] = spin(32, 512, 192, 32)
        self.f["fast_copy"] = QCheckBox(T("fast_copy"))
        self.f["fast_copy"].setToolTip(T("fast_copy_tip"))
        self.f["existing"] = combo([(T("ex_skip"), "skip"), (T("ex_rename"), "rename"), (T("ex_overwrite"), "overwrite")])
        self.f["threads"] = spin(0, 64, 0)
        titles = {"profile": "f_profile", "container": "f_container", "codec": "f_codec", "crf": "f_crf", "speed": "f_speed",
                  "bitrate_k": "f_bitrate", "fps": "f_fps", "height": "f_height", "keep_audio": None, "audio_codec": "f_acodec",
                  "audio_bitrate_k": "f_abitrate", "fast_copy": None, "existing": "f_existing", "threads": "f_threads"}
        try:
            if "libx265" not in available_encoders(ctx.ffmpeg):
                self.f["codec"].removeItem(1)
                self.f["codec"].setToolTip(T("no_h265"))
        except Exception:
            pass
        for k, w in self.f.items():
            if titles[k]:
                form.addRow(T(titles[k]), w)
            else:
                form.addRow("", w)
            sig = w.currentIndexChanged if isinstance(w, QComboBox) else (w.toggled if isinstance(w, QCheckBox) else w.valueChanged)
            sig.connect(lambda *_a, k=k: self._write(k))
        cl.addLayout(form)
        cl.addWidget(label(T("export_note"), "muted", True))
        self.folder = PathRow(T("export_folder"), T("browse"), T("open_finder"))
        self.folder.changed.connect(lambda v: setattr(self.p.paths, "export", v))
        cl.addWidget(self.folder)
        self.auto = QCheckBox(T("auto_export"))
        self.auto.toggled.connect(lambda v: setattr(self.p.export, "auto_export", v))
        cl.addWidget(self.auto)
        bar = QHBoxLayout()
        bar.addWidget(button(T("export_now"), "primary", self.export_now))
        bar.addStretch()
        cl.addLayout(bar)
        self.root.addWidget(cf)
        self.root.addStretch()
        self._loading = False
        self.refresh()

    def _write(self, k):
        if self._loading or not self.p:
            return
        w, e = self.f[k], self.p.export
        if k == "profile":
            exporter.apply_profile(e, w.currentData())
            self.refresh()
            return
        if k == "existing" and w.currentData() == "overwrite":
            if QMessageBox.question(self, T("ex_overwrite"), T("overwrite_confirm")) != QMessageBox.Yes:
                self._loading = True
                w.setCurrentIndex(w.findData(e.existing))
                self._loading = False
                return
        v = w.isChecked() if isinstance(w, QCheckBox) else (w.currentData() if isinstance(w, QComboBox) else w.value())
        setattr(e, k, v)

    def refresh(self):
        if not self.p:
            return
        self._loading = True
        for k, w in self.f.items():
            v = getattr(self.p.export, k)
            if isinstance(w, QComboBox):
                w.setCurrentIndex(max(0, w.findData(v)))
            elif isinstance(w, QCheckBox):
                w.setChecked(bool(v))
            else:
                w.setValue(v)
        self.folder.edit.setText(self.p.paths.export)
        self.auto.setChecked(self.p.export.auto_export)
        self._loading = False

    def export_now(self):
        for v in self.p.videos:
            splitter.plan_clips(self.p, v)
        self.ctx.export_pending()
