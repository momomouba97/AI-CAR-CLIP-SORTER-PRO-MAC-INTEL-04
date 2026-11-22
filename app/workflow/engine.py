"""محرك سير العمل: Import → Analyze → Detect → Split → Export → Sort → Upload → Report.
يحفظ التقدم بعد كل خطوة، ويمكن إيقافه واستكماله لاحقاً (الخطوات المنجزة تُتخطى)."""
import json
import os
import time
from pathlib import Path

from ..core.hooks import Hooks, Cancelled
from ..core.project import Project, VideoRec
from ..core import progress as prg
from ..exporter import exporter
from ..sorter import assist
from ..sorter.sorter import Sorter
from ..splitter import splitter
from ..uploader import manager as upl
from ..video import info

STEPS = ("import", "analyze", "detect", "split", "export", "sort", "upload", "report")
VIDEO_STEPS = ("import", "analyze", "detect", "split")

TEMPLATES = {
    "Quick Split": {"steps": ["import", "analyze", "detect", "split", "export", "report"], "profile": "Fast"},
    "High Quality": {"steps": ["import", "analyze", "detect", "split", "export", "report"], "profile": "High Quality"},
    "Auto Sort": {"steps": ["import", "analyze", "detect", "split", "export", "sort", "report"], "profile": None},
    "Export and Upload": {"steps": ["import", "analyze", "detect", "split", "export", "upload", "report"],
                          "profile": None},
    "Full Automation": {"steps": None, "profile": None},   # يستخدم الخطوات المفعلة حالياً
}


def apply_template(project: Project, name: str):
    t = TEMPLATES[name]
    project.workflow.template = name
    if t["steps"] is not None:
        project.workflow.steps = {s: (s in t["steps"]) for s in STEPS}
    if t["profile"]:
        exporter.apply_profile(project.export, t["profile"])


def reset_progress(project: Project):
    for v in project.videos:
        v.done_steps = []


def interrupted(project: Project) -> bool:
    return project.workflow_state.get("status") in ("running", "paused", "stopped")


