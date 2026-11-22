"""تخزين الأسرار في macOS Keychain عبر مكتبة keyring. لا يوجد أي بديل نصي."""
from .. import APP_ID


class KeychainError(RuntimeError):
    pass


class SecretStore:
    def __init__(self, backend=None, service=APP_ID):
        self._backend = backend
        self.service = service

    def _kr(self):
        if self._backend is not None:
            return self._backend
        try:
            import keyring
            from keyring.backends import fail
            if isinstance(keyring.get_keyring(), fail.Keyring):
                raise KeychainError("No secure keychain backend available")
            return keyring
        except KeychainError:
            raise
        except Exception as e:
            raise KeychainError(str(e))

    def get(self, key):
        try:
            return self._kr().get_password(self.service, key)
        except KeychainError:
            raise
        except Exception as e:
            raise KeychainError(str(e))

    def set(self, key, value):
        try:
            self._kr().set_password(self.service, key, value)
        except KeychainError:
            raise
        except Exception as e:
            raise KeychainError(str(e))

    def delete(self, key):
        try:
            self._kr().delete_password(self.service, key)
        except Exception:
            pass

    def backend_name(self):
        """اسم الـ backend كاملاً، مثل keyring.backends.macOS.Keyring."""
        try:
            kr = self._kr()
            b = kr.get_keyring() if hasattr(kr, "get_keyring") else kr
            return f"{type(b).__module__}.{type(b).__name__}"
        except Exception as e:
            return f"unavailable ({e})"
