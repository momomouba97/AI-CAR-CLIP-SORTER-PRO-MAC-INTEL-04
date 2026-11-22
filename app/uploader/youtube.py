"""رفع YouTube عبر Data API v3 (OAuth + رفع قابل للاستئناف). الرموز في Keychain فقط."""
import json
import socket
import time

from ..core.hooks import Cancelled
from ..security.keychain import SecretStore
from .base import UploadPlatform, UploadMeta, UploadError, QuotaExceeded

SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube.readonly"]
KEY_CLIENT = "youtube_client_config"
KEY_TOKEN = "youtube_token"
RETRY_STATUS = {500, 502, 503, 504}
CHUNK = 8 * 1024 * 1024


class YouTubePlatform(UploadPlatform):
    name = "youtube"
    supports_pause = True       # الإيقاف بين الأجزاء؛ الجلسة تبقى قابلة للاستئناف
    supports_drafts = False     # الواجهة لا تدعم المسودات: Private هو الأقرب

    def __init__(self, secrets: SecretStore):
        self.secrets = secrets
        self._label = ""

    # ---- الإعداد ----
    def has_client_config(self) -> bool:
        try:
            return bool(self.secrets.get(KEY_CLIENT))
        except Exception:
            return False

    def set_client_config(self, path):
        data = json.loads(open(path, "r", encoding="utf-8").read())
        if not ("installed" in data or "web" in data):
            raise UploadError("Invalid client_secret.json (expected a Desktop OAuth client)")
        self.secrets.set(KEY_CLIENT, json.dumps(data))

    def _credentials(self):
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        raw = self.secrets.get(KEY_TOKEN)
        if not raw:
            return None
        creds = Credentials.from_authorized_user_info(json.loads(raw), SCOPES)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            self.secrets.set(KEY_TOKEN, creds.to_json())
        return creds

    def is_authorized(self) -> bool:
        try:
            c = self._credentials()
            return bool(c and (c.valid or c.refresh_token))
        except Exception:
            return False

    def authorize(self):
        from google_auth_oauthlib.flow import InstalledAppFlow
        raw = self.secrets.get(KEY_CLIENT)
        if not raw:
            raise UploadError("Import client_secret.json first")
        flow = InstalledAppFlow.from_client_config(json.loads(raw), SCOPES)
        creds = flow.run_local_server(port=0, prompt="consent", open_browser=True)
        self.secrets.set(KEY_TOKEN, creds.to_json())
        self._label = ""
        return self.account_label()

    def disconnect(self):
        self.secrets.delete(KEY_TOKEN)
        self._label = ""

    def _service(self):
        from googleapiclient.discovery import build
        creds = self._credentials()
        if not creds:
            raise UploadError("Not authorized")
        return build("youtube", "v3", credentials=creds, cache_discovery=False)

    def channels(self):
        resp = self._service().channels().list(part="snippet", mine=True).execute()
        return [{"id": i["id"], "title": i["snippet"]["title"]} for i in resp.get("items", [])]

    def account_label(self) -> str:
        if self._label:
            return self._label
        try:
            ch = self.channels()
            self._label = ", ".join(c["title"] for c in ch) or "?"
        except Exception:
            self._label = ""
        return self._label

    # ---- الرفع ----
    def upload(self, path, meta: UploadMeta, hooks, on_progress, retries=3) -> str:
        from googleapiclient.http import MediaFileUpload
        from googleapiclient.errors import HttpError
        yt = self._service()
        body = {"snippet": {"title": meta.title[:100], "description": meta.description[:5000],
                            "tags": meta.tags, "categoryId": meta.category_id},
                "status": {"privacyStatus": meta.privacy, "selfDeclaredMadeForKids": False}}
        media = MediaFileUpload(str(path), chunksize=CHUNK, resumable=True, mimetype="video/*")
        req = yt.videos().insert(part="snippet,status", body=body, media_body=media)
        response, attempts, t0 = None, 0, time.monotonic()
        while response is None:
            hooks.check()
            try:
                status, response = req.next_chunk()
                attempts = 0
                if status:
                    el = max(1e-3, time.monotonic() - t0)
                    on_progress(status.progress(), status.resumable_progress / el)
            except Cancelled:
                raise
            except HttpError as e:
                code = getattr(e.resp, "status", 0)
                reason = str(e)
                if code == 403 and ("quota" in reason.lower() or "uploadLimit" in reason):
                    raise QuotaExceeded("YouTube quota/upload limit reached")
                if code in RETRY_STATUS and attempts < retries:
                    attempts += 1
                    self._backoff(attempts, hooks)
                    continue
                raise UploadError(f"YouTube error {code}: {reason[:200]}")
            except (ConnectionError, TimeoutError, socket.error, OSError) as e:
                if attempts < retries:
                    attempts += 1
                    hooks.log(f"Connection problem, retry {attempts}/{retries}: {e}", "warning")
                    self._backoff(attempts, hooks)
                    continue
                raise UploadError(f"Connection failed: {e}")
        vid = response.get("id")
        if not vid:
            raise UploadError("YouTube did not return a video id")
        check = yt.videos().list(part="status", id=vid).execute()   # تأكيد وجود الفيديو فعلاً
        if not check.get("items"):
            raise UploadError("Upload could not be confirmed by YouTube")
        on_progress(1.0, 0)
        return vid

    @staticmethod
    def _backoff(attempt, hooks):
        end = time.monotonic() + min(30, 2 ** attempt)
        while time.monotonic() < end:
            hooks.check()
            time.sleep(0.2)


PLATFORMS = {"youtube": YouTubePlatform}
