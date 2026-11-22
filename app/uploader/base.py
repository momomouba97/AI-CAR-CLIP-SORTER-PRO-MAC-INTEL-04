from dataclasses import dataclass, field


@dataclass
class UploadMeta:
    title: str
    description: str = ""
    tags: list = field(default_factory=list)
    privacy: str = "private"
    category_id: str = "2"


class UploadError(Exception):
    pass


class UploadNotAllowed(UploadError):
    pass


class QuotaExceeded(UploadError):
    pass


class UploadPlatform:
    """واجهة موحدة لأي منصة رفع. أضف منصة جديدة بوراثة هذه الفئة وتسجيلها في PLATFORMS."""
    name = "base"
    supports_pause = False
    supports_drafts = False

    def is_authorized(self) -> bool:
        raise NotImplementedError

    def account_label(self) -> str:
        return ""

    def authorize(self):
        raise NotImplementedError

    def disconnect(self):
        raise NotImplementedError

    def upload(self, path, meta: UploadMeta, hooks, on_progress, retries: int = 3) -> str:
        """يعيد معرّف الفيديو بعد تأكيد المنصة فقط."""
        raise NotImplementedError
