from neocortex.db.roles import oauth_sub_to_pg_role


def test_oauth_sub_to_pg_role_sanitizes_common_subject_formats() -> None:
    assert oauth_sub_to_pg_role("user@example.com") == "neocortex_agent_user_example_com"
    assert oauth_sub_to_pg_role("123E4567-E89B-12D3-A456-426614174000") == (
        "neocortex_agent_123e4567_e89b_12d3_a456_426614174000"
    )


def test_oauth_sub_to_pg_role_truncates_to_postgres_identifier_length() -> None:
    role = oauth_sub_to_pg_role("a" * 100)

    assert len(role) <= 63
    assert role == f"neocortex_agent_{'a' * 46}"


def test_oauth_sub_to_pg_role_replaces_unsafe_characters() -> None:
    assert oauth_sub_to_pg_role("User Name:/?#[]@!$&'()*+,;=") == "neocortex_agent_user_name__________________"
