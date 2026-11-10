from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from consensus import paths, reporter
from consensus.errors import APIError


class FakeCompletions:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)

        if isinstance(outcome, BaseException):
            raise outcome

        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=outcome),
                )
            ]
        )


class FakeClient:
    def __init__(self, outcomes):
        self.completions = FakeCompletions(outcomes)
        self.chat = SimpleNamespace(completions=self.completions)


class RetryableHTTPError(Exception):
    status_code = 503


class NonRetryableHTTPError(Exception):
    status_code = 400


def make_inputs() -> dict:
    return {
        "user_question": "Should I buy it or wait?",
        "video": {"video_id": "dQw4w9WgXcQ", "title": "Example"},
        "framework": {
            "question_interpretation": "Buying intent",
            "categories": [
                {"name": "BUY", "description": "Buy now."},
                {"name": "WAIT", "description": "Wait."},
                {"name": "UNSURE", "description": "Unsure."},
            ],
        },
        "aggregation": {
            "total_comments_classified": 4,
            "relevant_comments": 3,
            "irrelevant_comments": 1,
            "classification_distribution": {
                "BUY": {"count": 1, "percentage": 25.0},
                "WAIT": {"count": 2, "percentage": 50.0},
                "UNSURE": {"count": 0, "percentage": 0.0},
                "IRRELEVANT": {"count": 1, "percentage": 25.0},
            },
        },
        "eda": {
            "video": {"views": 100, "video_likes": 10},
            "comments": {
                "total_comments": 4,
                "likes": {"mean": 2.5, "median": 2, "max": 5},
                "top_comments": [
                    {
                        "comment": f"Comment number {index:02d}",
                        "likes": index,
                        "replies": [{"comment": "A reply", "likes": 9999}],
                    }
                    for index in range(12)
                ],
            },
        },
    }


def test_prepare_report_context_includes_only_ranked_top_ten_comments():
    inputs = make_inputs()

    context = reporter.prepare_report_context(**inputs)

    assert context["research_question"] == inputs["user_question"]
    assert context["classification_results"] == inputs["aggregation"]
    assert "top_comments" not in context["exploratory_data_analysis"]["comments"]
    assert context["exploratory_data_analysis"]["comments"]["total_comments"] == 4

    top_comments = context["most_liked_comments"]
    assert len(top_comments) == reporter.SUPPLEMENTARY_COMMENT_LIMIT == 10
    assert [item["likes"] for item in top_comments] == list(range(11, 1, -1))
    assert all(set(item) == {"comment", "likes"} for item in top_comments)
    assert top_comments[0] == {
        "comment": "Comment number 11",
        "likes": 11,
    }

    # The caller's EDA object is left untouched for later display.
    assert len(inputs["eda"]["comments"]["top_comments"]) == 12


def test_prepare_report_context_rejects_empty_question():
    inputs = make_inputs()
    inputs["user_question"] = "   "

    with pytest.raises(ValueError):
        reporter.prepare_report_context(**inputs)


def test_generate_report_sends_aggregate_and_top_ten_context(monkeypatch):
    inputs = make_inputs()
    client = FakeClient(["# REPORT\n\nGrounded report."])

    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setattr(reporter, "Groq", lambda api_key: client)

    report = reporter.generate_report(**inputs)

    assert report == "# REPORT\n\nGrounded report."
    assert len(client.completions.calls) == 1

    request = client.completions.calls[0]
    assert request["model"] == reporter.REPORT_MODEL
    assert request["reasoning_effort"] == reporter.REPORT_REASONING

    system_prompt = request["messages"][0]["content"]
    assert "2-3 connected paragraphs" in system_prompt
    assert "No headings, bullet points, numbered lists" in system_prompt
    assert "220-320 words" in system_prompt
    assert "#" not in system_prompt
    assert "Markdown" in system_prompt
    assert "Never treat engagement" in system_prompt
    assert "most_liked_comments" in system_prompt
    assert "Likes indicate engagement" in system_prompt
    assert "not necessarily agreement" in system_prompt
    assert "never let" in system_prompt
    assert "representative of the whole audience" in system_prompt
    assert "Compare patterns" in system_prompt
    assert "Do not invent bias" in system_prompt

    user_payload = json.loads(request["messages"][1]["content"])
    assert user_payload["research_question"] == inputs["user_question"]
    assert user_payload["classification_results"] == inputs["aggregation"]
    assert "top_comments" not in user_payload["exploratory_data_analysis"]["comments"]
    assert len(user_payload["most_liked_comments"]) == 10
    assert user_payload["most_liked_comments"][0]["comment"] == "Comment number 11"
    assert "Comment number 00" not in request["messages"][1]["content"]
    assert "Comment number 01" not in request["messages"][1]["content"]
    assert "A reply" not in request["messages"][1]["content"]
    assert "replies" not in request["messages"][1]["content"]


def test_generate_report_retries_transient_errors(monkeypatch):
    inputs = make_inputs()
    client = FakeClient(
        [
            RetryableHTTPError("busy"),
            RetryableHTTPError("busy"),
            "# REPORT",
        ]
    )
    sleeps: list[float] = []

    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setattr(reporter, "Groq", lambda api_key: client)
    monkeypatch.setattr(reporter.time, "sleep", sleeps.append)

    assert reporter.generate_report(**inputs) == "# REPORT"
    assert len(client.completions.calls) == 3
    assert sleeps == [
        reporter.REPORT_RETRY_BASE_DELAY,
        reporter.REPORT_RETRY_BASE_DELAY * 2,
    ]


