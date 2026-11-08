from __future__ import annotations

import json

import pytest

from consensus import storage
from consensus.errors import DataNotFoundError


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    target = tmp_path / "consensus-data"
    monkeypatch.setenv("CONSENSUS_DATA_DIR", str(target))
    return target


def test_write_and_read_json_atomic(tmp_path):
    path = tmp_path / "nested" / "file.json"
    data = {"text": "héllo", "values": [1, 2, 3]}

    storage.write_json_atomic(path, data)

    assert json.loads(path.read_text(encoding="utf-8")) == data
    assert not list(path.parent.glob(".*.tmp"))


def test_read_json_missing_file_raises(tmp_path):
    with pytest.raises(DataNotFoundError):
        storage.read_json(tmp_path / "missing.json")


def test_save_and_load_data_roundtrip(data_dir):
    payload = {"video": {"title": "Example"}, "comments": []}

    saved = storage.save_data("dQw4w9WgXcQ", payload)

    assert saved == data_dir / "raw" / "dQw4w9WgXcQ.json"
    assert storage.load_data("dQw4w9WgXcQ") == payload


def test_save_data_rejects_invalid_video_id(data_dir):
    with pytest.raises(Exception):
        storage.save_data("../../escape", {"comments": []})
