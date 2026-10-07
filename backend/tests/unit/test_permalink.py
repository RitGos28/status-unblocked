"""Native permalinks only when constructible; otherwise a stated reason."""

from standup.ingestion.permalink import teams_permalink


def test_one_to_one_chat_has_no_permalink_and_says_why():
    url, reason = teams_permalink("a:1on1-aarav", "1002")
    assert url is None
    assert "a:-form" in reason


def test_channel_thread_builds_a_deep_link_without_the_messageid_suffix():
    url, reason = teams_permalink("19:abc@thread.tacv2;messageid=1004", "1004")
    assert reason == ""
    assert url == "https://teams.microsoft.com/l/message/19%3Aabc%40thread.tacv2/1004"


def test_missing_message_id_is_explained():
    assert teams_permalink("19:abc@thread.tacv2", "") == (
        None,
        "teams: activity carried no message id",
    )


def test_unknown_id_form_is_explained():
    url, reason = teams_permalink("weird-id", "1")
    assert url is None
    assert "unrecognised" in reason


def test_missing_permalinks_are_described_in_plain_words():
    from standup.ingestion.permalink import describe_missing_permalink

    _, teams_reason = teams_permalink("a:1on1-aarav", "1002")
    assert "1:1 Teams chat" in describe_missing_permalink(teams_reason)
    assert "web form" in describe_missing_permalink("webform: no platform message to link to")
    assert describe_missing_permalink("teams: activity carried no message id") == (
        "No link to the original message: activity carried no message id."
    )
    assert describe_missing_permalink(None) == "No link to the original message."
    assert "spreadsheet" in describe_missing_permalink("csv import: no platform message to link to")
