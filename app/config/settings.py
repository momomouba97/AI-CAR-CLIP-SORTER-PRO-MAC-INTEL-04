import json
import os

from .paths import app_support_dir
from .schema import AppSettings, load_dc


def settings_file():
    return app_support_dir() / "settings.json"


def load_settings() -> AppSettings:
    try:
        return load_dc(AppSettings, json.loads(settings_file().read_text("utf-8")))
    except Exception:
        return AppSettings()


def save_settings(s: AppSettings) -> None:
    f = settings_file()
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(s.to_dict(), ensure_ascii=False, indent=2), "utf-8")
    os.replace(tmp, f)
