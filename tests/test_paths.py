from __future__ import annotations

from pathlib import Path

import pytest

from consensus import paths
from consensus.errors import ValidationError


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    target = tmp_path / "consensus-data"
    monkeypatch.setenv("CONSENSUS_DATA_DIR", str(target))
    return target


def test_data_dir_env_override(data_dir):
    assert paths.get_data_dir() == data_dir


def test_installed_default_uses_user_data_dir(tmp_path, monkeypatch):
    monkeypatch.delenv("CONSENSUS_DATA_DIR", raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setattr(paths, "is_source_checkout", lambda: False)

    assert paths.get_data_dir() == tmp_path / "consensus"


def test_ensure_data_dirs_creates_tree(data_dir):
    result = paths.ensure_data_dirs()

    assert result == data_dir
    for name in paths.DATA_SUBDIRECTORIES:
        assert (data_dir / name).is_dir()


def test_question_key_is_stable_and_distinct():
    first = paths.question_key("Do viewers trust the product?")
    second = paths.question_key("  Do viewers   trust the product? ")
    other = paths.question_key("Is the price fair?")

    assert first == second
    assert first != other
    assert len(first) == 16


def test_artifact_paths_include_four_artifacts(data_dir):
    artifacts = paths.classification_artifact_paths(
        "dQw4w9WgXcQ",
        "Is it useful?",
    )

    for key in ("results", "aggregation", "framework", "metadata"):
        assert key in artifacts
        assert artifacts[key].parent == data_dir / "classifications"

    assert artifacts["results"].name.startswith("dQw4w9WgXcQ_")
    assert artifacts["aggregation"].name.endswith("_aggregation.json")
    assert artifacts["framework"].name.endswith("_framework.json")
    assert artifacts["metadata"].name.endswith("_run_metadata.json")


def test_artifact_paths_differ_per_question(data_dir):
    first = paths.classification_artifact_paths("dQw4w9WgXcQ", "Question A")
    second = paths.classification_artifact_paths("dQw4w9WgXcQ", "Question B")

    assert first["results"] != second["results"]


def test_artifact_paths_reject_invalid_video_id(data_dir):
    with pytest.raises(ValidationError):
        paths.classification_artifact_paths("../etc/passwd", "Question")
