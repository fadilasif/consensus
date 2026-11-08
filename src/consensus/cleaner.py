
import json
import re
import html
from pathlib import Path
from bs4 import BeautifulSoup


BASE_DIR = Path(__file__).resolve().parent
RAW_DIR = BASE_DIR / "data" / "raw"
PROCESSED_DIR = BASE_DIR / "data" / "processed"


def clean_text(text):
    """Clean text while preserving its original meaning and formatting."""

    if not isinstance(text, str):
        return text

    # Decode HTML entities
    text = html.unescape(text)

    # Remove HTML tags while preserving their text
    text = BeautifulSoup(text, "html.parser").get_text(" ", strip=True)

    # Remove zero-width spaces
    text = text.replace("\u200b", "")

    # Normalize whitespace
    text = re.sub(r"\s+", " ", text).strip()

    return text


def clean_comments(comments):
    """Clean top-level comments and their nested replies."""

    cleaned_comments = []

    for comment in comments:
        cleaned_text = clean_text(comment["comment"])

        # Skip comments that become empty
        if not cleaned_text:
            continue

        cleaned_replies = []

        for reply in comment.get("replies", []):
            cleaned_reply = clean_text(reply["comment"])

            if not cleaned_reply:
                continue

            cleaned_replies.append({
                **reply,
                "comment": cleaned_reply
            })

        cleaned_comments.append({
            **comment,
            "comment": cleaned_text,
            "replies": cleaned_replies
        })

    return cleaned_comments


def clean_video_data(video_id):
    """Load raw data, clean it, and save the processed dataset."""

    raw_path = RAW_DIR / f"{video_id}.json"

    with open(raw_path, "r", encoding="utf-8") as file:
        raw_data = json.load(file)

    video = raw_data.get("video", {})

    processed_data = {
        **raw_data,
        "video": {
            **video,
            "title": clean_text(video.get("title")),
            "description": clean_text(video.get("description"))
        },
        "comments": clean_comments(raw_data.get("comments", []))
    }

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    processed_path = PROCESSED_DIR / f"{video_id}.json"

    with open(processed_path, "w", encoding="utf-8") as file:
        json.dump(
            processed_data,
            file,
            indent=4,
            ensure_ascii=False
        )

    return processed_path
