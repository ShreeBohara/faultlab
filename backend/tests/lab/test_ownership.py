"""Real local process leases; no database, network, provider or environment loading."""
import errno
import gc
import os
from pathlib import Path
import select
import subprocess
import sys
import weakref

import pytest

from app.lab import ownership
from app.lab.ownership import CoordinatorLease, OwnershipUnavailable, StoreInUse


def test_second_owner_conflicts_until_close_and_lock_file_is_never_replaced(tmp_path):
    path = tmp_path / 'lab.sqlite3'
    first = CoordinatorLease.acquire(path)
    inode = first.lock_path.stat().st_ino
    try:
        with pytest.raises(StoreInUse) as caught:
            CoordinatorLease.acquire(path, store_identity=object())
        assert caught.value.code == 'STORE_IN_USE'
        assert str(tmp_path) not in str(caught.value)
        assert not path.exists()  # Ownership acquisition does not open SQLite.
    finally:
        first.close()
    first.close()
    assert first.closed and first.lock_path.stat().st_ino == inode
    with CoordinatorLease.acquire(path) as second:
        assert second.lock_path.stat().st_ino == inode


def test_symlink_file_and_directory_aliases_share_the_canonical_lease(tmp_path):
    actual = tmp_path / 'actual'; actual.mkdir()
    alias = tmp_path / 'alias'; alias.symlink_to(actual, target_is_directory=True)
    path = actual / 'lab.sqlite3'
    path.write_bytes(b'Existing evidence must not be read or modified')
    linked = tmp_path / 'linked.sqlite3'; linked.symlink_to(path)
    with CoordinatorLease.acquire(path) as owner:
        assert owner.database_path == path.resolve()
        for name in (linked, alias / path.name, actual / '..' / 'actual' / path.name):
            with pytest.raises(StoreInUse):
                CoordinatorLease.acquire(name)
    assert path.read_bytes() == b'Existing evidence must not be read or modified'


def test_independent_paths_can_be_owned_together(tmp_path):
    with CoordinatorLease.acquire(tmp_path / 'one' / 'lab.sqlite3') as one:
        with CoordinatorLease.acquire(tmp_path / 'two' / 'lab.sqlite3') as two:
            assert one.database_path != two.database_path
            assert not one.closed and not two.closed


def test_in_memory_identity_distinguishes_independent_and_shared_injected_stores():
    first_store, second_store = object(), object()
    with CoordinatorLease.acquire(':memory:', store_identity=first_store):
        with pytest.raises(StoreInUse):
            CoordinatorLease.acquire(':memory:', store_identity=first_store)
        with CoordinatorLease.acquire(':memory:', store_identity=second_store):
            with CoordinatorLease.acquire(':memory:'):
                with CoordinatorLease.acquire(':memory:') as independent:
                    assert independent.lock_path is None
    with CoordinatorLease.acquire(':memory:', store_identity=first_store):
        pass


def test_exception_in_owned_scope_releases_the_lease(tmp_path):
    path = tmp_path / 'lab.sqlite3'
    with pytest.raises(RuntimeError, match='fixture failure'):
        with CoordinatorLease.acquire(path):
            raise RuntimeError('fixture failure')
    with CoordinatorLease.acquire(path):
        pass


def test_collected_owner_does_not_leave_a_registry_or_descriptor_lock(tmp_path):
    path = tmp_path / 'lab.sqlite3'
    lease = CoordinatorLease.acquire(path)
    reference = weakref.ref(lease)
    del lease
    gc.collect()
    assert reference() is None
    with CoordinatorLease.acquire(path):
        pass


def test_hard_linked_database_names_are_rejected_without_reading_or_modifying_them(tmp_path):
    original = tmp_path / 'original.sqlite3'; original.write_bytes(b'unchanged')
    linked = tmp_path / 'linked.sqlite3'; os.link(original, linked)
    for path in (original, linked):
        with pytest.raises(OwnershipUnavailable, match='Hard-linked database'):
            CoordinatorLease.acquire(path)
    assert original.read_bytes() == linked.read_bytes() == b'unchanged'
    assert not list(tmp_path.glob('*.coordinator.lock'))


@pytest.mark.parametrize('link_type', ['symlink', 'hardlink'])
def test_lock_file_aliases_are_rejected_without_touching_the_target(tmp_path, link_type):
    path = tmp_path / 'lab.sqlite3'
    target = tmp_path / 'existing-lock'; target.write_bytes(b'private owner diagnostics')
    lock = path.with_name(path.name + '.coordinator.lock')
    if link_type == 'symlink': lock.symlink_to(target)
    else: os.link(target, lock)
    with pytest.raises(OwnershipUnavailable) as caught:
        CoordinatorLease.acquire(path)
    assert target.read_bytes() == b'private owner diagnostics'
    assert 'private owner diagnostics' not in str(caught.value)
    assert str(tmp_path) not in str(caught.value)


def test_leftover_lock_contents_have_no_authority_and_are_not_rewritten(tmp_path):
    path = tmp_path / 'lab.sqlite3'
    lock = path.with_name(path.name + '.coordinator.lock')
    lock.write_text('not-a-real-owner-pid\n')
    before = lock.stat().st_ino
    with CoordinatorLease.acquire(path):
        assert lock.read_text() == 'not-a-real-owner-pid\n'
    assert lock.stat().st_ino == before


