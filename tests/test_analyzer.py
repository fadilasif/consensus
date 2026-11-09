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


def test_top_comments_are_sorted_descending_and_exclude_replies():
    comments = [
        {
            "comment": f"Comment {index}",
            "likes": index,
            "replies": [{"comment": "A reply", "likes": 9999}],
        }
        for index in range(12)
    ]

    df = analyzer.create_dataframe({"comments": comments})
    top_comments = analyzer.analyse_comments(df)["top_comments"]

    assert len(top_comments) == 10
    assert [item["likes"] for item in top_comments] == list(range(11, 1, -1))
    assert all(item["comment"] != "A reply" for item in top_comments)


def test_top_comments_handles_fewer_than_ten():
    comments = [
        {"comment": "Low", "likes": 1, "replies": []},
        {"comment": "High", "likes": 5, "replies": []},
        {"comment": "Middle", "likes": 3, "replies": []},
    ]

    df = analyzer.create_dataframe({"comments": comments})
    top_comments = analyzer.analyse_comments(df)["top_comments"]

    assert [item["comment"] for item in top_comments] == [
        "High",
        "Middle",
        "Low",
    ]


def test_print_top_comments_shows_text_and_like_counts(capsys):
    analyzer.print_top_comments(
        [
            {"comment": "Second", "likes": 2},
            {"comment": "First", "likes": 10},
        ]
    )

    output = capsys.readouterr().out

    assert "Top 5 most-liked comments" in output
    assert " 1." in output
    assert "10 likes  First" in output
    assert " 2." in output
    assert "2 likes  Second" in output
    assert output.index("First") < output.index("Second")


def test_print_top_comments_limits_display_to_five(capsys):
    comments = [
        {"comment": f"Comment {index:02d}", "likes": index}
        for index in range(12)
    ]

    analyzer.print_top_comments(comments)

    output = capsys.readouterr().out

    assert "Top 5 most-liked comments" in output
    assert "Comment 11" in output
    assert "Comment 07" in output
    assert "Comment 06" not in output


def test_print_top_comments_handles_empty_list(capsys):
    analyzer.print_top_comments([])

    assert "No top-level comments available." in capsys.readouterr().out
