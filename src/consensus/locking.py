"""A small cross-platform advisory file lock.

The lock prevents two classification processes from writing the same
checkpoint files at the same time.  It is advisory and process-scoped.
"""

from __future__ import annotations

import os
from pathlib import Path

from .errors import ConcurrentRunError


class FileLock:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._handle = None

    def __enter__(self) -> "FileLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self.path.open("a+", encoding="utf-8")

        try:
            if os.name == "nt":
                import msvcrt

                self._handle.seek(0)
                self._handle.write(" ")
                self._handle.flush()
                self._handle.seek(0)
                msvcrt.locking(self._handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self._handle.close()
            self._handle = None
            raise ConcurrentRunError(
                f"Another run is already using {self.path.name}. "
                "Wait for it to finish before starting a new run."
            ) from None

        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        if self._handle is None:
            return

        try:
            if os.name == "nt":
                import msvcrt

                self._handle.seek(0)
                msvcrt.locking(self._handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        finally:
            self._handle.close()
            self._handle = None
