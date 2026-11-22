"""إعدادات التطبيق والمشروع (dataclasses قابلة للحفظ في JSON)."""
from dataclasses import dataclass, field, fields, asdict

CATEGORIES = ("moving", "stopping", "excluded")
CATEGORY_DIRS = {"moving": "MovingCars", "stopping": "StoppingCars", "excluded": "ExcludedCars"}


def load_dc(cls, data):
    names = {f.name for f in fields(cls)}
    return cls(**{k: v for k, v in (data or {}).items() if k in names})


@dataclass
class AnalysisCfg:
    mode: str = "scene"            # scene | fixed | auto_short
    detector: str = "content"      # content | adaptive
    threshold: float = 27.0
    adaptive_threshold: float = 3.0
    min_scene_len: float = 1.0     # ثوانٍ
    max_scene_len: float = 0.0     # 0 = معطل
    target_len: float = 0.0        # 0 = معطل
    fixed_len: float = 10.0
    min_valid_len: float = 0.3     # أقصر مقطع مسموح
    prefix: str = "clip"


@dataclass
class ExportCfg:
    auto_export: bool = False
    container: str = "mp4"         # mp4 | mov
    codec: str = "h264"            # h264 | h265
    profile: str = "Balanced"
    speed: str = "medium"
    crf: int = 23
    bitrate_k: int = 0             # 0 = استخدم CRF
    fps: int = 0                   # 0 = الأصلي
    height: int = 0                # 0 = الدقة الأصلية
    keep_audio: bool = True
    audio_codec: str = "aac"
    audio_bitrate_k: int = 192
    fast_copy: bool = False        # نسخ بدون إعادة ترميز (أسرع، حدود غير دقيقة)
    existing: str = "rename"       # skip | rename | overwrite
    threads: int = 0               # 0 = نصف أنوية المعالج


@dataclass
class UploadCfg:
    enabled: bool = False          # Enable Auto Upload (المفتاح الرئيسي)
    consent: bool = False          # موافقة المستخدم الصريحة
    after_export: bool = False
    only_selected: bool = False
    max_queue: int = 50
    retries: int = 3
    privacy: str = "private"       # public | unlisted | private
    platform: str = "youtube"
    title_template: str = "{project} - {name}"
    description: str = ""
    tags: list = field(default_factory=list)
    category_id: str = "2"         # Autos & Vehicles


@dataclass
class SortCfg:
    copy_instead_of_move: bool = False
    autoplay: bool = True
    loop: bool = True
    assist: bool = True
    assist_min_conf: float = 0.75
    moving_thr: float = 0.04
    stopping_thr: float = 0.005


@dataclass
class WorkflowCfg:
    template: str = "Full Automation"
    queue_folder: str = ""         # مجلد الاستيراد التلقائي (فارغ = معطل)
    queue_recursive: bool = False
    sequential: bool = True        # فيديو واحد كاملاً ثم الذي يليه
    steps: dict = field(default_factory=lambda: {
        "import": True, "analyze": True, "detect": True, "split": True,
        "export": True, "sort": True, "upload": False, "report": True})


@dataclass
class PathsCfg:
    source: str = ""
    export: str = ""
    moving: str = ""
    stopping: str = ""
    excluded: str = ""
    temp: str = ""


@dataclass
class AppSettings:
    language: str = "ar"
    last_project: str = ""
    recent: list = field(default_factory=list)

    def to_dict(self):
        return asdict(self)
