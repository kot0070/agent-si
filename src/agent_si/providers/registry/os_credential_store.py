"""OS credential store adapter (K04KEY1 lane owned).

Windows Credential Manager binding behind the existing credential-store
port. Entries live under the product namespace, the same namespace the
leftover-keys route already uses: the ProviderCtx docstring names the
app own namespace ``"app:"`` (see provider_routes ProviderCtx
app_prefix docs). Targets are ``"app:"`` + secret_id, with an optional
label suffix (HD live run uses ``"TEST"``) appended as
``"app:"`` + secret_id + ``":"`` + suffix.

Stdlib only (ctypes over advapi32 CredWriteW/CredReadW/CredDeleteW/
CredEnumerateW). Every operation is bounded in time: a worker thread
with a timeout raises TimeoutError, never hangs. Secret values never
appear in repr, errors, audit records or logs (only the entry name).
Non-Windows hosts raise OSError on use; callers fall back to memory.
"""

from __future__ import annotations

import os as _os
from concurrent.futures import ThreadPoolExecutor as _Pool
from typing import Any, Dict, List

APP_NAMESPACE = "app:"

CRED_TYPE_GENERIC = 1
CRED_PERSIST_LOCAL_MACHINE = 2

_DEFAULT_TIMEOUT_S = 5.0


def _is_windows() -> bool:
    return _os.name == "nt"


def _load_advapi32():  # type: ignore[no-untyped-def]
    if not _is_windows():
        raise OSError("OS credential store needs Windows")
    import ctypes as _ct

    try:
        return _ct.windll.advapi32  # type: ignore[attr-defined]
    except Exception as exc:
        raise OSError("OS credential store needs Windows") from exc


def _run_bounded(label: str, fn, timeout_s: float):  # type: ignore[no-untyped-def]
    limit = float(timeout_s if timeout_s and timeout_s > 0 else _DEFAULT_TIMEOUT_S)
    with _Pool(max_workers=1) as pool:
        future = pool.submit(fn)
        try:
            return future.result(timeout=limit)
        except Exception as exc:
            if "Timeout" in type(exc).__name__ or "TimeoutError" in type(exc).__name__:
                raise TimeoutError("OS store op timed out: %s" % (label,)) from None
            # concurrent timeout raises its own TimeoutError subclass
            try:
                import concurrent.futures as _fut

                if isinstance(exc, _fut.TimeoutError):
                    raise TimeoutError(
                        "OS store op timed out: %s" % (label,)) from None
            except TimeoutError:
                raise
            raise


