import json
import os
import shutil
import threading
from pathlib import Path

from ..core.project import Project, PROJECT_FILE, VideoRec, SceneRec
from dataclasses import asdict

_lock = threading.Lock()


def project_file(root) -> Path:
    return Path(root) / PROJECT_FILE


def save_project(p: Project) -> None:
    """حفظ ذري: نكتب ملفاً مؤقتاً ثم نستبدله، فلا يتلف المشروع عند انقطاع التيار."""
    with _lock:
        Path(p.root).mkdir(parents=True, exist_ok=True)
        f = project_file(p.root)
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(p.to_dict(), ensure_ascii=False, indent=1), "utf-8")
        if f.exists():
            shutil.copy2(f, f.with_suffix(".bak"))
        os.replace(tmp, f)


def load_project(path) -> Project:
    path = Path(path)
    f = path if path.is_file() else project_file(path)
    try:
        data = json.loads(f.read_text("utf-8"))
    except Exception:
        bak = f.with_suffix(".bak")
        if not bak.exists():
            raise
        data = json.loads(bak.read_text("utf-8"))
    p = Project.from_dict(data)
    p.root = str(f.parent)
    p.apply_default_paths()
    return p


def create_project(name: str, parent_dir) -> Project:
    root = Path(parent_dir) / name
    if project_file(root).exists():
        raise FileExistsError(str(root))
    p = Project(name, str(root))
    p.ensure_dirs()
    save_project(p)
    return p


def duplicate_project(src: Project, new_name: str, parent_dir) -> Project:
    """نسخ الإعدادات وقائمة الفيديوهات (بدون المقاطع الناتجة)."""
    root = Path(parent_dir) / new_name
    if project_file(root).exists():
        raise FileExistsError(str(root))
    p = Project(new_name, str(root))
    p.apply_settings_dict(src.settings_dict())
    p.upload.consent = False
    for v in src.videos:
        nv = VideoRec(**{**asdict(v), "scenes": [], "done_steps": [], "status": "new"})
        nv.scenes = [SceneRec(**asdict(s)) for s in v.scenes]
        p.videos.append(nv)
    p.ensure_dirs()
    save_project(p)
    return p


def export_settings(p: Project, dest) -> None:
    Path(dest).write_text(json.dumps(p.settings_dict(), ensure_ascii=False, indent=2), "utf-8")


def import_settings(p: Project, src) -> None:
    p.apply_settings_dict(json.loads(Path(src).read_text("utf-8")))
