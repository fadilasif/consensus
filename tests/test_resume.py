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


def test_resume_reuses_stored_configured_batch_size(tmp_path, monkeypatch):
    monkeypatch.setenv("CONSENSUS_DATA_DIR", str(tmp_path))

    processed = tmp_path / "processed"
    processed.mkdir(parents=True)
    comments = [
        {"comment": f"Comment {index} about the product"}
        for index in range(12)
    ]
    (processed / "dQw4w9WgXcQ.json").write_text(
        json.dumps({"video": {"title": "Title"}, "comments": comments}),
        encoding="utf-8",
    )

    artifact_paths = paths.classification_artifact_paths(
        "dQw4w9WgXcQ",
        "Question?",
    )
    artifact_paths["base"].mkdir(parents=True)
    artifact_paths["framework"].write_text(
        json.dumps({
            "video_id": "dQw4w9WgXcQ",
            "user_question": "Question?",
            "framework": make_framework(),
        }),
        encoding="utf-8",
    )

    interrupted = {"value": True}

    def fake_classify_chunk(chunk, chunk_number, *args, **kwargs):
        if interrupted["value"] and chunk_number > 1:
            raise RuntimeError("interrupted")

        return (
            [make_result(item["comment_index"]) for item in chunk],
            {
                "chunk": chunk_number,
                "comments": len(chunk),
                "questions": len(chunk) * 2,
                "input_tokens": 10,
                "output_tokens": 2,
            },
        )

    monkeypatch.setattr(classification, "classify_chunk", fake_classify_chunk)

    # First run: 12 pending comments -> batch size 4, one batch checkpointed.
    with pytest.raises(classification.ClassificationIncompleteError):
        classification.run_classification("dQw4w9WgXcQ", "Question?")

    stored = json.loads(artifact_paths["metadata"].read_text(encoding="utf-8"))
    assert stored["configured_batch_size"] == 4

    journal_name = (
        f"dQw4w9WgXcQ_{paths.question_key('Question?')}"
        f"_{stored['run_signature'][:12]}.jsonl"
    )
    assert (artifact_paths["base"] / journal_name).is_file()

    # Second run: only 8 comments remain, which would choose a batch size of 1.
    assert classification.choose_batch_size(8) == 1

    batch_sizes = []
    create_chunks = classification.create_chunks

    def spy_create_chunks(items, batch_size):
        batch_sizes.append(batch_size)
        return create_chunks(items, batch_size)

    monkeypatch.setattr(classification, "create_chunks", spy_create_chunks)
    interrupted["value"] = False

    aggregation = classification.run_classification("dQw4w9WgXcQ", "Question?")

    assert batch_sizes == [4]
    assert aggregation["configured_batch_size"] == 4
    # Metrics from the interrupted run must not be overwritten by the resume.
    assert aggregation["requests"] == 3
    assert aggregation["total_input_tokens"] == 30
    assert aggregation["total_output_tokens"] == 6


def test_resume_ignores_results_from_a_previous_signature(tmp_path, monkeypatch):
    monkeypatch.setenv("CONSENSUS_DATA_DIR", str(tmp_path))

    processed = tmp_path / "processed"
    processed.mkdir(parents=True)

    def write_comments(texts):
        (processed / "dQw4w9WgXcQ.json").write_text(
            json.dumps({
                "video": {"title": "Title"},
                "comments": [{"comment": text} for text in texts],
            }),
            encoding="utf-8",
        )

    artifact_paths = paths.classification_artifact_paths(
        "dQw4w9WgXcQ",
        "Question?",
    )
    artifact_paths["base"].mkdir(parents=True)
    artifact_paths["framework"].write_text(
        json.dumps({
            "video_id": "dQw4w9WgXcQ",
            "user_question": "Question?",
            "framework": make_framework(),
        }),
        encoding="utf-8",
    )

    interrupted = {"value": False}
    calls: list[int] = []

    def fake_classify_chunk(chunk, chunk_number, *args, **kwargs):
        calls.append(chunk_number)

        if interrupted["value"]:
            raise RuntimeError("interrupted")

        results = []

        for item in chunk:
            result = make_result(item["comment_index"])
            result["comment"] = item["text"]
            results.append(result)

        return results, {
            "chunk": chunk_number,
            "comments": len(chunk),
            "questions": len(chunk) * 2,
            "input_tokens": 10,
            "output_tokens": 2,
        }

    monkeypatch.setattr(classification, "classify_chunk", fake_classify_chunk)

    first_texts = [f"First set comment {index}" for index in range(4)]
    write_comments(first_texts)
    classification.run_classification("dQw4w9WgXcQ", "Question?")

    # A changed comment set produces a new signature while the completed
    # results file still belongs to the previous signature.
    second_texts = [f"Second set comment {index}" for index in range(4)]
    write_comments(second_texts)
    # A changed comment sample invalidates the generated framework; this test
    # is about results reuse, so supply a framework without calling Groq.
    monkeypatch.setattr(
        classification,
        "generate_framework",
        lambda **kwargs: make_framework(),
    )
    interrupted["value"] = True
    calls.clear()

    with pytest.raises(classification.ClassificationIncompleteError):
        classification.run_classification("dQw4w9WgXcQ", "Question?")

    assert calls  # The changed run really attempted new batches.

    interrupted["value"] = False
    calls.clear()
    classification.run_classification("dQw4w9WgXcQ", "Question?")

    assert calls  # Resuming reclassifies instead of reusing stale results.

    results = json.loads(artifact_paths["results"].read_text(encoding="utf-8"))
    assert {item["comment"] for item in results} == set(second_texts)

    # A completed run still reuses its results without new requests.
    calls.clear()
    classification.run_classification("dQw4w9WgXcQ", "Question?")

    assert calls == []


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


