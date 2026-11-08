from __future__ import annotations

from consensus import analyzer


def test_create_dataframe_handles_empty_comments():
    df = analyzer.create_dataframe({"video": {}, "comments": []})

    assert df.empty
    assert list(df.columns) == ["comment", "likes", "replies"]


def test_analysis_handles_empty_dataframe():
    df = analyzer.create_dataframe({"comments": []})

    assert analyzer.analyse_comments(df)["total_comments"] == 0
    assert analyzer.analyse_replies(df)["total_replies"] == 0
    assert analyzer.analyse_reply_distribution(df)["comments_with_replies"] == 0


def test_analysis_handles_non_list_comments():
    df = analyzer.create_dataframe({"comments": "not a list"})

    assert df.empty
