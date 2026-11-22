from app.config.schema import AnalysisCfg
from app.core.hooks import Hooks
from app.core.project import Project, VideoRec, SceneRec
from app.splitter import splitter as sp
from app.video import info


def test_fixed_segments():
    segs = sp.fixed_segments(25, 10)
    assert segs == [(0, 10), (10, 20), (20, 25)]


def test_merge_short_and_drop():
    cfg = AnalysisCfg(min_scene_len=1, min_valid_len=0.3, max_scene_len=0)
    out = sp.post_process([(0, 0.4), (0.4, 5), (5, 5.5), (5.5, 9)], cfg)
    assert out[0][0] == 0 and out[-1][1] == 9
    assert all(e - s >= 1 - 1e-6 for s, e in out)


def test_split_long_keeps_order_and_coverage():
    out = sp.split_long([(0, 25)], 10)
    assert len(out) == 3 and out[0][0] == 0 and out[-1][1] == 25
    assert all(b[0] == a[1] for a, b in zip(out, out[1:]))
    assert all(e - s <= 10 + 1e-6 for s, e in out)


def test_group_to_target():
    out = sp.group_to_target([(0, 2), (2, 4), (4, 6), (6, 20)], 5)
    assert out[0] == (0, 6) or out[0] == (0, 4)
    assert out[-1][1] == 20


def test_merge_scenes_adjacent_only():
    sc = [SceneRec(0, 1), SceneRec(1, 2), SceneRec(2, 3), SceneRec(3, 4)]
    m = sp.merge_scenes(sc, [1, 2])
    assert [(s.start, s.end) for s in m] == [(0, 1), (1, 3), (3, 4)]
    import pytest
    with pytest.raises(ValueError):
        sp.merge_scenes(sc, [0, 2])


def test_detect_real_video(video3):
    meta = info.probe(video3)
    v = VideoRec(video3, **meta)
    segs = sp.analyze_video(v, AnalysisCfg(min_scene_len=1), Hooks())
    assert len(segs) == 3
    assert abs(segs[1][0] - 3.0) < 0.2


def test_adaptive_and_fixed_modes(video3):
    v = VideoRec(video3, **info.probe(video3))
    assert len(sp.analyze_video(v, AnalysisCfg(mode="fixed", fixed_len=4), Hooks())) == 3
    assert len(sp.analyze_video(v, AnalysisCfg(detector="adaptive"), Hooks())) >= 1


def test_plan_clips_preserves_exported(tmp_path, video3):
    p = Project("t", str(tmp_path / "p"))
    v = VideoRec(video3, **info.probe(video3))
    p.add_video(v)
    sp.set_scenes(v, [(0, 3), (3, 6), (6, 9)])
    assert sp.plan_clips(p, v) == 3
    p.clips[0].exported = True
    v.scenes[1].keep = False
    assert sp.plan_clips(p, v) == 1   # المقطع 3 غير المصدّر يُعاد تخطيطه، والمقطع 2 مستبعد
    assert [c.index for c in p.clips] == [1, 3]
    assert p.clips[0].name == "clip_three_0001"


def test_corrupt_video(tmp_path):
    bad = tmp_path / "bad.mp4"
    bad.write_bytes(b"not a video")
    import pytest
    with pytest.raises(info.CorruptVideoError):
        info.probe(str(bad))
