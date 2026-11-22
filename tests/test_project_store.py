import json
from pathlib import Path

from app.core.project import Project, VideoRec, SceneRec, ClipRec
from app.storage import project_store as st


def test_roundtrip_and_backup(tmp_path):
    p = st.create_project("demo", tmp_path)
    p.videos.append(VideoRec("/a.mp4", duration=9, scenes=[SceneRec(0, 3), SceneRec(3, 9, False)]))
    p.clips.append(ClipRec("c1", "/a.mp4", 1, 0, 3, name="n", exported=True, category="moving"))
    p.analysis.threshold = 31
    p.upload.consent = True
    p.bump("exported", 2)
    st.save_project(p)
    q = st.load_project(tmp_path / "demo")
    assert q.analysis.threshold == 31 and q.upload.consent is True
    assert q.videos[0].scenes[1].keep is False and q.clips[0].category == "moving"
    assert q.stats()["moving"] == 1 and q.daily
    st.save_project(q)
    (tmp_path / "demo" / "project.json").write_text("{broken")
    assert st.load_project(tmp_path / "demo").name == "demo"     # الاستعادة من النسخة الاحتياطية


def test_each_project_has_own_paths(tmp_path):
    a, b = st.create_project("a", tmp_path), st.create_project("b", tmp_path)
    assert a.paths.export != b.paths.export and Path(a.paths.moving).is_dir()


def test_duplicate_and_settings(tmp_path):
    a = st.create_project("a", tmp_path)
    a.analysis.prefix = "zz"
    a.upload.consent = True
    a.videos.append(VideoRec("/x.mp4", scenes=[SceneRec(0, 1)]))
    a.clips.append(ClipRec("c", "/x.mp4", 1, 0, 1))
    b = st.duplicate_project(a, "b", tmp_path)
    assert b.analysis.prefix == "zz" and not b.clips and len(b.videos) == 1 and b.upload.consent is False
    dest = tmp_path / "s.json"
    st.export_settings(a, dest)
    assert "consent" not in json.loads(dest.read_text())["upload"]
    c = st.create_project("c", tmp_path)
    st.import_settings(c, dest)
    assert c.analysis.prefix == "zz"


def test_series_daily_weekly():
    import datetime as dt
    p = Project("t", "/tmp/x")
    today = dt.date(2026, 11, 21)
    p.bump("exported", 3, today.isoformat())
    p.bump("sorted", 1, (today - dt.timedelta(days=2)).isoformat())
    labels, s = p.series("daily", today)
    assert len(labels) == 7 and s["exported"][-1] == 3 and s["sorted"][4] == 1
    labels, s = p.series("weekly", today)
    assert len(labels) == 8 and s["exported"][-1] == 3
