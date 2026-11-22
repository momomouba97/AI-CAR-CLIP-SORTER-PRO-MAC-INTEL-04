from pathlib import Path

from conftest import make_video
from app.core.hooks import Hooks
from app.core.project import Project
from app.video.info import natural_key, scan_folder
from app.workflow import engine as wf


def test_natural_order():
    names = ["v10.mp4", "v2.mp4", "v1.mp4"]
    assert sorted(names, key=natural_key) == ["v1.mp4", "v2.mp4", "v10.mp4"]


def test_folder_queue_one_by_one_in_order(tmp_path, ffmpeg):
    src = tmp_path / "incoming"
    src.mkdir()
    for n in ("v10", "v2", "v1"):
        make_video(src / f"{n}.mp4", ffmpeg, colors=("red", "blue"), d=2)
    p = Project("q", str(tmp_path / "p"))
    p.ensure_dirs()
    wf.apply_template(p, "Quick Split")
    p.workflow.queue_folder = str(src)
    events = []
    h = Hooks(log=lambda lvl, m: events.append(m))
    r = wf.WorkflowEngine(p, ffmpeg, h).run()
    assert r["status"] == "done"
    assert [Path(v.path).name for v in p.videos] == ["v1.mp4", "v2.mp4", "v10.mp4"]
    assert len(p.clips) == 6 and all(c.exported for c in p.clips)
    assert all("complete" in v.done_steps for v in p.videos)
    # الفيديو التالي لا يُستورد إلا بعد تصدير السابق
    imports = [i for i, m in enumerate(events) if m.startswith("Auto-import")]
    exports = [i for i, m in enumerate(events) if m.startswith("Exported: clip_v1_")]
    assert imports[1] > max(exports)
    # إعادة التشغيل لا تعيد المعالجة
    n = len(list(Path(p.paths.export).glob("*.mp4")))
    r2 = wf.WorkflowEngine(p, ffmpeg, Hooks()).run()
    assert r2["status"] == "done" and len(list(Path(p.paths.export).glob("*.mp4"))) == n


def test_queue_picks_up_new_files_on_rerun(tmp_path, ffmpeg):
    src = tmp_path / "incoming"
    src.mkdir()
    make_video(src / "a1.mp4", ffmpeg, colors=("red", "blue"), d=2)
    p = Project("q", str(tmp_path / "p"))
    p.ensure_dirs()
    wf.apply_template(p, "Quick Split")
    p.workflow.queue_folder = str(src)
    wf.WorkflowEngine(p, ffmpeg, Hooks()).run()
    make_video(src / "a2.mp4", ffmpeg, colors=("green", "blue"), d=2)
    wf.WorkflowEngine(p, ffmpeg, Hooks()).run()
    assert len(p.videos) == 2 and len(p.clips) == 4 and all(c.exported for c in p.clips)
