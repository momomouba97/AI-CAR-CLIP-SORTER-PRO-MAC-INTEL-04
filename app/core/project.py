"""نموذج المشروع: الفيديوهات والمقاطع والإعدادات والسجل."""
import datetime as dt
import os
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path

from ..config.schema import (AnalysisCfg, ExportCfg, UploadCfg, SortCfg, WorkflowCfg, PathsCfg,
                             load_dc, CATEGORIES, CATEGORY_DIRS)

PROJECT_FILE = "project.json"
SCHEMA_VERSION = 1


@dataclass
class SceneRec:
    start: float
    end: float
    keep: bool = True

    @property
    def duration(self):
        return self.end - self.start


@dataclass
class VideoRec:
    path: str
    duration: float = 0.0
    fps: float = 0.0
    width: int = 0
    height: int = 0
    size: int = 0
    scenes: list = field(default_factory=list)
    scenes_manual: bool = False
    done_steps: list = field(default_factory=list)
    status: str = "new"

    @property
    def name(self):
        return Path(self.path).name


@dataclass
class ClipRec:
    id: str
    source: str
    index: int
    start: float
    end: float
    name: str = ""
    file: str = ""
    category: str = ""        # "" | moving | stopping | excluded | skipped
    exported: bool = False
    uploaded: bool = False
    video_id: str = ""
    suggestion: str = ""
    confidence: float = 0.0
    selected: bool = False
    error: str = ""

    @property
    def duration(self):
        return self.end - self.start


