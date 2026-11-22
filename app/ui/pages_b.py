"""صفحات: الفرز، الرفع، سير العمل."""
import os
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QHBoxLayout, QVBoxLayout, QFormLayout, QComboBox, QCheckBox, QLineEdit, QPlainTextEdit,
                               QMessageBox, QFileDialog, QTableWidgetItem, QProgressBar, QWidget)

from ..core.i18n import T, Tx
from ..core.progress import fmt_size
from ..sorter import assist
from ..sorter.sorter import Sorter, SortError
from ..splitter import splitter
from ..uploader import manager as upl
from ..workflow import engine as wf
from .pages_a import Page, spin, combo
from .player import PlayerBox
from .theme import C
from .widgets import card, label, button, make_table, PathRow


# ============================================================ الفرز
class SorterPage(Page):
    def __init__(self, ctx):
        super().__init__(ctx)
        self.header("nav_sorter")
        self.current = None
        top = QHBoxLayout()
        top.addWidget(label(T("source_filter") + ":"))
        self.filter = QComboBox()
        self.filter.currentIndexChanged.connect(self.next_clip)
        top.addWidget(self.filter, 1)
        self.autoplay = QCheckBox(T("autoplay"))
        self.loop = QCheckBox(T("loop"))
        self.autoplay.toggled.connect(lambda v: setattr(self.p.sort, "autoplay", v))
        self.loop.toggled.connect(self._loop)
        top.addWidget(self.autoplay)
        top.addWidget(self.loop)
        self.root.addLayout(top)
        pf, pl = card()
        self.title = label("", "h2")
        pl.addWidget(self.title)
        self.player = PlayerBox()
        pl.addWidget(self.player, 1)
        self.hint = label("", "muted", True)
        pl.addWidget(self.hint)
        bar = QHBoxLayout()
        self.btns = {}
        for key, name, cat in (("moving", "success", "moving"), ("stopping", "warning", "stopping"), ("excluded", "danger", "excluded")):
            b = button(f"{T('cat_' + key)}  [{ {'moving': '1', 'stopping': '2', 'excluded': '3'}[key] }]", name, lambda _=False, c=cat: self.classify(c))
            b.setMinimumHeight(40)
            self.btns[key] = b
            bar.addWidget(b)
        pl.addLayout(bar)
        bar2 = QHBoxLayout()
        bar2.addWidget(button(T("skip") + " [S]", None, self.skip))
        bar2.addWidget(button(T("undo") + " [Z]", None, self.undo))
        bar2.addWidget(button(T("restore_skipped") + " [R]", None, self.restore))
        bar2.addStretch()
        bar2.addWidget(button(T("suggest"), None, self.suggest))
        bar2.addWidget(button(T("auto_sort_all"), "primary", self.auto_sort_all))
        pl.addLayout(bar2)
        self.stats = label("", "muted")
        pl.addWidget(self.stats)
        self.root.addWidget(pf, 1)
        ctx.statsChanged.connect(self._update_stats)
        # اختصارات لوحة المفاتيح (تعمل عندما يكون التركيز داخل هذه الصفحة)
        for keys, fn in (("1", lambda: self.classify("moving")), ("2", lambda: self.classify("stopping")),
                         ("3", lambda: self.classify("excluded")), ("S", self.skip), ("Z", self.undo),
                         ("R", self.restore), ("Space", self.player.toggle),
                         ("Left", lambda: self.player.seek_rel(-2)), ("Right", lambda: self.player.seek_rel(2))):
            sc = QShortcut(QKeySequence(keys), self)
            sc.setContext(Qt.WidgetWithChildrenShortcut)
            sc.activated.connect(fn)
        self.setFocusPolicy(Qt.StrongFocus)

    @property
    def sorter(self):
        return Sorter(self.p)

    def showEvent(self, e):
        super().showEvent(e)
        self.refresh()
        self.setFocus()

    def hideEvent(self, e):
        self.player.pause()
        super().hideEvent(e)

    def _loop(self, v):
        self.p.sort.loop = v
        self.player.set_loop(v)

    def refresh(self):
        if not self.p:
            return
        self.autoplay.blockSignals(True)
        self.loop.blockSignals(True)
        self.autoplay.setChecked(self.p.sort.autoplay)
        self.loop.setChecked(self.p.sort.loop)
        self.autoplay.blockSignals(False)
        self.loop.blockSignals(False)
        cur = self.filter.currentData()
        self.filter.blockSignals(True)
        self.filter.clear()
        self.filter.addItem(T("all_sources"), None)
        for v in self.p.videos:
            self.filter.addItem(v.name, v.path)
        self.filter.setCurrentIndex(max(0, self.filter.findData(cur)))
        self.filter.blockSignals(False)
        self.player.set_loop(self.p.sort.loop)
        if self.current is None or not os.path.isfile(self.current.file) or self.current.category != "":
            self.next_clip()
        self._update_stats()

    def _update_stats(self):
        if not self.p:
            return
        s = self.p.stats()
        self.stats.setText(T("sort_stats").format(pending=s["pending"], moving=s["moving"], stopping=s["stopping"],
                                                  excluded=s["excluded"], skipped=s["skipped"]))

    def next_clip(self):
        if not self.p:
            return
        pend = self.sorter.pending(self.filter.currentData())
        self.current = pend[0] if pend else None
        if self.current:
            self.title.setText(f"{Path(self.current.file).name}   ({len(pend)} {T('remaining')})")
            self.player.load(self.current.file, self.p.sort.autoplay)
            sug = self.current.suggestion
            self.hint.setText(T("suggested").format(label=T("cat_" + sug), conf=int(self.current.confidence * 100)) if sug else "")
        else:
            self.player.release()
            self.title.setText(T("no_pending"))
            self.hint.setText("")
        for b in self.btns.values():
            b.setEnabled(self.current is not None)

    def _guard(self, fn):
        if not self.current:
            return
        self.player.release()          # تحرير الملف قبل نقله
        try:
            fn()
        except (SortError, OSError) as e:
            self.ctx.log(f"{T('sort_failed')}: {e}", "error")
        self.ctx.save()
        self.ctx.statsChanged.emit()
        self.next_clip()

    def classify(self, cat):
        self._guard(lambda: self.sorter.classify(self.current, cat))

    def skip(self):
        self._guard(lambda: self.sorter.skip(self.current))

    def undo(self):
        self.player.release()
        try:
            c = self.sorter.undo()
        except (SortError, OSError) as e:
            self.ctx.log(f"{T('sort_failed')}: {e}", "error")
            c = None
        self.ctx.save()
        self.ctx.statsChanged.emit()
        self.current = c
        if c and os.path.isfile(c.file):
            self.title.setText(Path(c.file).name)
            self.player.load(c.file, self.p.sort.autoplay)
            for b in self.btns.values():
                b.setEnabled(True)
        else:
            self.next_clip()

    def restore(self):
        n = self.sorter.restore_skipped()
        self.ctx.log(T("restored_n").format(n=n))
        self.ctx.statsChanged.emit()
        if self.current is None:
            self.next_clip()

    def suggest(self):
        c = self.current
        if not c:
            return

        def fn(h):
            return assist.suggest(c.file, self.p.sort)

        def done(sg):
            c.suggestion, c.confidence = sg.label, round(sg.confidence, 3)
            self.hint.setText(T("suggested").format(label=T("cat_" + sg.label), conf=int(sg.confidence * 100))
                              if sg.label else T("uncertain"))
        self.ctx.run_task(T("suggest"), fn, done)

    def auto_sort_all(self):
        if QMessageBox.question(self, T("auto_sort_all"), T("auto_sort_confirm")) != QMessageBox.Yes:
            return
        self.player.release()
        p = self.p

        def fn(h):
            from ..core.hooks import Cancelled
            s, todo = Sorter(p), Sorter(p).pending()
            ok = unsure = 0
            for i, c in enumerate(todo):
                h.check()
                h.progress("sort", i / max(1, len(todo)), f"{i + 1}/{len(todo)} • {Path(c.file).name}")
                try:
                    sg = assist.suggest(c.file, p.sort)
                except Exception as e:
                    h.log(f"{Path(c.file).name}: {e}", "warning")
                    unsure += 1
                    continue
                c.suggestion, c.confidence = sg.label, round(sg.confidence, 3)
                if sg.label and sg.confidence >= p.sort.assist_min_conf:
                    s.classify(c, sg.label)
                    ok += 1
                else:
                    unsure += 1
            return ok, unsure

        def done(r):
            self.ctx.log(T("auto_sort_done").format(ok=r[0], unsure=r[1]), "success")
            self.next_clip()
        self.ctx.run_task(T("auto_sort_all"), fn, done)