def write_processed_comments(tmp_path, texts):
    processed = tmp_path / "processed"
    processed.mkdir(parents=True, exist_ok=True)
    (processed / "dQw4w9WgXcQ.json").write_text(
        json.dumps({
            "video": {"title": "Title"},
            "comments": [{"comment": text} for text in texts],
        }),
        encoding="utf-8",
    )


def write_framework_artifact(artifact_paths, **extra):
    artifact_paths["base"].mkdir(parents=True, exist_ok=True)
    payload = {
        "video_id": "dQw4w9WgXcQ",
        "user_question": "Question?",
        "framework": make_framework(),
    }
    payload.update(extra)
    artifact_paths["framework"].write_text(
        json.dumps(payload),
        encoding="utf-8",
    )


def fake_classification(calls):
    def classify_chunk(chunk, chunk_number, *args, **kwargs):
        calls.append(chunk_number)
        return (
            [make_result(item["comment_index"]) for item in chunk],
            {
                "chunk": chunk_number,
                "comments": len(chunk),
                "questions": len(chunk) * 2,
                "input_tokens": 10,
                "output_tokens": 2,
            },
        )

    return classify_chunk


def test_load_journal_skips_invalid_records(tmp_path):
    journal = tmp_path / "run.jsonl"
    journal.write_text(
        "\n".join([
            json.dumps({"kind": "result", "result": {"comment_index": 0}}),
            json.dumps({"kind": "result", "result": make_result(1)}),
            json.dumps({"kind": "metrics", "metrics": {"chunk": 1}}),
        ]) + "\n",
        encoding="utf-8",
    )

    results, metrics = classification.load_journal(journal)

    assert results == {1: make_result(1)}
    assert metrics == {}


def test_corrupt_results_file_falls_back_to_journal(tmp_path, monkeypatch):
    monkeypatch.setenv("CONSENSUS_DATA_DIR", str(tmp_path))
    write_processed_comments(
        tmp_path,
        [f"Comment {index} about the product" for index in range(4)],
    )
    artifact_paths = paths.classification_artifact_paths(
        "dQw4w9WgXcQ",
        "Question?",
    )
    write_framework_artifact(artifact_paths)

    calls = []
    monkeypatch.setattr(
        classification,
        "classify_chunk",
        fake_classification(calls),
    )

    classification.run_classification("dQw4w9WgXcQ", "Question?")
    assert calls

    # Simulate a results file truncated by a crash after the journal was
    # flushed. The checkpoint journal still owns every completed record.
    artifact_paths["results"].write_text("{not json", encoding="utf-8")
    calls.clear()

    aggregation = classification.run_classification(
        "dQw4w9WgXcQ",
        "Question?",
    )

    assert calls == []
    assert aggregation["total_comments_classified"] == 4
    assert len(
        json.loads(artifact_paths["results"].read_text(encoding="utf-8"))
    ) == 4


def test_corrupt_framework_artifact_is_regenerated(tmp_path, monkeypatch):
    monkeypatch.setenv("CONSENSUS_DATA_DIR", str(tmp_path))
    write_processed_comments(tmp_path, ["A comment", "Another comment"])
    artifact_paths = paths.classification_artifact_paths(
        "dQw4w9WgXcQ",
        "Question?",
    )
    artifact_paths["base"].mkdir(parents=True)
    artifact_paths["framework"].write_text("{not json", encoding="utf-8")

    generated = []

    def fake_generate_framework(**kwargs):
        generated.append(kwargs)
        return make_framework()

    monkeypatch.setattr(
        classification,
        "generate_framework",
        fake_generate_framework,
    )
    calls = []
    monkeypatch.setattr(
        classification,
        "classify_chunk",
        fake_classification(calls),
    )

    aggregation = classification.run_classification(
        "dQw4w9WgXcQ",
        "Question?",
    )

    assert generated
    assert aggregation["total_comments_classified"] == 2
    saved = json.loads(
        artifact_paths["framework"].read_text(encoding="utf-8")
    )
    assert saved["framework"] == make_framework()
    assert saved["generation_signature"]


def test_stale_framework_signature_forces_regeneration(tmp_path, monkeypatch):
    monkeypatch.setenv("CONSENSUS_DATA_DIR", str(tmp_path))
    write_processed_comments(tmp_path, ["A comment", "Another comment"])
    artifact_paths = paths.classification_artifact_paths(
        "dQw4w9WgXcQ",
        "Question?",
    )
    write_framework_artifact(artifact_paths, generation_signature="stale")

    generated = []

    def fake_generate_framework(**kwargs):
        generated.append(kwargs)
        return make_framework()

    monkeypatch.setattr(
        classification,
        "generate_framework",
        fake_generate_framework,
    )
    calls = []
    monkeypatch.setattr(
        classification,
        "classify_chunk",
        fake_classification(calls),
    )

    classification.run_classification("dQw4w9WgXcQ", "Question?")

    assert generated

    # The regenerated artifact records the current inputs and is reused next.
    generated.clear()
    calls.clear()
    classification.run_classification("dQw4w9WgXcQ", "Question?")

    assert generated == []
    assert calls == []


def test_framework_signature_changes_with_prompt(monkeypatch):
    kwargs = {
        "video_id": "dQw4w9WgXcQ",
        "video_title": "Title",
        "user_question": "Question?",
        "comments": [{"comment_index": 0, "text": "A comment"}],
    }
    baseline = classification.build_framework_signature(**kwargs)

    monkeypatch.setattr(
        classification,
        "FRAMEWORK_SYSTEM_PROMPT",
        "changed prompt",
    )

    assert classification.build_framework_signature(**kwargs) != baseline
