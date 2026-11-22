import threading
import time


class Cancelled(Exception):
    pass


class Hooks:
    """قناة موحدة للسجل والتقدم والإيقاف المؤقت والإلغاء."""

    def __init__(self, log=None, progress=None):
        self._log = log or (lambda level, msg: None)
        self._progress = progress or (lambda task, frac, detail: None)
        self.cancel = threading.Event()
        self.paused = threading.Event()

    def log(self, msg, level="info"):
        self._log(level, msg)

    def progress(self, task, frac=None, detail=""):
        self._progress(task, frac, detail)

    def check(self):
        while self.paused.is_set() and not self.cancel.is_set():
            time.sleep(0.1)
        if self.cancel.is_set():
            raise Cancelled()
