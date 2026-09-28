"""One coordinator owns a local store until its OS lease is closed.

This guards schedulers, not every LabStore reader or legacy CLI writer. It must be
acquired before policy initialization or restart recovery. No database is opened
here, and lock-file contents (including an old PID) are never ownership authority.
"""
from __future__ import annotations

import errno
import os
from pathlib import Path
import stat
from threading import RLock
import weakref

from app.lab.storage import StoreConflict

try:
    import fcntl
except ImportError:  # Fail closed on platforms without this reviewed local lease.
    fcntl = None


class StoreInUse(StoreConflict):
    code = 'STORE_IN_USE'

    def __init__(self):
        super().__init__('Another FaultLab coordinator owns this store. Stop it before opening fresh work.')


class OwnershipUnavailable(StoreConflict):
    code = 'STORE_OWNERSHIP_UNAVAILABLE'

    def __init__(self, message='Local store ownership could not be established.'):
        super().__init__(message)


_claims = {}
_claims_lock = RLock()


def _check_database_path(path):
    try:
        info = path.stat()
    except FileNotFoundError:
        return
    if not stat.S_ISREG(info.st_mode):
        raise OwnershipUnavailable('The store path must name a regular database file.')
    if info.st_nlink != 1:
        raise OwnershipUnavailable('Hard-linked database files cannot acquire coordinator ownership.')


class CoordinatorLease:
    """Nonblocking lifetime lease; acquire through ``acquire``, release via ``close``.

    File-backed stores use the canonical database path, including symlink targets.
    Existing hard links are rejected: distinct pathnames would otherwise create
    distinct lock files for the same SQLite database. Do not rename, replace or
    hard-link database/lock files while an owner is running.

    ``:memory:`` stores are independent unless the caller supplies the same
    ``store_identity`` object for an injected store. Keep that object alive with
    the lease so Python cannot reuse its identity before release.
    """

    @classmethod
    def acquire(cls, path, *, store_identity=None):
        descriptor = None
        identity = None
        try:
            raw = os.fspath(path)
            if raw == ':memory:':
                identity = store_identity if store_identity is not None else object()
                database_path = lock_path = None
                key = ('memory', id(identity))
            else:
                if not isinstance(raw, str) or not raw or raw.startswith('file:'):
                    raise OwnershipUnavailable('A local filesystem database path is required.')
                database_path = Path(raw).expanduser().resolve()
                _check_database_path(database_path)
                lock_path = database_path.with_name(database_path.name + '.coordinator.lock')
                key = ('file', str(database_path))

            with _claims_lock:
                previous = _claims.get(key)
                if previous is not None and previous() is not None:
                    raise StoreInUse()
                if database_path is not None:
                    if fcntl is None or not hasattr(os, 'O_NOFOLLOW'):
                        raise OwnershipUnavailable('Coordinator ownership is unsupported on this platform.')
                    database_path.parent.mkdir(parents=True, exist_ok=True)
                    descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
                    os.set_inheritable(descriptor, False)
                    info = os.fstat(descriptor)
                    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                        raise OwnershipUnavailable('The coordinator lock must be a regular file without hard links.')
                    try:
                        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except OSError as error:
                        if error.errno in (errno.EACCES, errno.EAGAIN):
                            raise StoreInUse() from None
                        raise
                    # Reject a hard link added while this acquisition was waiting
                    # for filesystem I/O. Never rewrite or remove either file.
                    _check_database_path(database_path)
                lease = cls()
                lease.database_path = database_path
                lease.lock_path = lock_path
                lease._key = key
                lease._identity = identity
                lease._descriptor = descriptor
                lease._closed = False
                _claims[key] = weakref.ref(lease)
                return lease
        except (StoreInUse, OwnershipUnavailable):
            if descriptor is not None:
                os.close(descriptor)
            raise
        except (OSError, RuntimeError, TypeError, ValueError):
            if descriptor is not None:
                os.close(descriptor)
            # Filesystem errors may contain arbitrary paths; do not expose them
            # through the API or substitute their text for safe diagnostics.
            raise OwnershipUnavailable() from None

    @property
    def closed(self):
        return getattr(self, '_closed', True)

    def close(self):
        with _claims_lock:
            if self.closed:
                return
            self._closed = True
            descriptor, self._descriptor = self._descriptor, None
            try:
                if descriptor is not None:
                    # Closing the final descriptor releases flock. Do not unlink
                    # the lock or explicitly unlock an inherited fork descriptor.
                    os.close(descriptor)
            finally:
                previous = _claims.get(self._key)
                if previous is not None and previous() is self:
                    _claims.pop(self._key, None)
                self._identity = None

    def __enter__(self):
        if self.closed:
            raise OwnershipUnavailable('The coordinator lease is already closed.')
        return self

    def __exit__(self, *_):
        self.close()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass


def _after_fork_child():
    """A child must not retain its parent's lease or inherited thread lock."""
    global _claims_lock
    _claims_lock = RLock()
    inherited = [reference() for reference in _claims.values()]
    for lease in inherited:
        if lease is not None:
            lease.close()
    _claims.clear()


if hasattr(os, 'register_at_fork'):
    os.register_at_fork(after_in_child=_after_fork_child)