class OSCredentialStore:
    """Credential-store port over Windows Credential Manager.

    Port (matches the ephemeral memory store used by facades):
    seed/has/delete plus set_secret/get_secret and the get/get_secret/
    retrieve/read aliases plus mapping read (``__getitem__`` returns a
    ``{"value": ...}`` mapping so call-time readers work, ``in`` works,
    iteration lists entry names under the namespace).
    """

    def __init__(self, *, label_suffix: str = "",
                 namespace: str = APP_NAMESPACE,
                 timeout_s: float = _DEFAULT_TIMEOUT_S) -> None:
        self._namespace = str(namespace or APP_NAMESPACE)
        self._suffix = str(label_suffix or "").strip()
        try:
            self._timeout = float(timeout_s)
        except (TypeError, ValueError):
            self._timeout = _DEFAULT_TIMEOUT_S
        if not self._timeout or self._timeout <= 0:
            self._timeout = _DEFAULT_TIMEOUT_S

    def _target(self, secret_id: str) -> str:
        sid = str(secret_id)
        if not sid:
            raise ValueError("secret_id is required")
        base = "%s%s" % (self._namespace, sid)
        if self._suffix:
            base = "%s:%s" % (base, self._suffix)
        return base

    def _write_native(self, target: str, value: str) -> None:
        import ctypes as _ct

        adv = _load_advapi32()

        class _FileTime(_ct.Structure):
            _fields_ = [("low", _ct.c_ulong), ("high", _ct.c_ulong)]

        class _Cred(_ct.Structure):
            _fields_ = [
                ("flags", _ct.c_ulong),
                ("cred_type", _ct.c_ulong),
                ("target", _ct.c_wchar_p),
                ("comment", _ct.c_wchar_p),
                ("written", _FileTime),
                ("blob_size", _ct.c_ulong),
                ("blob", _ct.c_void_p),
                ("persist", _ct.c_ulong),
                ("attr_count", _ct.c_ulong),
                ("attrs", _ct.c_void_p),
                ("alias", _ct.c_wchar_p),
                ("user", _ct.c_wchar_p),
            ]

        raw = value.encode("utf-8")
        buf = _ct.create_string_buffer(raw, len(raw) or 1)
        cred = _Cred()
        cred.flags = 0
        cred.cred_type = CRED_TYPE_GENERIC
        cred.target = target
        cred.comment = None
        cred.blob_size = len(raw)
        cred.blob = _ct.cast(buf, _ct.c_void_p) if raw else None
        cred.persist = CRED_PERSIST_LOCAL_MACHINE
        cred.attr_count = 0
        cred.attrs = None
        cred.alias = None
        cred.user = None
        ok = adv.CredWriteW(_ct.byref(cred), 0)
        if not ok:
            raise OSError("OS store write failed for %r" % (target,))
        # keep buf alive until call returns (referenced above)

    def _read_native(self, target: str) -> str:
        import ctypes as _ct

        adv = _load_advapi32()
        adv.CredReadW.argtypes = [
            _ct.c_wchar_p, _ct.c_ulong, _ct.c_ulong,
            _ct.POINTER(_ct.c_void_p)]
        adv.CredReadW.restype = _ct.c_int
        adv.CredFree.argtypes = [_ct.c_void_p]
        out = _ct.c_void_p()
        ok = adv.CredReadW(target, CRED_TYPE_GENERIC, 0, _ct.byref(out))
        if not ok or not out.value:
            raise KeyError(target)
        try:
            # CREDENTIALW layout: blob_size at offset 24 (x64) varies;
            # read via field offsets using a mirror struct.
            class _FileTime(_ct.Structure):
                _fields_ = [("low", _ct.c_ulong), ("high", _ct.c_ulong)]

            class _Cred(_ct.Structure):
                _fields_ = [
                    ("flags", _ct.c_ulong),
                    ("cred_type", _ct.c_ulong),
                    ("target", _ct.c_wchar_p),
                    ("comment", _ct.c_wchar_p),
                    ("written", _FileTime),
                    ("blob_size", _ct.c_ulong),
                    ("blob", _ct.c_void_p),
                    ("persist", _ct.c_ulong),
                    ("attr_count", _ct.c_ulong),
                    ("attrs", _ct.c_void_p),
                    ("alias", _ct.c_wchar_p),
                    ("user", _ct.c_wchar_p),
                ]

            cred = _ct.cast(out, _ct.POINTER(_Cred)).contents
            size = int(cred.blob_size)
            if size <= 0 or not cred.blob:
                return ""
            data = _ct.string_at(cred.blob, size)
            return data.decode("utf-8")
        finally:
            try:
                adv.CredFree(out)
            except Exception:
                pass

    def _delete_native(self, target: str) -> None:
        import ctypes as _ct

        adv = _load_advapi32()
        ok = adv.CredDeleteW(target, CRED_TYPE_GENERIC, 0)
        if not ok:
            raise KeyError(target)

    def _list_native(self) -> List[str]:
        import ctypes as _ct

        adv = _load_advapi32()
        adv.CredEnumerateW.argtypes = [
            _ct.c_wchar_p, _ct.c_ulong,
            _ct.POINTER(_ct.c_ulong),
            _ct.POINTER(_ct.POINTER(_ct.c_void_p))]
        adv.CredEnumerateW.restype = _ct.c_int
        adv.CredFree.argtypes = [_ct.c_void_p]
        pattern = "%s*" % (self._namespace,)
        if self._suffix:
            # enumerate namespace then filter by suffix below
            pattern = "%s*" % (self._namespace,)
        count = _ct.c_ulong(0)
        ptr = _ct.POINTER(_ct.c_void_p)()

        def _do() -> List[str]:
            ok = adv.CredEnumerateW(pattern, 0, _ct.byref(count),
                                    _ct.byref(ptr))
            if not ok:
                return []
            try:
                names: List[str] = []

                class _FileTime(_ct.Structure):
                    _fields_ = [("low", _ct.c_ulong),
                                ("high", _ct.c_ulong)]

                class _Cred(_ct.Structure):
                    _fields_ = [
                        ("flags", _ct.c_ulong),
                        ("cred_type", _ct.c_ulong),
                        ("target", _ct.c_wchar_p),
                        ("comment", _ct.c_wchar_p),
                        ("written", _FileTime),
                        ("blob_size", _ct.c_ulong),
                        ("blob", _ct.c_void_p),
                        ("persist", _ct.c_ulong),
                        ("attr_count", _ct.c_ulong),
                        ("attrs", _ct.c_void_p),
                        ("alias", _ct.c_wchar_p),
                        ("user", _ct.c_wchar_p),
                    ]

                for idx in range(int(count.value)):
                    raw_ptr = ptr[idx]
                    if not raw_ptr:
                        continue
                    cred = _ct.cast(raw_ptr,
                                    _ct.POINTER(_Cred)).contents
                    name = str(cred.target or "")
                    if name.startswith(self._namespace):
                        if self._suffix and not name.endswith(
                                ":%s" % (self._suffix,)):
                            continue
                        names.append(name)
                return sorted(names)
            finally:
                try:
                    adv.CredFree(ptr)
                except Exception:
                    pass

        return _run_bounded("enumerate", _do, self._timeout)

    # -- port: write --
    def set_secret(self, secret_id: str, value: Any,
                   timeout_s: float | None = None) -> None:
        if not isinstance(secret_id, str) or not secret_id:
            raise ValueError("secret_id is required")
        if not isinstance(value, str) or not value:
            raise ValueError("key value is required")
        target = self._target(secret_id)
        limit = float(timeout_s) if timeout_s else self._timeout

        def _do() -> None:
            self._write_native(target, value)

        _run_bounded("write %s" % (target,), _do, limit)

    def seed(self, secret_id: str, payload: Any = "ephemeral-entry") -> None:
        self.set_secret(secret_id, str(payload))

    # aliases for duck-typed callers
    def store(self, secret_id: str, value: Any) -> None:
        self.set_secret(secret_id, value)

    def put(self, secret_id: str, value: Any) -> None:
        self.set_secret(secret_id, value)

    def set(self, secret_id: str, value: Any) -> None:
        self.set_secret(secret_id, value)

    def store_secret(self, secret_id: str, value: Any) -> None:
        self.set_secret(secret_id, value)

    # -- port: read --
    def get_secret(self, secret_id: str,
                   timeout_s: float | None = None) -> str:
        if not isinstance(secret_id, str) or not secret_id:
            raise ValueError("secret_id is required")
        target = self._target(secret_id)
        limit = float(timeout_s) if timeout_s else self._timeout

        def _do() -> str:
            return self._read_native(target)

        return _run_bounded("read %s" % (target,), _do, limit)

    def get(self, secret_id: str, default: Any = None) -> Any:  # type: ignore[override]
        try:
            return self.get_secret(secret_id)
        except (KeyError, OSError, ValueError, TimeoutError):
            return default

    def retrieve(self, secret_id: str) -> str:
        return self.get_secret(secret_id)

    def read(self, secret_id: str) -> str:
        return self.get_secret(secret_id)

    def get_secret_value(self, secret_id: str) -> str:
        return self.get_secret(secret_id)

    def __getitem__(self, secret_id: str) -> Dict[str, Any]:
        return {"value": self.get_secret(secret_id)}

    def __contains__(self, secret_id: object) -> bool:
        return self.has(str(secret_id))

    def has(self, secret_id: str) -> bool:
        try:
            self.get_secret(secret_id)
            return True
        except (KeyError, OSError, ValueError, TimeoutError):
            return False

    def __iter__(self):  # type: ignore[no-untyped-def]
        return iter(self._list_native())

    def __len__(self) -> int:
        return len(self._list_native())

    def delete(self, secret_id: str) -> None:
        if not isinstance(secret_id, str) or not secret_id:
            raise ValueError("secret_id is required")
        target = self._target(secret_id)

        def _do() -> None:
            self._delete_native(target)

        try:
            _run_bounded("delete %s" % (target,), _do, self._timeout)
        except KeyError:
            raise KeyError(secret_id) from None

    def __delitem__(self, secret_id: str) -> None:
        self.delete(secret_id)

    def __repr__(self) -> str:
        return "OSCredentialStore(namespace=%r, suffix=%r)" % (
            self._namespace, self._suffix)


__all__ = ["APP_NAMESPACE", "OSCredentialStore"]
