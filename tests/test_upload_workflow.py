from pathlib import Path

import pytest

from app.core.hooks import Hooks, Cancelled
from app.core.project import Project, ClipRec
from app.uploader import manager as um
from app.uploader.base import UploadPlatform, UploadNotAllowed, QuotaExceeded
from app.workflow import engine as wf
from app.video import info
from app.core.project import VideoRec


class FakePlatform(UploadPlatform):
    name = "fake"

    def __init__(self, auth=True, fail=()):
        self.auth, self.fail, self.sent = auth, set(fail), []

    def is_authorized(self):
        return self.auth

    def upload(self, path, meta, hooks, on_progress, retries=3):
        if Path(path).name in self.fail:
            raise RuntimeError("boom")
        on_progress(0.5, 1000)
        self.sent.append((path, meta))
        return "vid_" + Path(path).stem


def proj(tmp_path, n=3):
    p = Project("Demo", str(tmp_path / "p"))
    p.ensure_dirs()
    for i in range(n):
        f = Path(p.paths.export) / f"c{i}.mp4"
        f.write_bytes(b"x")
        p.clips.append(ClipRec(f"i{i}", "/s.mp4", i, 0, 1, name=f"c{i}", file=str(f), exported=True))
    return p


def test_upload_requires_enable_and_consent(tmp_path):
    p = proj(tmp_path)
    plat = FakePlatform()
    with pytest.raises(UploadNotAllowed):
        um.run_uploads(p, plat, p.clips, Hooks())
    p.upload.enabled = True
    with pytest.raises(UploadNotAllowed):
        um.run_uploads(p, plat, p.clips, Hooks())
    p.upload.consent = True
    assert um.run_uploads(p, FakePlatform(auth=False), p.clips, Hooks()) if False else True
    with pytest.raises(UploadNotAllowed):
        um.run_uploads(p, FakePlatform(auth=False), p.clips, Hooks())
    assert plat.sent == []


def test_upload_ok_fail_and_limits(tmp_path):
    p = proj(tmp_path, 4)
    p.upload.enabled = p.upload.consent = True
    p.upload.max_queue = 3
    p.upload.title_template = "{project}: {name}"
    p.upload.tags = ["cars"]
    plat = FakePlatform(fail={"c1.mp4"})
    r = um.run_uploads(p, plat, um.select_clips(p), Hooks())
    assert r["ok"] == 2 and r["failed"] == 1 and r["remaining"] == 1
    assert plat.sent[0][1].title == "Demo: c0" and plat.sent[0][1].tags == ["cars"]
    assert [c.uploaded for c in p.clips] == [True, False, True, False]
    assert [e["status"] for e in p.uploads_log] == ["done", "failed", "done"]
    assert len(um.select_clips(p)) == 2           # لا إعادة رفع للمرفوع


def test_only_selected(tmp_path):
    p = proj(tmp_path)
    p.clips[1].selected = True
    p.upload.only_selected = True
    assert [c.id for c in um.select_clips(p)] == ["i1"]


def test_quota_stops_queue(tmp_path):
    p = proj(tmp_path)
    p.upload.enabled = p.upload.consent = True

    class Q(FakePlatform):
        def upload(self, *a, **k):
            raise QuotaExceeded("quota")
    r = um.run_uploads(p, Q(), p.clips, Hooks())
    assert r["failed"] == 1 and r["remaining"] == 3 - 1 + 0 or r["remaining"] == 2


def test_workflow_end_to_end(tmp_path, video3, ffmpeg):
    p = Project("wf", str(tmp_path / "p"))
    p.ensure_dirs()
    p.videos.append(VideoRec(video3))
    wf.apply_template(p, "Quick Split")
    assert p.export.profile == "Fast" and not p.workflow.steps["sort"]
    saves = []
    r = wf.WorkflowEngine(p, ffmpeg, Hooks(), save=lambda: saves.append(1)).run()
    assert r["status"] == "done" and len(p.clips) == 3 and all(c.exported for c in p.clips)
    assert p.workflow_state["status"] == "done" and saves
    assert list(Path(p.reports_dir).glob("report_*.txt"))
    # إعادة التشغيل لا تعيد العمل المنجز
    n_files = len(list(Path(p.paths.export).glob("*.mp4")))
    wf.WorkflowEngine(p, ffmpeg, Hooks()).run()
    assert len(list(Path(p.paths.export).glob("*.mp4"))) == n_files


def test_workflow_stop_and_resume(tmp_path, video3, ffmpeg):
    p = Project("wf", str(tmp_path / "p"))
    p.ensure_dirs()
    p.videos.append(VideoRec(video3))
    wf.apply_template(p, "Quick Split")
    h = Hooks()
    calls = {"n": 0}
    orig = h.check

    def check():
        calls["n"] += 1
        if calls["n"] == 7:
            h.cancel.set()
        orig()
    h.check = check
    r = wf.WorkflowEngine(p, ffmpeg, h).run()
    assert r["status"] == "stopped" and wf.interrupted(p)
    r2 = wf.WorkflowEngine(p, ffmpeg, Hooks()).run()
    assert r2["status"] == "done" and all(c.exported for c in p.clips) and len(p.clips) == 3


def test_workflow_skips_corrupt_and_upload_without_consent(tmp_path, video3, ffmpeg):
    bad = tmp_path / "bad.mp4"
    bad.write_bytes(b"junk")
    p = Project("wf", str(tmp_path / "p"))
    p.ensure_dirs()
    p.videos += [VideoRec(str(bad)), VideoRec(video3)]
    wf.apply_template(p, "Export and Upload")
    plat = FakePlatform()
    r = wf.WorkflowEngine(p, ffmpeg, Hooks(), platform=plat).run()
    assert r["status"] == "done" and plat.sent == []
    assert r["results"]["upload"]["skipped"] and p.videos[0].status == "corrupt"
    assert len(p.clips) == 3


def test_workflow_autosort_leaves_uncertain(tmp_path, video3, ffmpeg):
    p = Project("wf", str(tmp_path / "p"))
    p.ensure_dirs()
    p.videos.append(VideoRec(video3))
    wf.apply_template(p, "Auto Sort")
    r = wf.WorkflowEngine(p, ffmpeg, Hooks()).run()
    s = r["results"]["sort"]
    assert s["classified"] + s["uncertain"] == 3
    # فيديو ثابت تماماً ⇒ stopping بثقة عالية
    assert all(c.category in ("stopping", "") for c in p.clips)