class Project:
    def __init__(self, name: str, root: str):
        self.name = name
        self.root = str(root)
        self.created = time.time()
        self.videos: list[VideoRec] = []
        self.clips: list[ClipRec] = []
        self.analysis = AnalysisCfg()
        self.export = ExportCfg()
        self.upload = UploadCfg()
        self.sort = SortCfg()
        self.workflow = WorkflowCfg()
        self.paths = PathsCfg()
        self.activity: list = []
        self.daily: dict = {}
        self.uploads_log: list = []
        self.workflow_state: dict = {}
        self.sort_history: list = []
        self.apply_default_paths()

    # ---------- المسارات ----------
    def apply_default_paths(self):
        r = Path(self.root)
        p = self.paths
        p.source = p.source or str(r / "Source")
        p.export = p.export or str(r / "Exports")
        p.moving = p.moving or str(r / CATEGORY_DIRS["moving"])
        p.stopping = p.stopping or str(r / CATEGORY_DIRS["stopping"])
        p.excluded = p.excluded or str(r / CATEGORY_DIRS["excluded"])
        p.temp = p.temp or str(r / "Temp")

    def ensure_dirs(self):
        for d in (self.paths.source, self.paths.export, self.paths.moving, self.paths.stopping,
                  self.paths.excluded, self.paths.temp, self.trash_dir, self.reports_dir):
            Path(d).mkdir(parents=True, exist_ok=True)

    @property
    def trash_dir(self):
        return str(Path(self.root) / ".trash")

    @property
    def reports_dir(self):
        return str(Path(self.root) / "Reports")

    def category_dir(self, cat: str) -> str:
        return {"moving": self.paths.moving, "stopping": self.paths.stopping,
                "excluded": self.paths.excluded}[cat]

    # ---------- بحث ----------
    def video(self, path):
        return next((v for v in self.videos if v.path == path), None)

    def clip(self, cid):
        return next((c for c in self.clips if c.id == cid), None)

    def add_video(self, rec: VideoRec) -> bool:
        if self.video(rec.path):
            return False
        self.videos.append(rec)
        return True

    # ---------- النشاط والإحصائيات ----------
    def log_event(self, level: str, msg: str):
        self.activity.append({"ts": time.time(), "level": level, "msg": msg})
        if len(self.activity) > 2000:
            del self.activity[:500]

    def bump(self, kind: str, n: int = 1, day: str | None = None):
        day = day or dt.date.today().isoformat()
        d = self.daily.setdefault(day, {})
        d[kind] = d.get(kind, 0) + n

    def series(self, period: str = "daily", today: dt.date | None = None):
        """(labels, {kind: [values]}) لآخر 7 أيام أو 8 أسابيع."""
        today = today or dt.date.today()
        kinds = ("exported", "sorted", "uploaded")
        labels, out = [], {k: [] for k in kinds}
        if period == "daily":
            for i in range(6, -1, -1):
                day = today - dt.timedelta(days=i)
                labels.append(day.strftime("%m-%d"))
                for k in kinds:
                    out[k].append(self.daily.get(day.isoformat(), {}).get(k, 0))
        else:
            monday = today - dt.timedelta(days=today.weekday())
            for i in range(7, -1, -1):
                w0 = monday - dt.timedelta(weeks=i)
                labels.append(w0.strftime("%m-%d"))
                for k in kinds:
                    tot = 0
                    for d in range(7):
                        tot += self.daily.get((w0 + dt.timedelta(days=d)).isoformat(), {}).get(k, 0)
                    out[k].append(tot)
        return labels, out

    def storage_bytes(self) -> int:
        total = 0
        for c in self.clips:
            try:
                if c.file and os.path.isfile(c.file):
                    total += os.path.getsize(c.file)
            except OSError:
                pass
        return total

    def stats(self) -> dict:
        c = self.clips
        count = lambda f: sum(1 for x in c if f(x))
        return {
            "videos": len(self.videos),
            "scenes": sum(len(v.scenes) for v in self.videos),
            "exported": count(lambda x: x.exported),
            "processed": count(lambda x: x.category in CATEGORIES),
            "moving": count(lambda x: x.category == "moving"),
            "stopping": count(lambda x: x.category == "stopping"),
            "excluded": count(lambda x: x.category == "excluded"),
            "pending": count(lambda x: x.exported and x.category == ""),
            "skipped": count(lambda x: x.category == "skipped"),
            "uploaded": count(lambda x: x.uploaded),
            "storage": self.storage_bytes(),
        }

    # ---------- التسلسل ----------
    def settings_dict(self) -> dict:
        return {"analysis": asdict(self.analysis), "export": asdict(self.export),
                "upload": {k: v for k, v in asdict(self.upload).items() if k != "consent"},
                "sort": asdict(self.sort), "workflow": asdict(self.workflow),
                "paths": asdict(self.paths)}

    def apply_settings_dict(self, d: dict, with_paths=False):
        self.analysis = load_dc(AnalysisCfg, d.get("analysis"))
        self.export = load_dc(ExportCfg, d.get("export"))
        consent = self.upload.consent
        self.upload = load_dc(UploadCfg, d.get("upload"))
        self.upload.consent = consent
        self.sort = load_dc(SortCfg, d.get("sort"))
        self.workflow = load_dc(WorkflowCfg, d.get("workflow"))
        if with_paths:
            self.paths = load_dc(PathsCfg, d.get("paths"))
            self.apply_default_paths()

    def to_dict(self) -> dict:
        d = self.settings_dict()
        d["upload"] = asdict(self.upload)
        d.update({
            "version": SCHEMA_VERSION, "name": self.name, "root": self.root, "created": self.created,
            "videos": [asdict(v) for v in self.videos],
            "clips": [asdict(c) for c in self.clips],
            "activity": self.activity[-1000:], "daily": self.daily,
            "uploads_log": self.uploads_log[-2000:], "workflow_state": self.workflow_state,
            "sort_history": self.sort_history[-200:],
        })
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Project":
        p = cls(d.get("name", "Project"), d.get("root", ""))
        p.created = d.get("created", time.time())
        p.apply_settings_dict(d, with_paths=True)
        p.upload = load_dc(UploadCfg, d.get("upload"))
        for v in d.get("videos", []):
            scenes = [load_dc(SceneRec, s) for s in v.get("scenes", [])]
            rec = load_dc(VideoRec, {**v, "scenes": []})
            rec.scenes = scenes
            p.videos.append(rec)
        p.clips = [load_dc(ClipRec, c) for c in d.get("clips", [])]
        p.activity = d.get("activity", [])
        p.daily = d.get("daily", {})
        p.uploads_log = d.get("uploads_log", [])
        p.workflow_state = d.get("workflow_state", {})
        p.sort_history = d.get("sort_history", [])
        return p


def new_clip_id() -> str:
    return uuid.uuid4().hex[:12]