class WorkflowEngine:
    def __init__(self, project: Project, ffmpeg: str, hooks: Hooks, save=None, platform=None):
        self.p, self.ffmpeg, self.h, self.platform = project, ffmpeg, hooks, platform
        self._save = save or (lambda: None)
        self.errors: list[str] = []

    def _state(self, status, **kw):
        self.p.workflow_state = {"status": status, "template": self.p.workflow.template,
                                 "updated": time.time(), **kw}
        self._save()

    def enabled_steps(self):
        return [s for s in STEPS if self.p.workflow.steps.get(s)]

    # ---------- الخطوات على مستوى الفيديو ----------
    def _step_import(self, v):
        try:
            meta = info.probe(v.path)
        except info.CorruptVideoError as e:
            v.status = "corrupt"
            self.errors.append(str(e))
            self.h.log(f"Skipping corrupt video: {e}", "error")
            return False
        v.duration, v.fps, v.width, v.height, v.size = meta["duration"], meta["fps"], meta["width"], meta["height"], meta["size"]
        return True

    def _step_analyze(self, v):
        if not v.duration or not v.fps:
            return self._step_import(v)
        return True

    def _step_detect(self, v):
        if v.scenes_manual and v.scenes:
            self.h.log(f"Keeping manual scene edits: {v.name}")
            return True
        segs = splitter.analyze_video(v, self.p.analysis, self.h)
        splitter.set_scenes(v, segs)
        self.h.log(f"{v.name}: {len(segs)} scenes", "success")
        return True

    def _step_split(self, v):
        if not v.scenes:
            self.h.log(f"No scenes for {v.name}; enable the Detect step", "warning")
            return False
        n = splitter.plan_clips(self.p, v)
        self.h.log(f"{v.name}: {n} clips planned")
        return True

    # ---------- الخطوات العامة ----------
    def _step_export(self, source=None):
        clips = [c for c in self.p.clips if not c.exported and (source is None or c.source == source)]
        if not clips:
            return {"done": 0}
        r = exporter.export_clips(self.ffmpeg, self.p, clips, self.h, self._save)
        self.errors += r["errors"]
        return r

    def _step_sort(self, source=None):
        s = Sorter(self.p)
        todo = s.pending(source)
        if not self.p.sort.assist:
            self.h.log("Auto-assist sort is disabled; sorting stays manual", "warning")
            return {"classified": 0, "uncertain": len(todo)}
        n_ok = n_unsure = 0
        for i, c in enumerate(todo):
            self.h.check()
            self.h.progress("sort", i / max(1, len(todo)), f"{i + 1}/{len(todo)} • {Path(c.file).name}")
            try:
                sg = assist.suggest(c.file, self.p.sort)
            except Exception as e:
                self.h.log(f"Motion analysis failed for {Path(c.file).name}: {e}", "warning")
                n_unsure += 1
                continue
            c.suggestion, c.confidence = sg.label, round(sg.confidence, 3)
            if sg.label and sg.confidence >= self.p.sort.assist_min_conf:
                s.classify(c, sg.label)
                n_ok += 1
            else:
                n_unsure += 1
            self._save()
        self.h.log(f"Auto-sort: {n_ok} classified, {n_unsure} left for you to decide", "info")
        return {"classified": n_ok, "uncertain": n_unsure}

    def _step_upload(self, source=None):
        if self.platform is None:
            self.h.log("Upload skipped: no platform configured", "warning")
            return {"skipped": True}
        try:
            upl.assert_allowed(self.p, self.platform)
        except upl.UploadNotAllowed as e:
            self.h.log(f"Upload skipped: {e}", "warning")
            return {"skipped": True}
        clips = upl.select_clips(self.p, source=source)
        if not clips:
            return {"ok": 0}
        r = upl.run_uploads(self.p, self.platform, clips, self.h, self._save)
        self.errors += r["errors"]
        return r

    def _step_report(self, results):
        Path(self.p.reports_dir).mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        st = self.p.stats()
        data = {"project": self.p.name, "time": stamp, "stats": st, "results": results, "errors": self.errors}
        base = Path(self.p.reports_dir) / f"report_{stamp}"
        base.with_suffix(".json").write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), "utf-8")
        lines = [f"Project: {self.p.name}", f"Date: {stamp}", ""]
        lines += [f"{k}: {v}" for k, v in st.items() if k != "storage"]
        lines.append(f"storage: {prg.fmt_size(st['storage'])}")
        if self.errors:
            lines += ["", "Errors:"] + [f"- {e}" for e in self.errors]
        base.with_suffix(".txt").write_text("\n".join(lines), "utf-8")
        self.h.log(f"Report saved: {base.with_suffix('.txt').name}", "success")
        return str(base.with_suffix(".txt"))

    # ---------- الطابور التلقائي ----------
    def queue_paths(self):
        """مسارات الفيديوهات بالترتيب: ما في المشروع + ما في مجلد الاستيراد التلقائي (ترتيب طبيعي)."""
        cfg = self.p.workflow
        paths = [v.path for v in self.p.videos]
        if cfg.queue_folder and os.path.isdir(cfg.queue_folder):
            seen = set(paths)
            found = info.scan_folder(cfg.queue_folder, cfg.queue_recursive)
            paths += [f for f in found if f not in seen]
            paths = sorted(set(paths), key=info.natural_key)
        return paths

    def _video_steps(self, v, steps, idx, total):
        for step in VIDEO_STEPS:
            if step in v.done_steps:
                continue
            if step not in steps and not (step == "import" and not v.duration):
                continue                      # الاستيراد يُنفَّذ دائماً لفيديو جديد (نحتاج مدته ومعدل إطاراته)
            self.h.check()
            self.h.progress(step, None, f"{step} • {v.name} ({idx}/{total})")
            if not getattr(self, f"_step_{step}")(v):
                return False
            v.done_steps.append(step)
            self._save()
        return True

    def _run_sequential(self, steps, results):
        paths = self.queue_paths()
        total = len(paths)
        for i, path in enumerate(paths, start=1):
            self.h.check()
            v = self.p.video(path)
            if v is None:                     # استيراد تلقائي للفيديو التالي
                v = VideoRec(path, status="imported")
                self.p.add_video(v)
                self.h.log(f"Auto-import ({i}/{total}): {v.name}")
                self._save()
            if "complete" in v.done_steps:
                self.h.log(f"Already complete, skipping: {v.name}")
                continue
            self.h.progress("queue", (i - 1) / max(1, total), f"{i}/{total} • {v.name}")
            if not self._video_steps(v, steps, i, total):
                continue
            for step in ("export", "sort", "upload"):
                if step in steps:
                    self.h.check()
                    r = getattr(self, f"_step_{step}")(v.path)
                    prev = results.setdefault(step, {})
                    for k, val in (r or {}).items():
                        if isinstance(val, int) and not isinstance(val, bool):
                            prev[k] = prev.get(k, 0) + val
                        else:
                            prev[k] = val
            pending = [c for c in self.p.clips if c.source == v.path and not c.exported]
            if "export" not in steps or not pending:
                v.done_steps.append("complete")
            else:
                self.h.log(f"{v.name}: {len(pending)} clip(s) failed; will retry on next run", "warning")
            self._save()
        results["queue"] = {"videos": total}

    # ---------- التشغيل ----------
    def run(self):
        steps = self.enabled_steps()
        results = {}
        self._state("running", steps=steps)
        exporter.cleanup_partials(self.p)
        try:
            if self.p.workflow.sequential or self.p.workflow.queue_folder:
                self._run_sequential(steps, results)
            else:
                for vi, v in enumerate(self.p.videos):
                    self._video_steps(v, steps, vi + 1, len(self.p.videos))
                for step in ("export", "sort", "upload"):
                    if step in steps:
                        self.h.check()
                        results[step] = getattr(self, f"_step_{step}")()
            if "report" in steps:
                results["report"] = self._step_report(results)
        except Cancelled:
            self._state("stopped", steps=steps)
            self.h.log("Workflow stopped. Progress saved; you can resume later.", "warning")
            return {"status": "stopped", "results": results}
        except exporter.DiskFullError as e:
            self._state("stopped", steps=steps, error=str(e))
            self.h.log(f"Workflow halted: {e}", "error")
            return {"status": "error", "results": results, "error": str(e)}
        except Exception as e:
            self._state("stopped", steps=steps, error=str(e))
            self.h.log(f"Workflow error: {e}", "error")
            raise
        self._state("done", steps=steps)
        self.h.progress("done", 1.0, "")
        self.h.log("Workflow finished", "success")
        return {"status": "done", "results": results}
