import os
import time
from pathlib import Path

from ..core.hooks import Hooks, Cancelled
from ..core.progress import fmt_size
from ..core.project import Project, ClipRec
from .base import UploadMeta, UploadNotAllowed, UploadPlatform, QuotaExceeded


class _Safe(dict):
    def __missing__(self, k):
        return "{" + k + "}"


def build_meta(project: Project, clip: ClipRec) -> UploadMeta:
    cfg = project.upload
    fmt = _Safe(project=project.name, name=clip.name or Path(clip.file).stem, index=clip.index,
                source=Path(clip.source).stem, category=clip.category)
    return UploadMeta(title=cfg.title_template.format_map(fmt), description=cfg.description.format_map(fmt),
                      tags=list(cfg.tags), privacy=cfg.privacy, category_id=cfg.category_id)


def select_clips(project: Project, only_selected=None, source=None):
    cfg = project.upload
    only = cfg.only_selected if only_selected is None else only_selected
    return [c for c in project.clips if c.exported and not c.uploaded and c.file and os.path.isfile(c.file)
            and (c.selected or not only) and (source is None or c.source == source)]


def assert_allowed(project: Project, platform: UploadPlatform):
    cfg = project.upload
    if not cfg.enabled:
        raise UploadNotAllowed("Auto Upload is disabled")
    if not cfg.consent:
        raise UploadNotAllowed("User consent for uploading is missing")
    if not platform.is_authorized():
        raise UploadNotAllowed("Account is not linked")


def run_uploads(project: Project, platform: UploadPlatform, clips, hooks: Hooks, save=None):
    assert_allowed(project, platform)
    cfg = project.upload
    queue = clips[:max(1, cfg.max_queue)]
    res = {"ok": 0, "failed": 0, "remaining": max(0, len(clips) - len(queue)), "errors": []}
    for i, clip in enumerate(queue):
        hooks.check()
        entry = {"ts": time.time(), "file": clip.file, "status": "uploading", "video_id": "", "error": ""}
        project.uploads_log.append(entry)
        size = fmt_size(os.path.getsize(clip.file))

        def on_prog(frac, speed, i=i, clip=clip):
            hooks.progress("upload", (i + frac) / len(queue),
                           f"{i + 1}/{len(queue)} • {Path(clip.file).name} ({size}) • "
                           f"{int(frac * 100)}% • {fmt_size(speed)}/s")
        try:
            vid = platform.upload(clip.file, build_meta(project, clip), hooks, on_prog, cfg.retries)
            clip.uploaded, clip.video_id = True, vid
            entry.update(status="done", video_id=vid)
            project.bump("uploaded")
            res["ok"] += 1
            hooks.log(f"Uploaded {Path(clip.file).name} → {vid}", "success")
        except Cancelled:
            entry.update(status="cancelled")
            raise
        except QuotaExceeded as e:
            entry.update(status="failed", error=str(e))
            res["failed"] += 1
            res["errors"].append(str(e))
            hooks.log(str(e), "error")
            res["remaining"] += len(queue) - i - 1
            if save:
                save()
            break
        except Exception as e:
            entry.update(status="failed", error=str(e))
            res["failed"] += 1
            res["errors"].append(f"{Path(clip.file).name}: {e}")
            hooks.log(f"Upload failed {Path(clip.file).name}: {e}", "error")
        if save:
            save()
    return res
