import pytest

from app.core.progress import Eta, fmt_duration, fmt_size
from app.security.keychain import SecretStore, KeychainError


def test_eta():
    t = [0.0]
    e = Eta(clock=lambda: t[0])
    assert e.remaining(0.0) is None and e.remaining(None) is None
    t[0] = 10
    assert e.remaining(0.5) == 10
    assert fmt_duration(None) == "--:--" and fmt_duration(75) == "01:15" and fmt_duration(3700) == "1:01:40"
    assert fmt_size(1536) == "1.5 KB"


class Fake:
    def __init__(self):
        self.d = {}

    def get_password(self, s, k):
        return self.d.get((s, k))

    def set_password(self, s, k, v):
        self.d[(s, k)] = v

    def delete_password(self, s, k):
        self.d.pop((s, k), None)


def test_secret_store_roundtrip():
    s = SecretStore(Fake())
    s.set("k", "v")
    assert s.get("k") == "v"
    s.delete("k")
    assert s.get("k") is None


def test_secret_store_fails_closed():
    class Boom:
        def get_password(self, *a):
            raise RuntimeError("locked")
    with pytest.raises(KeychainError):
        SecretStore(Boom()).get("k")