# ============================================================ الرفع
class UploadPage(Page):
    def __init__(self, ctx):
        super().__init__(ctx)
        self.header("nav_upload", "upload_sub")
        row = QHBoxLayout()
        row.setSpacing(12)
        lf, ll = card()
        ll.addWidget(label("YouTube", "h2"))
        self.account = label("", "muted", True)
        ll.addWidget(self.account)
        bar = QHBoxLayout()
        bar.addWidget(button(T("import_secret"), None, self.import_secret))
        bar.addWidget(button(T("link_account"), "primary", self.authorize))
        bar.addWidget(button(T("disconnect"), None, self.disconnect))
        ll.addLayout(bar)
        ll.addWidget(label(T("yt_note"), "muted", True))
        form = QFormLayout()
        self.f = {}
        self.f["enabled"] = QCheckBox(T("u_enable"))
        self.f["after_export"] = QCheckBox(T("u_after_export"))
        self.f["only_selected"] = QCheckBox(T("u_only_selected"))
        self.f["max_queue"] = spin(1, 500, 50)
        self.f["retries"] = spin(0, 10, 3)
        self.f["privacy"] = combo([("Private", "private"), ("Unlisted", "unlisted"), ("Public", "public")])
        self.f["title_template"] = QLineEdit()
        self.f["description"] = QPlainTextEdit()
        self.f["description"].setFixedHeight(70)
        self.f["tags"] = QLineEdit()
        rows = {"enabled": None, "after_export": None, "only_selected": None, "max_queue": "u_max_queue",
                "retries": "u_retries", "privacy": "u_privacy", "title_template": "u_title",
                "description": "u_desc", "tags": "u_tags"}
        for k, w in self.f.items():
            form.addRow(T(rows[k]) if rows[k] else "", w)
        ll.addLayout(form)
        self.f["enabled"].clicked.connect(self._enable_clicked)
        for k, w in self.f.items():
            if k == "enabled":
                continue
            sig = (w.toggled if isinstance(w, QCheckBox) else w.currentIndexChanged if isinstance(w, QComboBox)
                   else w.textChanged if isinstance(w, (QLineEdit, QPlainTextEdit)) else w.valueChanged)
            sig.connect(lambda *_a: self._write())
        ll.addWidget(label(T("u_vars"), "muted", True))
        rf, rl = card()
        rl.addWidget(label(T("u_queue"), "h2"))
        self.table = make_table(["✓", T("c_name"), T("c_status"), "ID"], stretch_col=1)
        self.table.cellClicked.connect(self._toggle_sel)
        rl.addWidget(self.table, 1)
        b2 = QHBoxLayout()
        b2.addWidget(button(T("upload_selected"), None, lambda: self.go(True)))
        b2.addWidget(button(T("upload_all"), "primary", lambda: self.go(False)))
        b2.addWidget(button(T("select_all"), None, self.select_all))
        rl.addLayout(b2)
        b3 = QHBoxLayout()
        self.pause = button(T("pause"), None, self.ctx.toggle_pause)
        b3.addWidget(self.pause)
        b3.addWidget(button(T("cancel"), "danger", self.ctx.cancel))
        rl.addLayout(b3)
        row.addWidget(lf, 3)
        row.addWidget(rf, 3)
        self.root.addLayout(row, 1)
        self._loading = False
        self.refresh()

    def _write(self):
        if self._loading or not self.p:
            return
        u = self.p.upload
        u.after_export = self.f["after_export"].isChecked()
        u.only_selected = self.f["only_selected"].isChecked()
        u.max_queue = self.f["max_queue"].value()
        u.retries = self.f["retries"].value()
        u.privacy = self.f["privacy"].currentData()
        u.title_template = self.f["title_template"].text()
        u.description = self.f["description"].toPlainText()
        u.tags = [t.strip() for t in self.f["tags"].text().split(",") if t.strip()]

    def _enable_clicked(self, checked):
        u = self.p.upload
        if checked:
            msg = T("consent_text").format(account=self.ctx.platform.account_label() or "—", privacy=u.privacy)
            if QMessageBox.question(self, T("u_enable"), msg) == QMessageBox.Yes:
                u.enabled = u.consent = True
            else:
                self.f["enabled"].setChecked(False)
        else:
            u.enabled = u.consent = False

    def refresh(self):
        if not self.p:
            return
        self._loading = True
        u = self.p.upload
        self.f["enabled"].setChecked(u.enabled and u.consent)
        self.f["after_export"].setChecked(u.after_export)
        self.f["only_selected"].setChecked(u.only_selected)
        self.f["max_queue"].setValue(u.max_queue)
        self.f["retries"].setValue(u.retries)
        self.f["privacy"].setCurrentIndex(max(0, self.f["privacy"].findData(u.privacy)))
        self.f["title_template"].setText(u.title_template)
        self.f["description"].setPlainText(u.description)
        self.f["tags"].setText(", ".join(u.tags))
        self._loading = False
        self._account()
        self._table()

    def showEvent(self, e):
        super().showEvent(e)
        self._table()

    def _account(self):
        pl = self.ctx.platform
        if pl.is_authorized():
            self.account.setText(f"{T('linked_as')}: {pl.account_label() or '?'}")
        elif pl.has_client_config():
            self.account.setText(T("not_linked"))
        else:
            self.account.setText(T("no_client"))

    def _table(self):
        self.table.setRowCount(0)
        log = {e["file"]: e for e in self.p.uploads_log}
        for c in self.p.clips:
            if not (c.exported and c.file):
                continue
            r = self.table.rowCount()
            self.table.insertRow(r)
            st = "uploaded" if c.uploaded else (log.get(c.file, {}).get("status", "pending"))
            vals = ["✔" if c.selected else "", Path(c.file).name, Tx("us_" + st, st), c.video_id]
            for i, v in enumerate(vals):
                it = QTableWidgetItem(v)
                it.setData(Qt.UserRole, c.id)
                self.table.setItem(r, i, it)

    def _toggle_sel(self, row, col):
        if col == 0:
            c = self.p.clip(self.table.item(row, 0).data(Qt.UserRole))
            c.selected = not c.selected
            self.table.item(row, 0).setText("✔" if c.selected else "")

    def select_all(self):
        pend = [c for c in self.p.clips if c.exported and not c.uploaded]
        flag = not all(c.selected for c in pend)
        for c in pend:
            c.selected = flag
        self._table()

    def import_secret(self):
        f, _ = QFileDialog.getOpenFileName(self, T("import_secret"), "", "JSON (*.json)")
        if f:
            try:
                self.ctx.platform.set_client_config(f)
                self.ctx.log(T("secret_saved"), "success")
            except Exception as e:
                QMessageBox.warning(self, "YouTube", str(e))
            self._account()

    def authorize(self):
        pl = self.ctx.platform
        if not pl.has_client_config():
            QMessageBox.information(self, "YouTube", T("no_client"))
            return
        self.ctx.run_task(T("link_account"), lambda h: pl.authorize(), lambda _r: self._account())

    def disconnect(self):
        self.ctx.platform.disconnect()
        self._account()

    def go(self, only_selected):
        u = self.p.upload
        if not (u.enabled and u.consent):
            QMessageBox.information(self, T("nav_upload"), T("enable_first"))
            return
        clips = upl.select_clips(self.p, only_selected=only_selected)
        if not clips:
            self.ctx.log(T("nothing_to_upload"), "warning")
            return
        self.ctx.upload_clips(clips, then=self._table)


