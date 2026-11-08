from __future__ import annotations

import json

import pytest

from consensus import classification, paths


def make_framework() -> dict:
    return {
        "question_interpretation": "Interpretation",
        "classification_instructions": "Choose.",
        "categories": [
            {"name": "POSITIVE", "description": "Positive."},
            {"name": "NEGATIVE", "description": "Negative."},
            {"name": "NEUTRAL", "description": "Neutral."},
        ],
    }


def make_result(index: int = 0) -> dict:
    return {
        "comment_index": index,
        "comment": "comment",
        "classification": "POSITIVE",
        "source": "subq",
        "relevance_probability": 0.9,
        "stance_choice": "POSITIVE",
        "stance_probabilities": {
            "POSITIVE": 0.8,
            "NEGATIVE": 0.1,
            "NEUTRAL": 0.1,
        },
        "stance_top_probability": 0.8,
        "needs_review": False,
        "soft": {
            "POSITIVE": 0.72,
            "NEGATIVE": 0.09,
            "NEUTRAL": 0.09,
            "IRRELEVANT": 0.1,
        },
    }


def signature(**overrides):
    values = {
        "video_id": "dQw4w9WgXcQ",
        "video_title": "Title",
        "user_question": "Question?",
        "comments": [{"comment_index": 0, "text": "A comment"}],
        "analytics": {"views": 10},
        "framework": make_framework(),
    }
    values.update(overrides)
    return classification.build_run_signature(**values)


def test_signature_changes_with_comment_text():
    assert signature() != signature(
        comments=[{"comment_index": 0, "text": "Different"}]
    )


def test_signature_changes_with_question():
    assert signature() != signature(user_question="Another question?")


def test_signature_changes_with_framework():
    framework = make_framework()
    framework["categories"][0]["description"] = "Changed."
    assert signature() != signature(framework=framework)


def test_signature_changes_with_settings(monkeypatch):
    baseline = signature()
    monkeypatch.setattr(classification, "MAX_COMMENT_CHARS", 999)
    assert signature() != baseline


def test_signature_changes_with_prompt(monkeypatch):
    baseline = signature()
    monkeypatch.setattr(
        classification,
        "RELEVANCE_CRITERIA",
        {"true": "changed", "false": "changed"},
    )
    assert signature() != baseline


def test_journal_roundtrip_and_corrupt_line_handling(tmp_path):
    journal = tmp_path / "run.jsonl"
    result = make_result()

    classification.append_journal(
        journal,
        [result],
        {"chunk": 1, "comments": 1, "questions": 2,
         "input_tokens": 10, "output_tokens": 2},
    )
    journal.write_text(
        journal.read_text(encoding="utf-8") + "not json\n",
        encoding="utf-8",
    )

    results, metrics = classification.load_journal(journal)

    assert results == {0: result}
    assert metrics[1]["input_tokens"] == 10


def test_load_results_file_ignores_malformed_entries(tmp_path):
    path = tmp_path / "results.json"
    path.write_text(
        json.dumps([make_result(0), "bad", {"comment_index": "x"}]),
        encoding="utf-8",
    )

    assert classification.load_results_file(path) == {0: make_result(0)}


def test_archive_existing_run_copies_without_deleting(tmp_path, monkeypatch):
    monkeypatch.setenv("CONSENSUS_DATA_DIR", str(tmp_path))
    artifact_paths = paths.classification_artifact_paths(
        "dQw4w9WgXcQ",
        "Question?",
    )
    artifact_paths["base"].mkdir(parents=True)
    artifact_paths["results"].write_text("[]", encoding="utf-8")
    artifact_paths["metadata"].write_text("{}", encoding="utf-8")

    archive_dir = classification.archive_existing_run(artifact_paths)

    assert archive_dir is not None
    assert (archive_dir / artifact_paths["results"].name).exists()
    assert (archive_dir / artifact_paths["metadata"].name).exists()
    # Originals are preserved.
    assert artifact_paths["results"].exists()


def test_metadata_totals_preserve_prior_metrics():
    metrics = {
        1: {
            "chunk": 1,
            "comments": 1,
            "questions": 2,
            "input_tokens": 10,
            "output_tokens": 2,
        }
    }
    prior = {"requests": 4, "input_tokens": 100, "output_tokens": 20}

    totals = classification._metadata_totals(metrics, prior)

    assert totals["requests_total"] == 5
    assert totals["total_input_tokens"] == 110
    assert totals["total_output_tokens"] == 22


def test_aggregate_results_preserves_prior_totals():
    metrics = [
        {
            "chunk": 1,
            "comments": 1,
            "questions": 2,
            "input_tokens": 10,
            "output_tokens": 2,
        }
    ]

    aggregation = classification.aggregate_results(
        results=[make_result()],
        framework=make_framework(),
        video_id="dQw4w9WgXcQ",
        video_title="Title",
        user_question="Question?",
        total_video_comments=1,
        request_metrics=metrics,
        batch_size=1,
        total_replies=3,
        prior_totals={"requests": 4, "input_tokens": 100, "output_tokens": 20},
    )

    assert aggregation["requests"] == 5
    assert aggregation["total_input_tokens"] == 110
    assert aggregation["total_output_tokens"] == 22
    assert aggregation["average_input_tokens_per_comment"] == 110.0
    assert aggregation["total_replies_in_video"] == 3
    assert aggregation["classification_population"] == "top_level_comments"
    assert aggregation["average_tokens_per_comment"] == 110.0
    assert aggregation["comments_per_request"] == {
        "configured_batch_size": 1,
        "average": 1.0,
        "maximum": 1,
    }
    assert aggregation["llm_fallback_used"] == 0
