"""Consensus command-line entry point."""

from __future__ import annotations

import logging
import os
from urllib.parse import parse_qs, urlparse

from . import paths
from .analyzer import analyse_video_data, print_top_comments
from .cleaner import clean_video_data
from .classification import run_classification
from .collector import get_comments, get_video_details
from .config import load_environment
from .errors import ConsensusError, DataError
from .reporter import generate_report, print_report, save_report
from .storage import read_json, save_data
from .validation import validate_video_id


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


def _classification_run_signature(video_id: str, user_question: str) -> str:
    """Read the signature of the classification run that just completed."""

    artifact_paths = paths.classification_artifact_paths(
        video_id,
        user_question,
    )

    metadata = read_json(artifact_paths["metadata"])

    if not isinstance(metadata, dict):
        raise DataError("Classification metadata must be a JSON object.")

    run_signature = metadata.get("run_signature")

    if not isinstance(run_signature, str) or not run_signature:
        raise DataError("Classification metadata has no run signature.")

    return run_signature


def _log_level() -> int:
    """Return the configured log level, defaulting to warnings only."""

    name = os.getenv("CONSENSUS_LOG_LEVEL", "WARNING").strip().upper()
    level = getattr(logging, name, None)

    return level if isinstance(level, int) else logging.WARNING


def _configure_logging() -> None:
    logging.basicConfig(
        level=_log_level(),
        format="%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%H:%M:%S",
    )


def _run_pipeline(video_id: str, user_question: str) -> int:
    print("\nCollecting data...")

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
    save_data(video_id, video_data)

    print("Cleaning and analysing...")

    # Clean data
    clean_video_data(video_id)

    # Analyse processed data (top comments are printed after the report)
    eda_results = analyse_video_data(
        video_id,
        show_top_comments=False,
        show_summary=False,
        show_path=False,
    )

    if not isinstance(eda_results, dict):
        raise ConsensusError(
            "Analysis did not return the expected results."
        )

    print("Classifying comments...")

    aggregation = run_classification(
        video_id=video_id,
        user_question=user_question,
    )

    # Prepare classification framework
    framework = {
        "question_interpretation": aggregation.get(
            "question_interpretation", ""
        ),
        "categories": aggregation.get("categories", []),
    }

    # Generate final audience intelligence report
    print("Generating report...")

    report = generate_report(
        user_question=user_question,
        video={
            **details,
            "video_id": video_id,
        },
        framework=framework,
        aggregation=aggregation,
        eda=eda_results["analysis"],
    )

    # Snapshot the shared per-video data used by the brief so a later run for
    # another question cannot silently change this report's presentation.
    analysis = eda_results["analysis"]
    analysis_video = analysis.get("video", {}) if isinstance(analysis, dict) else {}

    if not isinstance(analysis_video, dict):
        analysis_video = {}

    report_video = {
        **details,
        "video_id": video_id,
        "comments": analysis_video.get("total_comments"),
        "replies": analysis_video.get("total_replies"),
    }

    # Persist the report as the fifth question-specific artifact
    save_report(
        video_id=video_id,
        user_question=user_question,
        report=report,
        run_signature=_classification_run_signature(
            video_id,
            user_question,
        ),
        top_comments=eda_results["top_comments"],
        video=report_video,
    )

    print("Report saved.")

    # Display final report
    print_report(report)

    # Display the most-liked top-level comments last
    print_top_comments(eda_results["top_comments"], limit=5)

    return 0


def main() -> int:
    load_environment()
    _configure_logging()

    print("\nConsensus | YouTube Audience Intelligence")

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
