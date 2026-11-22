from pathlib import Path

from app.core.hooks import Hooks
from app.core.project import Project, VideoRec, SceneRec
from app.exporter import exporter as ex
from app.splitter import splitter as sp
from app.video import info


def mk(tmp_path, video3):
    p = Project("t", str(tmp_path / "p"))
    p.ensure_dirs()
    v = VideoRec(video3, **info.probe(video3))
    p.add_video(v)
    sp.set_scenes(v, [(0, 3), (3, 6), (6, 9)])
    sp.plan_clips(p, v)
    return p


def test_build_command_options():
    from app.config.schema import ExportCfg
    c = ExportCfg(codec="h265", height=720, fps=30, keep_audio=False)
    cmd = ex.build_command("ff", "a.mp4", "b.mp4", 1.5, 2, c, 2)
    s = " ".join(cmd)
    assert "libx265" in s and "hvc1" in s and "scale=-2:720" in s and "-r 30" in s and "-an" in s
    assert "-map 0:a:0?" not in s
    c2 = ExportCfg(fast_copy=True)
    assert "-c copy" in " ".join(ex.build_command("ff", "a", "b", 0, 1, c2))


def test_profiles():
    from app.config.schema import ExportCfg
    c = ExportCfg()
    ex.apply_profile(c, "Maximum Quality")
    assert c.crf == 16 and c.speed == "slower"


def test_export_real_clips(tmp_path, video3, ffmpeg):
    p = mk(tmp_path, video3)
    events = []
    h = Hooks(progress=lambda t, f, d: events.append((t, f)))
    r = ex.export_clips(ffmpeg, p, p.clips, h)
    assert r["done"] == 3 and r["failed"] == 0
    files = sorted(Path(p.paths.export).glob("*.mp4"))
    assert len(files) == 3
    d = info.probe(str(files[0]))["duration"]
    assert 2.7 < d < 3.3
    assert any(f is not None and 0 < f <= 1 for _, f in events)
    assert not list(Path(p.paths.export).glob("*.part.*"))
    assert (Path(p.paths.export) / "clips_index.json").exists()


def test_existing_policies(tmp_path, video3, ffmpeg):
    p = mk(tmp_path, video3)
    ex.export_clips(ffmpeg, p, p.clips[:1], Hooks())
    first = Path(p.clips[0].file)
    mtime = first.stat().st_mtime_ns
    p.clips[0].exported = False
    p.export.existing = "skip"
    ex.export_clips(ffmpeg, p, p.clips[:1], Hooks())
    assert first.stat().st_mtime_ns == mtime and p.clips[0].exported
    p.clips[0].exported = False
    p.export.existing = "rename"
    ex.export_clips(ffmpeg, p, p.clips[:1], Hooks())
    assert Path(p.clips[0].file).name.endswith("_1.mp4")
    p.clips[0].exported = False
    p.export.existing = "overwrite"
    p.clips[0].file = ""
    ex.export_clips(ffmpeg, p, p.clips[:1], Hooks())
    assert list(Path(p.trash_dir).glob("*.mp4"))       # النسخة القديمة لم تُحذف نهائياً


def test_cancel_cleans_partial(tmp_path, video3, ffmpeg):
    from app.core.hooks import Cancelled
    import pytest
    p = mk(tmp_path, video3)
    h = Hooks()
    h.cancel.set()
    with pytest.raises(Cancelled):
        ex.export_clips(ffmpeg, p, p.clips, h)
    assert not list(Path(p.paths.export).glob("*.part.*"))


def test_disk_full(tmp_path, video3, ffmpeg, monkeypatch):
    import pytest
    p = mk(tmp_path, video3)
    monkeypatch.setattr(ex.shutil, "disk_usage", lambda d: type("U", (), {"free": 1000})())
    with pytest.raises(ex.DiskFullError):
        ex.export_clips(ffmpeg, p, p.clips, Hooks())


def test_h265_only_if_available(ffmpeg):
    from app.config.schema import ExportCfg
    from app.core.ffmpeg_util import available_encoders
    if "libx265" not in available_encoders(ffmpeg):
        import pytest
        with pytest.raises(ex.ExportError):
            ex.check_encoder(ffmpeg, ExportCfg(codec="h265"))
