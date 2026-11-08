"""Clean raw YouTube text while preserving meaning."""

from __future__ import annotations

import html
import re

from bs4 import BeautifulSoup

from . import paths
from .errors import DataError
from .storage import read_json, write_json_atomic
from .validation import safe_video_path, sanitize_terminal_text


def clean_text(text):
    """Clean text while preserving its original meaning and formatting."""

    if not isinstance(text, str):
        return text

    # Decode HTML entities
    text = html.unescape(text)

    # Remove HTML tags while preserving their text
    text = BeautifulSoup(text, "html.parser").get_text(" ", strip=True)

    # Remove zero-width spaces and terminal control characters
    text = text.replace("\u200b", "")
    text = sanitize_terminal_text(text)

    # Normalize whitespace
    text = re.sub(r"\s+", " ", text).strip()

    return text


def clean_comments(comments):
    """Clean top-level comments and their nested replies."""

    cleaned_comments = []

    if not isinstance(comments, list):
        return cleaned_comments

    for comment in comments:
        if not isinstance(comment, dict):
            continue

        cleaned_text = clean_text(comment.get("comment"))

        if not isinstance(cleaned_text, str) or not cleaned_text:
            continue

        raw_replies = comment.get("replies", [])
        if not isinstance(raw_replies, list):
            raw_replies = []

        cleaned_replies = []

        for reply in raw_replies:
            if not isinstance(reply, dict):
                continue

            cleaned_reply = clean_text(reply.get("comment"))

            if not isinstance(cleaned_reply, str) or not cleaned_reply:
                continue

            cleaned_replies.append({
                **reply,
                "comment": cleaned_reply,
            })

        cleaned_comments.append({
            **comment,
            "comment": cleaned_text,
            "replies": cleaned_replies,
        })

    return cleaned_comments


def clean_video_data(video_id):
    """Load raw data, clean it, and save the processed dataset."""

    paths.ensure_data_dirs()

    raw_path = safe_video_path(paths.get_raw_dir(), video_id)
    raw_data = read_json(raw_path)

    if not isinstance(raw_data, dict):
        raise DataError("Raw video data must be a JSON object.")

    video = raw_data.get("video", {})
    if not isinstance(video, dict):
        video = {}

    processed_data = {
        **raw_data,
        "video": {
            **video,
            "title": clean_text(video.get("title")),
            "description": clean_text(video.get("description")),
        },
        "comments": clean_comments(raw_data.get("comments", [])),
    }

    processed_path = safe_video_path(paths.get_processed_dir(), video_id)

    write_json_atomic(processed_path, processed_data, indent=4)

    return processed_path
