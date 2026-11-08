"""Basic statistical analysis of processed video data."""

from __future__ import annotations

import pandas as pd

from . import paths
from .errors import DataError
from .storage import read_json, write_json_atomic
from .validation import safe_video_path, sanitize_terminal_text


def load_processed_data(video_id):
    """Load processed video data."""

    file_path = safe_video_path(paths.get_processed_dir(), video_id)
    data = read_json(file_path)

    if not isinstance(data, dict):
        raise DataError("Processed video data must be a JSON object.")

    return data


def create_dataframe(data):
    """Create a DataFrame containing top-level comments and nested replies."""

    comments = data.get("comments", [])

    if not isinstance(comments, list):
        comments = []

    if not comments:
        return pd.DataFrame(columns=["comment", "likes", "replies"])

    comments_df = pd.DataFrame(comments)

    if "comment" not in comments_df.columns:
        comments_df["comment"] = ""

    if "likes" not in comments_df.columns:
        comments_df["likes"] = 0

    comments_df["likes"] = (
        pd.to_numeric(comments_df["likes"], errors="coerce")
        .fillna(0)
        .astype(int)
    )

    if "replies" not in comments_df.columns:
        comments_df["replies"] = [[] for _ in range(len(comments_df))]

    comments_df["replies"] = comments_df["replies"].apply(
        lambda value: value if isinstance(value, list) else []
    )

    return comments_df


def analyse_video(data, comments_df):
    """Calculate basic video statistics."""

    video = data.get("video", {})
    if not isinstance(video, dict):
        video = {}

    if "replies" in comments_df.columns:
        total_replies = int(comments_df["replies"].apply(len).sum())
    else:
        total_replies = 0

    return {
        "title": video.get("title"),
        "views": video.get("views", 0),
        "video_likes": video.get("likes", 0),
        "total_comments": len(comments_df),
        "total_replies": total_replies,
    }


def analyse_comments(comments_df):
    """Calculate top-level comment statistics."""

    total_comments = len(comments_df)

    if total_comments == 0:
        likes = pd.Series(dtype="int64")
    else:
        likes = comments_df["likes"]

    liked_comments = int((likes > 0).sum())

    return {
        "total_comments": total_comments,
        "likes": {
            "mean": float(likes.mean()) if total_comments else 0,
            "median": float(likes.median()) if total_comments else 0,
            "std": float(likes.std()) if total_comments > 1 else 0,
            "min": int(likes.min()) if total_comments else 0,
            "max": int(likes.max()) if total_comments else 0,
            "liked_comments": liked_comments,
            "unliked_comments": total_comments - liked_comments,
            "liked_percentage": round(
                liked_comments / total_comments * 100, 2
            ) if total_comments else 0,
        },
        "top_comments": (
            comments_df.nlargest(10, "likes")[["comment", "likes"]]
            .to_dict(orient="records")
            if total_comments else []
        ),
    }


def analyse_replies(comments_df):
    """Calculate reply engagement statistics."""

    if "replies" not in comments_df.columns:
        return {
            "total_replies": 0,
            "likes": None,
        }

    all_replies = [
        reply
        for replies in comments_df["replies"]
        if isinstance(replies, list)
        for reply in replies
        if isinstance(reply, dict)
    ]

    if not all_replies:
        return {
            "total_replies": 0,
            "likes": None,
        }

    replies_df = pd.DataFrame(all_replies)

    if "likes" not in replies_df.columns:
        replies_df["likes"] = 0

    likes = (
        pd.to_numeric(replies_df["likes"], errors="coerce")
        .fillna(0)
        .astype(int)
    )

    total_replies = len(replies_df)
    liked_replies = int((likes > 0).sum())

    return {
        "total_replies": total_replies,
        "likes": {
            "mean": float(likes.mean()),
            "median": float(likes.median()),
            "std": float(likes.std()) if total_replies > 1 else 0,
            "min": int(likes.min()),
            "max": int(likes.max()),
            "liked_replies": liked_replies,
            "unliked_replies": total_replies - liked_replies,
            "liked_percentage": round(
                liked_replies / total_replies * 100, 2
            ),
        },
    }


def analyse_reply_distribution(comments_df):
    """Calculate reply distribution across top-level comments."""

    if "replies" in comments_df.columns:
        reply_counts = comments_df["replies"].apply(
            lambda value: len(value) if isinstance(value, list) else 0
        )
    else:
        reply_counts = pd.Series(dtype="int64")

    total_comments = len(comments_df)
    comments_with_replies = int((reply_counts > 0).sum())

    return {
        "mean": float(reply_counts.mean()) if total_comments else 0,
        "median": float(reply_counts.median()) if total_comments else 0,
        "std": float(reply_counts.std()) if total_comments > 1 else 0,
        "min": int(reply_counts.min()) if total_comments else 0,
        "max": int(reply_counts.max()) if total_comments else 0,
        "comments_with_replies": comments_with_replies,
        "comments_without_replies": total_comments - comments_with_replies,
        "percentage_with_replies": round(
            comments_with_replies / total_comments * 100, 2
        ) if total_comments else 0,
    }


def save_analysis(video_id, results):
    """Save complete analysis results as JSON."""

    paths.ensure_data_dirs()

    file_path = safe_video_path(paths.get_analysis_dir(), video_id)

    write_json_atomic(file_path, results, indent=4)

    return file_path


def analyse_video_data(video_id):
    """Run statistical analysis and display a concise terminal summary."""

    data = load_processed_data(video_id)
    comments_df = create_dataframe(data)

    results = {
        "video": analyse_video(data, comments_df),
        "comments": analyse_comments(comments_df),
        "replies": analyse_replies(comments_df),
        "reply_distribution": analyse_reply_distribution(comments_df),
    }

    analysis_path = save_analysis(video_id, results)

    # Display basic video details
    summary = results["video"]

    print("\n========== VIDEO DETAILS ==========")
    print("Title:", sanitize_terminal_text(summary["title"]))
    print("Views:", summary["views"])
    print("Video Likes:", summary["video_likes"])
    print("Total Comments:", summary["total_comments"])
    print("Total Replies:", summary["total_replies"])

    # Display top 10 comments
    print("\n========== TOP 10 COMMENTS ==========")

    for comment in results["comments"]["top_comments"]:
        print(
            f"{comment['likes']:,} likes | "
            f"{sanitize_terminal_text(comment['comment'])}"
        )

    print(f"\nFull analysis saved: {analysis_path}")

    return {
        "summary": summary,
        "top_comments": results["comments"]["top_comments"],
        "analysis_path": analysis_path,
    }
