"""Validation and sanitisation helpers shared by the pipeline."""

from __future__ import annotations

import re
from pathlib import Path

from .errors import ValidationError

# YouTube IDs are exactly 11 URL-safe base64 characters.
VIDEO_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{11}$")

# C0/C1 control characters.  Newlines and tabs are intentionally kept for
# general text cleaning; terminal output is flattened separately below.
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")

_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(key|api_key|apikey|token|authorization)\s*=\s*[^&\s]+"
)
_BEARER_TOKEN = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._\-]+")


def validate_video_id(video_id: str) -> str:
    """Return a normalised video ID or raise :class:`ValidationError`."""

    if not isinstance(video_id, str):
        raise ValidationError("YouTube video ID must be a string.")

    video_id = video_id.strip()

    if not VIDEO_ID_PATTERN.fullmatch(video_id):
        raise ValidationError(
            "Invalid YouTube video ID. Expected 11 characters "
            "(letters, digits, '-' or '_')."
        )

    return video_id


def safe_video_path(directory: Path, video_id: str, suffix: str = ".json") -> Path:
    """Build a path for a video artifact after validating the ID.

    This prevents user-supplied IDs from escaping the configured data
    directory.
    """

    video_id = validate_video_id(video_id)
    directory = Path(directory).resolve()
    path = (directory / f"{video_id}{suffix}").resolve()

    if path.parent != directory:
        raise ValidationError("Unsafe video artifact path.")

    return path


def sanitize_terminal_text(value: object) -> str:
    """Remove control characters and flatten newlines before terminal output."""

    text = _CONTROL_CHARS.sub("", str(value or ""))
    return text.replace("\r", " ").replace("\n", " ")


def redact_secrets(text: object, *secrets: str | None) -> str:
    """Redact known secrets and common credential-shaped substrings."""

    result = str(text or "")

    for secret in secrets:
        if secret:
            result = result.replace(secret, "***")

    result = _SECRET_ASSIGNMENT.sub(lambda match: f"{match.group(1)}=***", result)
    result = _BEARER_TOKEN.sub("Bearer ***", result)

    return result