# ============================================================ سير العمل
class WorkflowPage(Page):
    def __init__(self, ctx):
        super().__init__(ctx)
        self.header("nav_workflow", "wf_sub")
        cf, cl = card()
        top = QHBoxLayout()
        top.addWidget(label(T("template") + ":"))
        self.tpl = combo([(Tx("tpl_" + k, k), k) for k in wf.TEMPLATES])
        self.tpl.currentIndexChanged.connect(self._template)
        top.addWidget(self.tpl, 1)
        cl.addLayout(top)
        self.checks = {}
        for s in wf.STEPS:
            cb = QCheckBox(f"{T('step_' + s)}")
            cb.toggled.connect(lambda v, s=s: self._step(s, v))
            self.checks[s] = cb
            cl.addWidget(cb)
        cl.addWidget(label(T("wf_queue_folder"), "h2"))
        self.queue = PathRow(T("wf_queue_folder"), T("browse"), T("open_finder"))
        self.queue.changed.connect(self._queue_folder)
        cl.addWidget(self.queue)
        self.seq = QCheckBox(T("wf_sequential"))
        self.seq.toggled.connect(lambda v: None if self._loading else setattr(self.p.workflow, "sequential", v))
        self.rec = QCheckBox(T("wf_recursive"))
        self.rec.toggled.connect(lambda v: None if self._loading else setattr(self.p.workflow, "queue_recursive", v))
        cl.addWidget(self.seq)
        cl.addWidget(self.rec)
        cl.addWidget(label(T("wf_queue_note"), "muted", True))
        self.state = label("", "muted", True)
        cl.addWidget(self.state)
        bar = QHBoxLayout()
        self.start = button(T("start_wf"), "success", self.start_wf)
        self.pause = button(T("pause"), "warning", self.toggle_pause)
        self.stop = button(T("stop"), "danger", self.ctx.cancel)
        self.reset = button(T("reset_progress"), None, self.reset_progress)
        for b in (self.start, self.pause, self.stop, self.reset):
            bar.addWidget(b)
        cl.addLayout(bar)
        cl.addWidget(label(T("wf_note"), "muted", True))
        self.root.addWidget(cf)
        self.root.addStretch()
        ctx.busyChanged.connect(lambda _b: self.refresh())
        self._loading = False
        self.refresh()

    def refresh(self):
        if not self.p:
            return
        self._loading = True
        self.tpl.setCurrentIndex(max(0, self.tpl.findData(self.p.workflow.template)))
        for s, cb in self.checks.items():
            cb.setChecked(self.p.workflow.steps.get(s, False))
        self.queue.edit.setText(self.p.workflow.queue_folder)
        self.queue.size.setText("")
        self.seq.setChecked(self.p.workflow.sequential)
        self.rec.setChecked(self.p.workflow.queue_recursive)
        self._loading = False
        busy = self.ctx.busy
        self.start.setEnabled(not busy)
        self.reset.setEnabled(not busy)
        st = self.p.workflow_state.get("status")
        self.state.setText(T("wf_interrupted") if wf.interrupted(self.p) and not busy else
                           (T("wf_state_" + st) if st in ("done",) else ""))

    def _queue_folder(self, v):
        self.p.workflow.queue_folder = v.strip()
        self.ctx.save()

    def _template(self):
        if self._loading:
            return
        wf.apply_template(self.p, self.tpl.currentData())
        self.refresh()
        self.ctx.projectChanged.emit()

    def _step(self, s, v):
        if not self._loading:
            self.p.workflow.steps[s] = v
            if s == "upload" and v and not (self.p.upload.enabled and self.p.upload.consent):
                self.ctx.log(T("upload_step_needs_consent"), "warning")

    def reset_progress(self):
        wf.reset_progress(self.p)
        self.p.workflow_state = {}
        self.ctx.save()
        self.refresh()

    def toggle_pause(self):
        paused = self.ctx.toggle_pause()
        self.pause.setText(T("resume") if paused else T("pause"))

    def start_wf(self):
        if not self.p.videos and not self.p.workflow.queue_folder:
            self.ctx.log(T("no_videos"), "warning")
            return
        p = self.p
        self.pause.setText(T("pause"))

        def fn(h):
            return wf.WorkflowEngine(p, self.ctx.ffmpeg, h, self.ctx.save, self.ctx.platform).run()

        def done(r):
            self.ctx.log(T("wf_result_" + r["status"]), "success" if r["status"] == "done" else "warning")
            self.ctx.projectChanged.emit()
        self.ctx.run_task(T("nav_workflow"), fn, done)
