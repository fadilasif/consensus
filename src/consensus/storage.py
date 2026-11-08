
import json
from pathlib import Path


DATA_DIR = Path(__file__).resolve().parent / "data" / "raw"


def save_data(video_id, data):
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    file_path = DATA_DIR / f"{video_id}.json"

    with open(file_path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4, ensure_ascii=False)

    return file_path


def load_data(video_id):
    file_path = DATA_DIR / f"{video_id}.json"

    with open(file_path, "r", encoding="utf-8") as file:
        return json.load(file)
