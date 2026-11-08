"""Atomic JSON storage helpers and raw-data access."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from . import paths
from .errors import DataError, DataNotFoundError
from .validation import safe_video_path


def write_json_atomic(path: Path, data: Any, *, indent: int = 2) -> None:
    """Write JSON via a uniquely named temporary file and atomic replace."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    file_descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    os.close(file_descriptor)
    temporary_path = Path(temporary_name)

    try:
        with temporary_path.open("w", encoding="utf-8") as file:
            json.dump(data, file, indent=indent, ensure_ascii=False)
            file.flush()
            os.fsync(file.fileno())

        os.replace(temporary_path, path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def read_json(path: Path) -> Any:
    """Read JSON with a clear, safe error message."""

    path = Path(path)

    if not path.exists():
        raise DataNotFoundError(f"Required file not found: {path}")

    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except json.JSONDecodeError as exc:
        raise DataError(f"Invalid JSON in {path.name}: {exc.msg}") from None
    except OSError as exc:
        raise DataError(f"Could not read {path.name}: {exc}") from None


def save_data(video_id, data):
    paths.ensure_data_dirs()
    file_path = safe_video_path(paths.get_raw_dir(), video_id)
    write_json_atomic(file_path, data, indent=4)
    return file_path


def load_data(video_id):
    file_path = safe_video_path(paths.get_raw_dir(), video_id)
    return read_json(file_path)
