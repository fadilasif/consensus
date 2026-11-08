"""Consensus command-line entry point."""

from __future__ import annotations

import logging
from urllib.parse import parse_qs, urlparse

from .analyzer import analyse_video_data
from .cleaner import clean_video_data
from .classification import run_classification
from .collector import get_comments, get_video_details
from .config import load_environment
from .errors import ConsensusError
from .storage import save_data
from .validation import sanitize_terminal_text, validate_video_id


def extract_video_id(video_url: str) -> str | None:
    """Extract and validate a YouTube video ID from a URL."""

    if not isinstance(video_url, str):
        return None

    parsed_url = urlparse(video_url.strip())
    hostname = (parsed_url.hostname or "").lower()

    if hostname.startswith("www."):
        hostname = hostname[4:]

    value = None

    if hostname in (
        "youtube.com",
        "m.youtube.com",
        "music.youtube.com",
        "youtube-nocookie.com",
    ):
        if parsed_url.path == "/watch":
            value = parse_qs(parsed_url.query).get("v", [None])[0]
        elif parsed_url.path.startswith(("/shorts/", "/embed/", "/live/")):
            parts = parsed_url.path.strip("/").split("/")
            if len(parts) >= 2:
                value = parts[1]

    elif hostname == "youtu.be":
        parts = parsed_url.path.strip("/").split("/")
        if parts and parts[0]:
            value = parts[0]

    if not value:
        return None

    try:
        return validate_video_id(value)
    except ConsensusError:
        return None


def _run_pipeline(video_id: str, user_question: str) -> int:
    # Collect video details
    details = get_video_details(video_id)

    if not details:
        print("Video not found")
        return 1

    # Collect comments and replies
    comments = get_comments(video_id)

    # Combine collected data
    video_data = {
        "video_id": video_id,
        "video": details,
        "comments": comments,
    }

    # Save raw data
    raw_path = save_data(video_id, video_data)
    print(f"Raw data saved: {raw_path}")

    # Clean data
    processed_path = clean_video_data(video_id)
    print(f"Processed data saved: {processed_path}")

    # Analyse processed data
    analyse_video_data(video_id)

    print("\nAnalysis completed successfully.")

    # Classify audience comments
    print("\nStarting audience classification...")

    aggregation = run_classification(
        video_id=video_id,
        user_question=user_question,
    )

    print("\nClassification completed successfully.")

    # Display summary
    print("\n" + "=" * 55)
    print("             PIPELINE COMPLETED")
    print("=" * 55)

    print(f"Video ID: {video_id}")
    print(f"Top-level comments collected: {len(comments)}")
    print(
        "Replies collected (not classified): "
        f"{aggregation.get('total_replies_in_video', 0)}"
    )
    print(
        "Top-level comments classified: "
        f"{aggregation['total_comments_classified']}"
    )
    print(f"Relevant comments: {aggregation['relevant_comments']}")
    print(f"Irrelevant comments: {aggregation['irrelevant_comments']}")

    print("\nClassification distribution:")

    for category, values in aggregation["classification_distribution"].items():
        print(
            f"{sanitize_terminal_text(category):<30} "
            f"{values['count']:>6} "
            f"({values['percentage']:.2f}%)"
        )

    print("\nConsensus pipeline finished successfully.")
    return 0


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%H:%M:%S",
    )

    load_environment()

    print("\n" + "=" * 55)
    print("                 CONSENSUS")
    print("          YouTube Audience Intelligence")
    print("=" * 55)

    try:
        video_url = input("\nEnter YouTube link: ")
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled.")
        return 130

    video_id = extract_video_id(video_url)

    if not video_id:
        print("Invalid YouTube URL")
        return 2

    try:
        user_question = input("\nEnter your research question: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled.")
        return 130

    if not user_question:
        print("Research question cannot be empty")
        return 2

    try:
        return _run_pipeline(video_id, user_question)
    except ConsensusError as error:
        print(f"\nError: {error}")
        return 1
    except KeyboardInterrupt:
        print("\nCancelled.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
