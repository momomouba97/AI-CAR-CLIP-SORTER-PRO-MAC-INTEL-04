import os
import sys
from pathlib import Path

from .. import APP_ID


def app_support_dir() -> Path:
    override = os.environ.get("AICCS_HOME")
    if override:
        p = Path(override)
    elif sys.platform == "darwin":
        p = Path.home() / "Library" / "Application Support" / APP_ID
    else:
        p = Path.home() / ".aiccs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def logs_dir() -> Path:
    p = app_support_dir() / "logs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def default_projects_dir() -> Path:
    return Path.home() / "Documents" / "AI CAR CLIP SORTER PRO" / "Projects"


def resource_path(rel: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return base / rel