def test_generate_report_stops_after_bounded_retries(monkeypatch):
    inputs = make_inputs()
    client = FakeClient([RetryableHTTPError("busy")] * reporter.REPORT_MAX_RETRIES)

    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setattr(reporter, "Groq", lambda api_key: client)
    monkeypatch.setattr(reporter.time, "sleep", lambda delay: None)

    with pytest.raises(APIError):
        reporter.generate_report(**inputs)

    assert len(client.completions.calls) == reporter.REPORT_MAX_RETRIES


def test_generate_report_does_not_retry_permanent_errors(monkeypatch):
    inputs = make_inputs()
    client = FakeClient([NonRetryableHTTPError("bad request"), "# REPORT"])

    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setattr(reporter, "Groq", lambda api_key: client)
    monkeypatch.setattr(reporter.time, "sleep", lambda delay: None)

    with pytest.raises(APIError):
        reporter.generate_report(**inputs)

    assert len(client.completions.calls) == 1


def test_print_report_has_no_decorative_separator(capsys):
    reporter.print_report("A short natural-language analysis.")

    output = capsys.readouterr().out

    assert "A short natural-language analysis." in output
    assert "Audience intelligence report" not in output
    assert "=" not in output


def test_save_report_writes_question_specific_fifth_artifact(tmp_path, monkeypatch):
    monkeypatch.setenv("CONSENSUS_DATA_DIR", str(tmp_path))
    question = "Should I buy it or wait?"

    report_path = reporter.save_report(
        video_id="dQw4w9WgXcQ",
        user_question=question,
        report="# REPORT\n\nBody.",
        run_signature="abc123",
        generated_at="2026-01-02T03:04:05+00:00",
    )

    expected = (
        tmp_path
        / "classifications"
        / f"dQw4w9WgXcQ_{paths.question_key(question)}_report.json"
    )

    assert report_path == expected
    assert report_path.exists()

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["video_id"] == "dQw4w9WgXcQ"
    assert payload["user_question"] == question
    assert payload["research_question"] == question
    assert payload["question_key"] == paths.question_key(question)
    assert payload["run_signature"] == "abc123"
    assert payload["generated_at"] == "2026-01-02T03:04:05+00:00"
    assert payload["model"] == reporter.REPORT_MODEL
    assert payload["reasoning_effort"] == reporter.REPORT_REASONING
    assert payload["report"] == "# REPORT\n\nBody."

    # The atomic writer leaves no temporary files behind.
    assert not list(report_path.parent.glob(".*.tmp"))


def test_save_report_snapshots_video_and_top_comments(tmp_path, monkeypatch):
    monkeypatch.setenv("CONSENSUS_DATA_DIR", str(tmp_path))

    report_path = reporter.save_report(
        "dQw4w9WgXcQ",
        "Question?",
        "Report",
        "signature",
        top_comments=[
            {"comment": "Useful", "likes": 4},
            {"comment": "   ", "likes": 99},
            {"comment": "Second", "likes": "7"},
        ],
        video={
            "video_id": "dQw4w9WgXcQ",
            "title": "Title",
            "views": 10,
            "ignored": True,
        },
    )

    payload = json.loads(report_path.read_text(encoding="utf-8"))

    assert payload["top_comments"] == [
        {"comment": "Useful", "likes": 4},
        {"comment": "Second", "likes": 7},
    ]
    assert payload["video"] == {
        "video_id": "dQw4w9WgXcQ",
        "title": "Title",
        "views": 10,
    }


def test_save_report_never_overwrites_another_question(tmp_path, monkeypatch):
    monkeypatch.setenv("CONSENSUS_DATA_DIR", str(tmp_path))

    first = reporter.save_report(
        "dQw4w9WgXcQ",
        "Question A",
        "Report A",
        "signature-a",
    )
    second = reporter.save_report(
        "dQw4w9WgXcQ",
        "Question B",
        "Report B",
        "signature-b",
    )

    assert first != second
    assert json.loads(first.read_text(encoding="utf-8"))["report"] == "Report A"
    assert json.loads(second.read_text(encoding="utf-8"))["report"] == "Report B"


def test_save_report_requires_report_and_signature(tmp_path, monkeypatch):
    monkeypatch.setenv("CONSENSUS_DATA_DIR", str(tmp_path))

    with pytest.raises(ValueError):
        reporter.save_report("dQw4w9WgXcQ", "Question", "", "signature")

    with pytest.raises(ValueError):
        reporter.save_report("dQw4w9WgXcQ", "Question", "Report", "")


def test_report_artifact_path_is_under_classifications(tmp_path, monkeypatch):
    monkeypatch.setenv("CONSENSUS_DATA_DIR", str(tmp_path))

    artifact_paths = paths.classification_artifact_paths(
        "dQw4w9WgXcQ",
        "Question?",
    )

    assert artifact_paths["report"].parent == tmp_path / "classifications"
    assert artifact_paths["report"].name.endswith("_report.json")
    assert isinstance(artifact_paths["report"], Path)
