
import json
from pathlib import Path

import pandas as pd


BASE_DIR = Path(__file__).resolve().parent
PROCESSED_DIR = BASE_DIR / "data" / "processed"
ANALYSIS_DIR = BASE_DIR / "data" / "analysis"


def load_processed_data(video_id):
    """Load processed video data."""

    file_path = PROCESSED_DIR / f"{video_id}.json"

    with open(file_path, "r", encoding="utf-8") as file:
        return json.load(file)


def create_dataframe(data):
    """Create a DataFrame containing top-level comments and nested replies."""

    return pd.DataFrame(data["comments"])


def analyse_video(data, comments_df):
    """Calculate basic video statistics."""

    video = data["video"]

    return {
        "title": video["title"],
        "views": video["views"],
        "video_likes": video["likes"],
        "total_comments": len(comments_df),
        "total_replies": int(comments_df["replies"].apply(len).sum())
    }


def analyse_comments(comments_df):
    """Calculate top-level comment statistics."""

    likes = comments_df["likes"]
    total_comments = len(comments_df)
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
            ) if total_comments else 0
        },
        "top_comments": (
            comments_df.nlargest(10, "likes")[["comment", "likes"]]
            .to_dict(orient="records")
        )
    }


def analyse_replies(comments_df):
    """Calculate reply engagement statistics."""

    all_replies = [
        reply
        for replies in comments_df["replies"]
        for reply in replies
    ]

    if not all_replies:
        return {
            "total_replies": 0,
            "likes": None
        }

    replies_df = pd.DataFrame(all_replies)
    likes = replies_df["likes"]

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
            )
        }
    }


def analyse_reply_distribution(comments_df):
    """Calculate reply distribution across top-level comments."""

    reply_counts = comments_df["replies"].apply(len)

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
        ) if total_comments else 0
    }


def save_analysis(video_id, results):
    """Save complete analysis results as JSON."""

    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)

    file_path = ANALYSIS_DIR / f"{video_id}.json"

    with open(file_path, "w", encoding="utf-8") as file:
        json.dump(results, file, indent=4, ensure_ascii=False)

    return file_path



def analyse_video_data(video_id):
    """Run statistical analysis and display a concise terminal summary."""

    data = load_processed_data(video_id)
    comments_df = create_dataframe(data)

    results = {
        "video": analyse_video(data, comments_df),
        "comments": analyse_comments(comments_df),
        "replies": analyse_replies(comments_df),
        "reply_distribution": analyse_reply_distribution(comments_df)
    }

    analysis_path = save_analysis(video_id, results)

    # Display basic video details
    summary = results["video"]

    print("\n========== VIDEO DETAILS ==========")
    print("Title:", summary["title"])
    print("Views:", summary["views"])
    print("Video Likes:", summary["video_likes"])
    print("Total Comments:", summary["total_comments"])
    print("Total Replies:", summary["total_replies"])

    # Display top 10 comments
    print("\n========== TOP 10 COMMENTS ==========")

    for comment in results["comments"]["top_comments"]:
        print(f"{comment['likes']:,} likes | {comment['comment']}")

    print(f"\nFull analysis saved: {analysis_path}")

    return {
        "summary": summary,
        "top_comments": results["comments"]["top_comments"],
        "analysis_path": analysis_path
    }
