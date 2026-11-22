import time


class Eta:
    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self.t0 = clock()

    def elapsed(self):
        return self._clock() - self.t0

    def remaining(self, frac):
        """الوقت المتبقي بالثواني، أو None إذا تعذر التقدير."""
        if frac is None or frac < 0.02:
            return None
        return self.elapsed() * (1 - frac) / frac


def fmt_duration(sec):
    if sec is None:
        return "--:--"
    sec = int(max(0, sec))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def fmt_size(n):
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
