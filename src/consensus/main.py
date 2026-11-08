from urllib.parse import urlparse, parse_qs

from src.consensus.collector import get_comments, get_video_details
from src.consensus.storage import save_data
from src.consensus.cleaner import clean_video_data
from src.consensus.analyzer import analyse_video_data
from src.consensus.classification import run_classification


def extract_video_id(video_url):

    parsed_url = urlparse(video_url.strip())

    hostname = (parsed_url.hostname or "").lower()

    if hostname in ("www.youtube.com", "youtube.com", "m.youtube.com"):
        return parse_qs(parsed_url.query).get("v", [None])[0]

    elif hostname in ("youtu.be", "www.youtu.be"):
        return parsed_url.path.strip("/").split("/")[0]

    return None


def main():

    print("\n" + "=" * 55)
    print("                 CONSENSUS")
    print("          YouTube Audience Intelligence")
    print("=" * 55)

    video_url = input("\nEnter YouTube link: ")

    video_id = extract_video_id(video_url)

    if not video_id:
        print("Invalid YouTube URL")
        return

    user_question = input("\nEnter your research question: ").strip()

    if not user_question:
        print("Research question cannot be empty")
        return

    # Collect video details
    details = get_video_details(video_id)

    if not details:
        print("Video not found")
        return

    # Collect comments and replies
    comments = get_comments(video_id)

    # Combine collected data
    video_data = {
        "video_id": video_id,
        "video": details,
        "comments": comments
    }

    # Save raw data
    raw_path = save_data(video_id, video_data)
    print(f"Raw data saved: {raw_path}")

    # Clean data
    processed_path = clean_video_data(video_id)
    print(f"Processed data saved: {processed_path}")

    # Analyse processed data
    comments_df = analyse_video_data(video_id)

    print("\nAnalysis completed successfully.")

    # Classify audience comments
    print("\nStarting audience classification...")

    aggregation = run_classification(
        video_id=video_id,
        user_question=user_question
    )

    print("\nClassification completed successfully.")

    # Display summary
    print("\n" + "=" * 55)
    print("             PIPELINE COMPLETED")
    print("=" * 55)

    print(f"Video ID: {video_id}")
    print(f"Comments collected: {len(comments)}")
    print(f"Comments classified: {aggregation['total_comments_classified']}")
    print(f"Relevant comments: {aggregation['relevant_comments']}")
    print(f"Irrelevant comments: {aggregation['irrelevant_comments']}")

    print("\nClassification distribution:")

    for category, values in aggregation["classification_distribution"].items():
        print(
            f"{category:<30} "
            f"{values['count']:>6} "
            f"({values['percentage']:.2f}%)"
        )

    print("\nConsensus pipeline finished successfully.")


if __name__ == "__main__":
    main()
