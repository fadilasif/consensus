from __future__ import annotations

import logging

import pytest

from consensus import main
from consensus.main import extract_video_id


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://youtube.com/watch?v=dQw4w9WgXcQ&t=10",
        "https://m.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://music.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://youtu.be/dQw4w9WgXcQ",
        "https://www.youtube.com/shorts/dQw4w9WgXcQ",
        "https://www.youtube.com/embed/dQw4w9WgXcQ",
        "https://www.youtube.com/live/dQw4w9WgXcQ",
        "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ",
    ],
)
def test_extract_video_id_valid_urls(url):
    assert extract_video_id(url) == "dQw4w9WgXcQ"


@pytest.mark.parametrize(
    "url",
    [
        "",
        "not a url",
        "https://example.com/watch?v=dQw4w9WgXcQ",
        "https://youtube.com.evil.example/watch?v=dQw4w9WgXcQ",
        "https://www.youtube.com/watch?v=short",
        "https://www.youtube.com/watch?v=../../etc/passwd",
        "https://youtu.be/",
    ],
)
def test_extract_video_id_invalid_urls(url):
    assert extract_video_id(url) is None


def test_log_level_defaults_to_warning(monkeypatch):
    monkeypatch.delenv("CONSENSUS_LOG_LEVEL", raising=False)

    assert main._log_level() == logging.WARNING


def test_log_level_is_configurable(monkeypatch):
    monkeypatch.setenv("CONSENSUS_LOG_LEVEL", "DEBUG")

    assert main._log_level() == logging.DEBUG


def test_invalid_log_level_falls_back_to_warning(monkeypatch):
    monkeypatch.setenv("CONSENSUS_LOG_LEVEL", "not-a-level")

    assert main._log_level() == logging.WARNING


def test_pipeline_generates_persists_and_prints_report_then_top_comments(
    monkeypatch,
    capsys,
):
    events: list[str] = []
    captured: dict = {}

    aggregation = {
        "total_replies_in_video": 0,
        "total_comments_classified": 1,
        "relevant_comments": 1,
        "irrelevant_comments": 0,
        "classification_distribution": {
            "BUY": {"count": 1, "percentage": 100.0},
        },
        "question_interpretation": "Buying intent",
        "categories": [{"name": "BUY"}],
    }
    eda_results = {
        "summary": {"title": "Example"},
        "top_comments": [{"comment": "Top comment", "likes": 5}],
        "analysis": {"comments": {"total_comments": 1}},
        "analysis_path": "/analysis.json",
    }

    monkeypatch.setattr(
        main,
        "get_video_details",
        lambda video_id: {"title": "Example", "views": 1, "likes": 2},
    )
    monkeypatch.setattr(
        main,
        "get_comments",
        lambda video_id: [{"comment": "Top comment", "likes": 5, "replies": []}],
    )
    monkeypatch.setattr(main, "save_data", lambda video_id, data: "/raw.json")
    monkeypatch.setattr(
        main,
        "clean_video_data",
        lambda video_id: "/processed.json",
    )

    def fake_analysis(
        video_id,
        *,
        show_top_comments=True,
        show_summary=True,
        show_path=True,
    ):
        events.append("eda")
        captured["show_top_comments"] = show_top_comments
        captured["show_summary"] = show_summary
        captured["show_path"] = show_path
        return eda_results

    monkeypatch.setattr(main, "analyse_video_data", fake_analysis)

    def fake_classification(*, video_id, user_question):
        events.append("classify")
        return aggregation

    monkeypatch.setattr(main, "run_classification", fake_classification)

    def fake_generate(**kwargs):
        events.append("generate")
        captured["generate"] = kwargs
        return "# REPORT"

    monkeypatch.setattr(main, "generate_report", fake_generate)
    monkeypatch.setattr(
        main,
        "_classification_run_signature",
        lambda video_id, user_question: "run-signature",
    )

    def fake_save(**kwargs):
        events.append("save")
        captured["save"] = kwargs
        return "/report.json"

    monkeypatch.setattr(main, "save_report", fake_save)

    def fake_print_report(report):
        events.append("print_report")
        captured["printed_report"] = report

    monkeypatch.setattr(main, "print_report", fake_print_report)

    def fake_print_top_comments(comments, limit=5):
        events.append("print_top_comments")
        captured["printed_comments"] = comments
        captured["top_limit"] = limit

    monkeypatch.setattr(main, "print_top_comments", fake_print_top_comments)

    result = main._run_pipeline("dQw4w9WgXcQ", "Should I buy it?")

    assert result == 0
    assert events == [
        "eda",
        "classify",
        "generate",
        "save",
        "print_report",
        "print_top_comments",
    ]

    assert captured["show_top_comments"] is False
    assert captured["show_summary"] is False
    assert captured["show_path"] is False
    assert captured["generate"]["user_question"] == "Should I buy it?"
    assert captured["generate"]["aggregation"] is aggregation
    assert captured["generate"]["eda"] is eda_results["analysis"]
    assert captured["save"]["report"] == "# REPORT"
    assert captured["save"]["run_signature"] == "run-signature"
    assert captured["save"]["top_comments"] == eda_results["top_comments"]
    assert captured["save"]["video"]["video_id"] == "dQw4w9WgXcQ"
    assert captured["printed_report"] == "# REPORT"
    assert captured["printed_comments"] == eda_results["top_comments"]
    assert captured["top_limit"] == 5

    output = capsys.readouterr().out
    progress = [
        "Collecting data...",
        "Cleaning and analysing...",
        "Classifying comments...",
        "Generating report...",
    ]

    positions = [output.index(message) for message in progress]
    assert positions == sorted(positions)

    assert "Video details" not in output
    assert "Report saved." in output
    assert "/report.json" not in output