@pytest.mark.parametrize('failure', ['open', 'flock'])
def test_failed_acquisition_is_safe_and_does_not_leak_ownership(tmp_path, monkeypatch, failure):
    path = tmp_path / 'lab.sqlite3'
    with monkeypatch.context() as patched:
        def fail(*args, **kwargs):
            raise OSError(errno.EIO, 'PRIVATE filesystem detail')
        if failure == 'open': patched.setattr(ownership.os, 'open', fail)
        else: patched.setattr(ownership.fcntl, 'flock', fail)
        with pytest.raises(OwnershipUnavailable) as caught:
            CoordinatorLease.acquire(path)
        assert str(caught.value) == 'Local store ownership could not be established.'
        assert 'PRIVATE' not in str(caught.value)
    with CoordinatorLease.acquire(path):
        pass


def test_platform_without_supported_lock_fails_closed_for_files(tmp_path, monkeypatch):
    monkeypatch.setattr(ownership, 'fcntl', None)
    with pytest.raises(OwnershipUnavailable, match='unsupported'):
        CoordinatorLease.acquire(tmp_path / 'lab.sqlite3')
    with CoordinatorLease.acquire(':memory:'):
        pass


_CHILD = '''
import sys
from app.lab.ownership import CoordinatorLease, StoreInUse
print('READY', flush=True)
sys.stdin.readline()
try:
    lease = CoordinatorLease.acquire(sys.argv[1])
except StoreInUse:
    print('STORE_IN_USE', flush=True)
    raise SystemExit(3)
print('ACQUIRED', flush=True)
sys.stdin.readline()
lease.close()
'''


def read_line(process):
    ready, _, _ = select.select([process.stdout], [], [], 10)
    assert ready, 'Lease subprocess did not report within ten seconds'
    return process.stdout.readline().strip()


@pytest.fixture
def children():
    processes = []
    def start(path):
        process = subprocess.Popen([sys.executable, '-c', _CHILD, str(path)],
            cwd=Path(__file__).resolve().parents[2], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
        processes.append(process)
        assert read_line(process) == 'READY'
        return process
    yield start
    for process in processes:
        if process.poll() is None: process.kill()
        process.communicate(timeout=10)


def attempt(process):
    process.stdin.write('\n'); process.stdin.flush()
    return read_line(process)


def test_another_process_cannot_acquire_a_live_owner(tmp_path, children):
    path = tmp_path / 'lab.sqlite3'
    with CoordinatorLease.acquire(path):
        contender = children(path)
        assert attempt(contender) == 'STORE_IN_USE'
        assert contender.wait(timeout=10) == 3


def test_two_simultaneous_processes_admit_exactly_one_owner(tmp_path, children):
    path = tmp_path / 'lab.sqlite3'
    first, second = children(path), children(path)
    for process in (first, second):
        process.stdin.write('\n'); process.stdin.flush()
    states = [read_line(process) for process in (first, second)]
    assert sorted(states) == ['ACQUIRED', 'STORE_IN_USE']
    with pytest.raises(StoreInUse): CoordinatorLease.acquire(path)
    winner = (first, second)[states.index('ACQUIRED')]
    winner.stdin.write('\n'); winner.stdin.flush()
    assert winner.wait(timeout=10) == 0
    with CoordinatorLease.acquire(path):
        pass


def test_process_crash_releases_os_ownership_without_deleting_a_stale_file(tmp_path, children):
    path = tmp_path / 'lab.sqlite3'
    owner = children(path)
    assert attempt(owner) == 'ACQUIRED'
    lock = path.with_name(path.name + '.coordinator.lock')
    inode = lock.stat().st_ino
    with pytest.raises(StoreInUse): CoordinatorLease.acquire(path)
    owner.kill(); owner.wait(timeout=10)
    with CoordinatorLease.acquire(path) as restarted:
        assert restarted.lock_path.stat().st_ino == inode


@pytest.mark.skipif(not hasattr(os, 'fork'), reason='POSIX fork behavior')
def test_fork_child_does_not_unlock_parent_or_retain_its_lease(tmp_path):
    path = tmp_path / 'lab.sqlite3'
    lease = CoordinatorLease.acquire(path)
    read_fd, write_fd = os.pipe()
    pid = os.fork()
    if pid == 0:
        os.close(read_fd)
        try:
            # The at-fork hook closed only the inherited child descriptor. A new
            # acquisition still conflicts with the independently alive parent.
            try:
                CoordinatorLease.acquire(path)
            except StoreInUse:
                os.write(write_fd, b'protected')
            else:
                os.write(write_fd, b'unlocked')
        finally:
            os.close(write_fd)
            os._exit(0)
    os.close(write_fd)
    try:
        ready, _, _ = select.select([read_fd], [], [], 10)
        assert ready
        assert os.read(read_fd, 64) == b'protected'
        assert os.waitpid(pid, 0)[1] == 0
    finally:
        os.close(read_fd)
        lease.close()
    with CoordinatorLease.acquire(path):
        pass
