import pytest

from tagger.patterns import CommitPattern, PatternError, TagPattern


def test_tag_pattern_v_prefix() -> None:
    pat = TagPattern.compile("v{major}.{minor}.{patch}")
    match = pat.regex.match("v1.2.3")
    assert match is not None
    assert match.group("major") == "1"
    assert match.group("minor") == "2"
    assert match.group("patch") == "3"


def test_tag_pattern_rejects_unversioned_tag() -> None:
    pat = TagPattern.compile("v{major}.{minor}.{patch}")
    assert pat.regex.match("1.2.3") is None  # missing "v" prefix
    assert pat.regex.match("release-1.2.3") is None


def test_tag_pattern_suffix_style() -> None:
    pat = TagPattern.compile("{major}.{minor}.{patch}-release")
    match = pat.regex.match("2.0.10-release")
    assert match is not None
    assert (match.group("major"), match.group("minor"), match.group("patch")) == (
        "2",
        "0",
        "10",
    )
    assert pat.regex.match("2.0.10") is None  # missing suffix


def test_tag_pattern_format_roundtrip() -> None:
    pat = TagPattern.compile("v{major}.{minor}.{patch}")
    assert pat.format(1, 4, 2) == "v1.4.2"


def test_tag_pattern_requires_all_three_fields() -> None:
    with pytest.raises(PatternError):
        TagPattern.compile("v{major}.{minor}")


def test_tag_pattern_rejects_unknown_field() -> None:
    with pytest.raises(PatternError):
        TagPattern.compile("v{major}.{minor}.{patch}+{build}")


def test_commit_pattern_jira_style() -> None:
    pat = CommitPattern.compile(r"[^:]*: {type}(\({scope}\))?: {message}")
    match = pat.match("JIRA-123: feat(auth): add SSO login")
    assert match is not None
    assert match.group("type") == "feat"
    assert match.group("scope") == "auth"
    assert match.group("message") == "add SSO login"


def test_commit_pattern_optional_scope() -> None:
    pat = CommitPattern.compile(r"[^:]*: {type}(\({scope}\))?: {message}")
    match = pat.match("JIRA-456: fix: correct off-by-one")
    assert match is not None
    assert match.group("type") == "fix"
    assert match.group("scope") is None


def test_commit_pattern_requires_type_field() -> None:
    with pytest.raises(PatternError):
        CommitPattern.compile(r"{message}")


def test_commit_pattern_quantifier_not_mistaken_for_field() -> None:
    # `{2,4}` is a real regex quantifier, not a placeholder -- must survive.
    pat = CommitPattern.compile(r"{type}: \d{2,4} {message}")
    match = pat.match("feat: 123 things")
    assert match is not None
    assert match.group("type") == "feat"
