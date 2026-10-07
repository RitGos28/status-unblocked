"""Team codes: readable, forgiving to type, and never ambiguous out loud."""

from standup.auth.team_code import (
    CODE_ALPHABET,
    SUFFIX_LENGTH,
    format_team_code,
    generate_team_code,
    normalise_name,
    normalise_team_code,
)


def test_a_code_starts_with_the_team_and_ends_with_random_unambiguous_characters():
    code = generate_team_code("core")
    assert code.startswith("CORE")
    assert len(code) == 4 + SUFFIX_LENGTH
    assert set(code[4:]) <= set(CODE_ALPHABET)
    assert not set("01IO") & set(code[4:])


def test_codes_differ_between_calls():
    assert len({generate_team_code("core") for _ in range(20)}) > 1


def test_a_slug_with_nothing_usable_still_gets_a_prefix():
    assert generate_team_code("--").startswith("TEAM")
    assert generate_team_code("mobile-apps").startswith("MOBI")


def test_what_people_type_is_forgiven():
    for typed in ("CORE7K3MQ", "core-7k3mq", " core 7k3mq ", "CORE-7K3MQ\n"):
        assert normalise_team_code(typed) == "CORE7K3MQ"


def test_display_form_round_trips():
    assert format_team_code("CORE7K3MQ") == "CORE-7K3MQ"
    assert normalise_team_code(format_team_code("CORE7K3MQ")) == "CORE7K3MQ"
    assert format_team_code("ABC") == "ABC"


def test_names_compare_without_case_or_spacing():
    assert normalise_name("  ritwik   GOSSAIN ") == normalise_name("Ritwik Gossain")
    assert normalise_name("Ritwik Gossain") != normalise_name("Ritwik Gossain-Smith")
