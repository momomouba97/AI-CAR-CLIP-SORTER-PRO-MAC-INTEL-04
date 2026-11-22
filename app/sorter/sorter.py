"""الفرز: نقل/نسخ المقاطع إلى مجلدات التصنيف مع تراجع وتخطي واستعادة."""
import os
import shutil
from pathlib import Path

from ..config.schema import CATEGORIES
from ..core.project import Project, ClipRec


class SortError(Exception):
    pass


def _unique(path: Path) -> Path:
    if not path.exists():
        return path
    i = 1
    while True:
        c = path.with_name(f"{path.stem}_{i}{path.suffix}")
        if not c.exists():
            return c
        i += 1


class Sorter:
    def __init__(self, project: Project):
        self.p = project

    def pending(self, source: str | None = None):
        return [c for c in self.p.clips
                if c.exported and c.category == "" and c.file and os.path.isfile(c.file)
                and (source is None or c.source == source)]

    def skipped(self):
        return [c for c in self.p.clips if c.category == "skipped"]

    def classify(self, clip: ClipRec, category: str):
        if category not in CATEGORIES:
            raise SortError(f"Unknown category {category}")
        src = Path(clip.file)
        if not src.is_file():
            raise SortError(f"File missing: {src}")
        dest_dir = Path(self.p.category_dir(category))
        dest_dir.mkdir(parents=True, exist_ok=True)
        dst = _unique(dest_dir / src.name)
        copy = self.p.sort.copy_instead_of_move
        if copy:
            shutil.copy2(src, dst)
        else:
            shutil.move(str(src), str(dst))
        self.p.sort_history.append({"id": clip.id, "from": str(src), "to": str(dst),
                                    "prev": clip.category, "copy": copy})
        clip.file, clip.category = str(dst), category
        self.p.bump("sorted")
        return dst

    def skip(self, clip: ClipRec):
        self.p.sort_history.append({"id": clip.id, "from": clip.file, "to": clip.file,
                                    "prev": clip.category, "copy": False})
        clip.category = "skipped"

    def restore_skipped(self):
        n = 0
        for c in self.skipped():
            c.category = ""
            n += 1
        return n

    def undo(self):
        """يتراجع عن آخر عملية. يعيد المقطع أو None."""
        while self.p.sort_history:
            op = self.p.sort_history.pop()
            clip = self.p.clip(op["id"])
            if not clip:
                continue
            if op["from"] != op["to"]:
                cur, back = Path(op["to"]), Path(op["from"])
                if op.get("copy"):
                    if cur.exists():   # النسخة التي أنشأناها تنتقل إلى .trash بدل الحذف النهائي
                        trash = Path(self.p.trash_dir)
                        trash.mkdir(parents=True, exist_ok=True)
                        shutil.move(str(cur), str(_unique(trash / cur.name)))
                    clip.file = str(back)
                elif cur.exists():
                    back.parent.mkdir(parents=True, exist_ok=True)
                    target = _unique(back) if back.exists() else back
                    shutil.move(str(cur), str(target))
                    clip.file = str(target)
                if clip.category in CATEGORIES:
                    self.p.bump("sorted", -1)
            clip.category = op["prev"]
            return clip
        return None
