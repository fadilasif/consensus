from __future__ import annotations

import pytest

from consensus.errors import ConcurrentRunError
from consensus.locking import FileLock


def test_file_lock_prevents_concurrent_use(tmp_path):
    lock_path = tmp_path / ".run.lock"

    with FileLock(lock_path):
        with pytest.raises(ConcurrentRunError):
            with FileLock(lock_path):
                pass


def test_file_lock_can_be_reacquired(tmp_path):
    lock_path = tmp_path / ".run.lock"

    with FileLock(lock_path):
        pass

    with FileLock(lock_path):
        pass
