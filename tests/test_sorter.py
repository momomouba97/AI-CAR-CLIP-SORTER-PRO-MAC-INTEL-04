from pathlib import Path

import pytest

from app.config.schema import SortCfg
from app.core.hooks import Hooks
from app.core.project import Project, ClipRec
from app.sorter.sorter import Sorter, SortError
from app.sorter import assist


def make_project(tmp_path, n=3):
    p = Project("t", str(tmp_path / "p"))
    p.ensure_dirs()
    for i in range(n):
        f = Path(p.paths.export) / f"c{i}.mp4"
        f.write_bytes(b"x" * 10)
        p.clips.append(ClipRec(f"id{i}", "/s.mp4", i, 0, 1, name=f"c{i}", file=str(f), exported=True))
    return p


def test_classify_and_undo(tmp_path):
    p = make_project(tmp_path)
    s = Sorter(p)
    c = p.clips[0]
    dst = s.classify(c, "moving")
    assert dst.parent.name == "MovingCars" and dst.exists() and c.category == "moving"
    assert len(s.pending()) == 2
    back = s.undo()
    assert back is c and c.category == "" and Path(c.file).parent.name == "Exports"
    assert len(s.pending()) == 3


def test_never_overwrites(tmp_path):
    p = make_project(tmp_path, 1)
    s = Sorter(p)
    (Path(p.paths.stopping) / "c0.mp4").write_bytes(b"keep")
    dst = s.classify(p.clips[0], "stopping")
    assert dst.name == "c0_1.mp4"
    assert (Path(p.paths.stopping) / "c0.mp4").read_bytes() == b"keep"


def test_skip_restore(tmp_path):
    p = make_project(tmp_path)
    s = Sorter(p)
    s.skip(p.clips[0])
    assert len(s.pending()) == 2 and len(s.skipped()) == 1
    assert s.restore_skipped() == 1 and len(s.pending()) == 3


def test_copy_mode_undo_goes_to_trash(tmp_path):
    p = make_project(tmp_path, 1)
    p.sort.copy_instead_of_move = True
    s = Sorter(p)
    orig = Path(p.clips[0].file)
    dst = s.classify(p.clips[0], "excluded")
    assert orig.exists() and dst.exists()
    s.undo()
    assert orig.exists() and not dst.exists() and list(Path(p.trash_dir).glob("*.mp4"))


def test_errors(tmp_path):
    p = make_project(tmp_path, 1)
    with pytest.raises(SortError):
        Sorter(p).classify(p.clips[0], "bogus")
    Path(p.clips[0].file).unlink()
    with pytest.raises(SortError):
        Sorter(p).classify(p.clips[0], "moving")


def test_classify_score_thresholds():
    cfg = SortCfg()
    assert assist.classify_score(0.2, cfg).label == "moving"
    assert assist.classify_score(0.0, cfg).label == "stopping"
    assert assist.classify_score(0.02, cfg).label == ""
    assert assist.classify_score(0.2, cfg).confidence >= cfg.assist_min_conf


def _moving_video(path, moving):
    import cv2
    import numpy as np
    w = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 25, (320, 240))
    rng = np.random.default_rng(1)
    bg = (rng.random((240, 320, 3)) * 80 + 60).astype("uint8")
    for i in range(75):
        f = bg.copy()
        x = (i * 6) % 250 if moving else 100
        f[90:150, x:x + 70] = (30, 200, 240)
        f[100:140, x + 10:x + 60] = (200, 40, 40)
        w.write(f)
    w.release()


def test_motion_assist_on_synthetic(tmp_path):
    a, b = tmp_path / "move.mp4", tmp_path / "still.mp4"
    _moving_video(a, True)
    _moving_video(b, False)
    ma, mb = assist.motion_score(a), assist.motion_score(b)
    assert ma > mb
    assert assist.classify_score(mb, SortCfg()).label == "stopping"
