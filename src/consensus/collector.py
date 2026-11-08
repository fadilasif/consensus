
import os
import requests
from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv()

API_KEY = os.getenv("YOUTUBE_API_KEY")

BASE_URL = "https://www.googleapis.com/youtube/v3"

MAX_REPLIES = 10


def get_comments(video_id):

    url = f"{BASE_URL}/commentThreads"

    params = {
        "part": "snippet,replies",
        "videoId": video_id,
        "maxResults": 100,
        "key": API_KEY
    }

    comments = []
    progress = None

    try:
        while True:

            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()

            data = response.json()

            if progress is None:
                total = data.get("pageInfo", {}).get("totalResults")

                progress = tqdm(
                    total=total,
                    desc="Fetching comments",
                    unit="comments"
                )

            items = data.get("items", [])

            for item in items:

                thread = item["snippet"]
                top_comment = thread["topLevelComment"]
                snippet = top_comment["snippet"]

                # Extract embedded replies
                replies = []

                embedded_replies = item.get("replies", {}).get("comments", [])

                for reply in embedded_replies[:MAX_REPLIES]:

                    reply_snippet = reply["snippet"]

                    replies.append({
                        "comment": reply_snippet["textDisplay"],
                        "likes": reply_snippet["likeCount"]
                    })

                comments.append({
                    "comment": snippet["textDisplay"],
                    "likes": snippet["likeCount"],
                    "replies": replies
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

    url = f"{BASE_URL}/videos"

    params = {
        "part": "snippet,statistics",
        "id": video_id,
        "key": API_KEY
    }

    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()

    data = response.json()

    if not data.get("items"):
        return None

    video = data["items"][0]
    snippet = video["snippet"]
    statistics = video.get("statistics", {})

    return {
        "title": snippet["title"],
        "description": snippet["description"],
        "views": int(statistics.get("viewCount", 0)),
        "likes": int(statistics.get("likeCount", 0))
    }
