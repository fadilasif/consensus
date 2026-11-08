"""YouTube Data API collection with bounded retries."""

from __future__ import annotations

import requests
from requests.adapters import HTTPAdapter
from tqdm import tqdm
from urllib3.util.retry import Retry

from .config import get_required_env
from .errors import YouTubeAPIError
from .validation import redact_secrets, validate_video_id

BASE_URL = "https://www.googleapis.com/youtube/v3"

REQUEST_TIMEOUT = 30
MAX_RETRIES = 5

# YouTube embeds at most a handful of replies in commentThreads.  This
# constant is a safety cap; fetching every reply would require a separate
# comments.list(parentId=...) traversal and would change the current data
# population.
MAX_REPLIES = 10


def _to_int(value: object, default: int = 0) -> int:
    """Coerce API counters without crashing on malformed values."""

    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _api_key() -> str:
    return get_required_env("YOUTUBE_API_KEY")


def _session() -> requests.Session:
    retry = Retry(
        total=MAX_RETRIES,
        connect=MAX_RETRIES,
        read=MAX_RETRIES,
        status=MAX_RETRIES,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        respect_retry_after_header=True,
        raise_on_status=False,
    )

    session = requests.Session()
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def _get_json(url: str, params: dict, context: str) -> dict:
    key = _api_key()

    try:
        with _session() as session:
            response = session.get(
                url,
                params={**params, "key": key},
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            data = response.json()

    except requests.HTTPError as error:
        status = (
            error.response.status_code
            if error.response is not None
            else None
        )
        body = (
            error.response.text[:1000]
            if error.response is not None
            else ""
        )
        safe_body = redact_secrets(body, key)

        if "commentsDisabled" in body:
            raise YouTubeAPIError(
                "Comments are disabled for this video."
            ) from None

        raise YouTubeAPIError(
            f"YouTube API error {status} while {context}: {safe_body}"
        ) from None

    except requests.RequestException as error:
        raise YouTubeAPIError(
            f"YouTube API request failed while {context}: "
            f"{redact_secrets(str(error), key)}"
        ) from None

    except ValueError:
        raise YouTubeAPIError(
            f"YouTube API returned invalid JSON while {context}."
        ) from None

    if not isinstance(data, dict):
        raise YouTubeAPIError(
            f"YouTube API returned an unexpected response while {context}."
        )

    return data


def get_comments(video_id):
    video_id = validate_video_id(video_id)

    url = f"{BASE_URL}/commentThreads"

    params = {
        "part": "snippet,replies",
        "videoId": video_id,
        "maxResults": 100,
    }

    comments = []
    progress = None

    try:
        while True:
            data = _get_json(url, params, "fetching comments")

            if progress is None:
                total = data.get("pageInfo", {}).get("totalResults")

                progress = tqdm(
                    total=total,
                    desc="Fetching comments",
                    unit="comments",
                )

            items = data.get("items", [])
            if not isinstance(items, list):
                items = []

            for item in items:
                if not isinstance(item, dict):
                    continue

                thread = item.get("snippet", {})
                top_comment = thread.get("topLevelComment", {})
                snippet = top_comment.get("snippet", {})

                if not isinstance(snippet, dict):
                    continue

                text = snippet.get("textDisplay")
                if not isinstance(text, str):
                    continue

                # Extract embedded replies.  The API normally embeds at
                # most five; MAX_REPLIES is only a safety cap.
                replies = []

                replies_block = item.get("replies", {})
                embedded_replies = (
                    replies_block.get("comments", [])
                    if isinstance(replies_block, dict)
                    else []
                )

                if not isinstance(embedded_replies, list):
                    embedded_replies = []

                for reply in embedded_replies[:MAX_REPLIES]:
                    if not isinstance(reply, dict):
                        continue

                    reply_snippet = reply.get("snippet", {})
                    if not isinstance(reply_snippet, dict):
                        continue

                    reply_text = reply_snippet.get("textDisplay")
                    if not isinstance(reply_text, str):
                        continue

                    replies.append({
                        "comment": reply_text,
                        "likes": _to_int(reply_snippet.get("likeCount", 0)),
                    })

                comments.append({
                    "comment": text,
                    "likes": _to_int(snippet.get("likeCount", 0)),
                    "replies": replies,
                })

            progress.update(len(items))

            next_page_token = data.get("nextPageToken")

            if not next_page_token:
                break

            params["pageToken"] = next_page_token

    finally:
        if progress is not None:
            progress.close()

    return comments


def get_video_details(video_id):
    video_id = validate_video_id(video_id)

    url = f"{BASE_URL}/videos"

    params = {
        "part": "snippet,statistics",
        "id": video_id,
    }

    data = _get_json(url, params, "fetching video details")

    items = data.get("items", [])
    if not isinstance(items, list) or not items:
        return None

    video = items[0]
    if not isinstance(video, dict):
        return None

    snippet = video.get("snippet", {})
    statistics = video.get("statistics", {})

    if not isinstance(snippet, dict):
        snippet = {}
    if not isinstance(statistics, dict):
        statistics = {}

    return {
        "title": snippet.get("title", ""),
        "description": snippet.get("description", ""),
        "views": _to_int(statistics.get("viewCount", 0)),
        "likes": _to_int(statistics.get("likeCount", 0)),
    }
