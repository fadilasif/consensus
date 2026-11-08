from __future__ import annotations

import pytest

from consensus.errors import ValidationError
from consensus.validation import (
    redact_secrets,
    safe_video_path,
    sanitize_terminal_text,
    validate_video_id,
)


@pytest.mark.parametrize(
    "video_id",
    ["dQw4w9WgXcQ", "abcDEF123_-", "12345678901"],
)
def test_validate_video_id_accepts_valid_ids(video_id):
    assert validate_video_id(video_id) == video_id


@pytest.mark.parametrize(
    "video_id",
    [
        "",
        "short",
        "dQw4w9WgXc",
        "dQw4w9WgXcQQ",
        "../escape11",
        "dQw4w9WgXc/",
        "dQw4w9WgXc ",
        None,
        123,
    ],
)
def test_validate_video_id_rejects_invalid_ids(video_id):
    with pytest.raises(ValidationError):
        validate_video_id(video_id)


def test_safe_video_path_stays_inside_directory(tmp_path):
    path = safe_video_path(tmp_path, "dQw4w9WgXcQ")

    assert path == (tmp_path / "dQw4w9WgXcQ.json").resolve()


def test_safe_video_path_rejects_traversal(tmp_path):
    with pytest.raises(ValidationError):
        safe_video_path(tmp_path, "../../etc/passwd")


def test_sanitize_terminal_text_strips_control_characters():
    value = "hello\x1b[31m red\x1b[0m\nworld\t!"

    cleaned = sanitize_terminal_text(value)

    assert "\x1b" not in cleaned
    assert "\n" not in cleaned
    assert "\t" in cleaned  # tabs are preserved by the shared sanitiser


def test_sanitize_terminal_text_handles_none():
    assert sanitize_terminal_text(None) == ""


def test_redact_secrets_removes_known_values_and_assignments():
    text = (
        "Authorization: Bearer abc123 "
        "api_key=secret-value key=another-secret"
    )

    cleaned = redact_secrets(text, "abc123")

    assert "abc123" not in cleaned
    assert "secret-value" not in cleaned
    assert "another-secret" not in cleaned
    assert "***" in cleaned
