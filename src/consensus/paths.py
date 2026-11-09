"""Centralised, overridable data paths.

Default behaviour:

* running from a source checkout -> ``<project>/data``
* installed package              -> platform user-data directory + ``/consensus``
* ``CONSENSUS_DATA_DIR``         -> explicit override (highest priority)
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

from .errors import DataError
from .validation import validate_video_id

PACKAGE_DIR = Path(__file__).resolve().parent
SOURCE_ROOT = PACKAGE_DIR.parents[1]
SOURCE_DATA_DIR = SOURCE_ROOT / "data"

DATA_SUBDIRECTORIES = ("raw", "processed", "analysis", "classifications")


def is_source_checkout() -> bool:
    """Return True when running from the project's source tree."""

    return (
        (SOURCE_ROOT / "pyproject.toml").is_file()
        and (SOURCE_ROOT / "src" / "consensus").is_dir()
    )


def user_data_dir(app_name: str = "consensus") -> Path:
    """Return the platform-appropriate per-user data directory."""

    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if base:
            return Path(base) / app_name
        return Path.home() / "AppData" / "Local" / app_name

    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / app_name

    base = os.environ.get("XDG_DATA_HOME")
    return (Path(base) if base else Path.home() / ".local" / "share") / app_name


def user_config_dir(app_name: str = "consensus") -> Path:
    """Return the platform-appropriate per-user config directory."""

    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.environ.get("LOCALAPPDATA")
        if base:
            return Path(base) / app_name
        return Path.home() / "AppData" / "Roaming" / app_name

    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / app_name

    base = os.environ.get("XDG_CONFIG_HOME")
    return (Path(base) if base else Path.home() / ".config") / app_name


def get_data_dir() -> Path:
    """Return the active data directory."""

    override = os.environ.get("CONSENSUS_DATA_DIR")
    if override:
        return Path(override).expanduser()

    if is_source_checkout():
        return SOURCE_DATA_DIR

    return user_data_dir()


def get_raw_dir() -> Path:
    return get_data_dir() / "raw"


def get_processed_dir() -> Path:
    return get_data_dir() / "processed"


def get_analysis_dir() -> Path:
    return get_data_dir() / "analysis"


def get_classifications_dir() -> Path:
    return get_data_dir() / "classifications"


def ensure_data_dirs(base_dir: Path | None = None) -> Path:
    """Create the data directory tree and return its root."""

    base = Path(base_dir) if base_dir is not None else get_data_dir()
    base.mkdir(parents=True, exist_ok=True)

    for name in DATA_SUBDIRECTORIES:
        (base / name).mkdir(parents=True, exist_ok=True)

    return base


def question_key(user_question: str) -> str:
    """Return a stable short key for a research question."""

    normalised = " ".join(str(user_question or "").split())
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()[:16]


def classification_artifact_paths(video_id: str, user_question: str) -> dict[str, Path]:
    """Return the preserved artifacts plus internal checkpoint paths."""

    video_id = validate_video_id(video_id)
    base = get_classifications_dir()
    key = question_key(user_question)
    prefix = f"{video_id}_{key}"

    return {
        "base": base,
        "prefix": base / prefix,
        "results": base / f"{prefix}.json",
        "aggregation": base / f"{prefix}_aggregation.json",
        "framework": base / f"{prefix}_framework.json",
        "metadata": base / f"{prefix}_run_metadata.json",
        "report": base / f"{prefix}_report.json",
        "journal": base / f"{prefix}.jsonl",
        "lock": base / f".{prefix}.lock",
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def _validate_json_file(path: Path) -> None:
    try:
        with path.open("r", encoding="utf-8") as file:
            json.load(file)
    except (OSError, json.JSONDecodeError) as exc:
        raise DataError(f"Unreadable JSON file: {path.name}") from exc


def _atomic_copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)

    file_descriptor, temporary_name = tempfile.mkstemp(
        dir=target.parent,
        prefix=f".{target.name}.",
        suffix=".tmp",
    )
    os.close(file_descriptor)
    temporary_path = Path(temporary_name)

    try:
        shutil.copy2(source, temporary_path)

        with temporary_path.open("rb+") as file:
            os.fsync(file.fileno())

        if _sha256(source) != _sha256(temporary_path):
            raise DataError(f"Verification failed while copying {source.name}.")

        os.replace(temporary_path, target)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def migrate_legacy_data(
    source: Path | str | None = None,
    target: Path | str | None = None,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Copy legacy JSON files into the active data directory.

    Safety rules:

    * existing target files are never overwritten;
    * identical files are skipped;
    * conflicting files are reported;
    * source files are never deleted;
    * every copied file is hash-verified.
    """

    source_path = Path(source).expanduser() if source is not None else SOURCE_DATA_DIR
    target_path = Path(target).expanduser() if target is not None else get_data_dir()

    report: dict[str, Any] = {
        "source": str(source_path),
        "target": str(target_path),
        "dry_run": dry_run,
        "copied": [],
        "planned": [],
        "skipped_identical": [],
        "conflicts": [],
        "errors": [],
    }

    if source_path.resolve() == target_path.resolve():
        report["errors"].append("Source and target are the same directory; nothing to do.")
        return report

    if not source_path.is_dir():
        report["errors"].append(f"Source directory does not exist: {source_path}")
        return report

    for source_file in sorted(source_path.rglob("*.json")):
        if not source_file.is_file():
            continue

        relative = source_file.relative_to(source_path)
        target_file = target_path / relative

        try:
            _validate_json_file(source_file)
        except DataError as exc:
            report["errors"].append(f"{relative}: {exc}")
            continue

        if target_file.exists():
            if _sha256(source_file) == _sha256(target_file):
                report["skipped_identical"].append(str(relative))
            else:
                report["conflicts"].append(str(relative))
            continue

        if dry_run:
            report["planned"].append(str(relative))
            continue

        try:
            _atomic_copy(source_file, target_file)
        except (OSError, DataError) as exc:
            report["errors"].append(f"{relative}: {exc}")
            continue

        report["copied"].append(str(relative))

    return report
