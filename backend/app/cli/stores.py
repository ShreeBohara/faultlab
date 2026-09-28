"""CLI ownership boundaries: offline writers own the store; saved readers never do."""
from contextlib import contextmanager

from app.contracts.models import content_hash
from app.lab.ownership import CoordinatorLease, OwnershipUnavailable, StoreInUse
from app.lab.storage import LabStore, ReadOnlyLabStore, ReadOnlyStore


@contextmanager
def owned_store(path):
    """Acquire before SQLite opens, including when construction or cleanup fails."""
    lease = CoordinatorLease.acquire(path)
    try:
        store = LabStore(lease.database_path if lease.database_path is not None else ':memory:')
        try:
            store.on_close(lease.close)
            yield store
        finally:
            store.close()
    finally:
        lease.close()


@contextmanager
def writable_store(settings):
    if settings.faultlab_read_only:
        raise ReadOnlyStore('This store is a read-only archive; select a writable data directory.')
    with owned_store(settings.artifact_path / 'lab.sqlite3') as store:
        yield store


@contextmanager
def saved_store(settings):
    store = ReadOnlyLabStore(settings.artifact_path / 'lab.sqlite3')
    try:
        store.begin_snapshot()
        yield store
    finally:
        store.close()


def expected_store_identity(settings):
    """Match the server's descriptor without opening, claiming or creating a DB."""
    path = str((settings.artifact_path / 'lab.sqlite3').expanduser().resolve())
    return content_hash({'local_store_path': path})


OWNERSHIP_ERRORS = (StoreInUse, OwnershipUnavailable, ReadOnlyStore)


def ownership_error(error):
    if isinstance(error, StoreInUse):
        return {'status': 'REJECTED', 'error_type': 'StoreInUse', 'code': 'STORE_IN_USE',
                'message': 'Another FaultLab backend or CLI owns this store. Stop it before this offline write, or select a separate data directory.'}
    if isinstance(error, ReadOnlyStore):
        return {'status': 'REJECTED', 'error_type': 'ReadOnlyStore', 'code': 'READ_ONLY_ARCHIVE',
                'message': 'This store is a read-only archive; select a writable data directory.'}
    return {'status': 'REJECTED', 'error_type': 'OwnershipUnavailable', 'code': 'STORE_OWNERSHIP_UNAVAILABLE',
            'message': 'Exclusive local store ownership could not be established. No offline write started.'}
