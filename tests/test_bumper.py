from tagger.bumper import compute_bump_result
from tagger.config import Config
from tagger.models import BumpLevel, Commit, TaggedVersion, Version
from tagger.patterns import CommitPattern, TagPattern

CONFIG = Config()
TAG_PATTERN = TagPattern.compile(CONFIG.tag_pattern)
COMMIT_PATTERN = CommitPattern.compile(CONFIG.commit_pattern, CONFIG.commit_field_patterns)


def _result(messages: list[str], previous: TaggedVersion | None = None):
    commits = [Commit(sha=f"sha{i}", message=m) for i, m in enumerate(messages)]
    return compute_bump_result(previous, commits, COMMIT_PATTERN, TAG_PATTERN, CONFIG)


def test_feat_triggers_minor() -> None:
    result = _result(["feat: add login"])
    assert result.level is BumpLevel.MINOR


def test_fix_triggers_patch() -> None:
    result = _result(["fix: correct typo"])
    assert result.level is BumpLevel.PATCH


def test_chore_triggers_nothing() -> None:
    result = _result(["chore: bump lockfile"])
    assert result.level is BumpLevel.NONE
    assert result.next_tag is None


def test_highest_bump_wins() -> None:
    result = _result(["fix: minor bug", "feat: new widget", "chore: cleanup"])
    assert result.level is BumpLevel.MINOR


def test_bang_suffix_forces_major() -> None:
    result = _result(["feat!: drop legacy API"])
    assert result.level is BumpLevel.MAJOR


def test_breaking_change_footer_forces_major() -> None:
    message = "fix: patch a thing\n\nBREAKING CHANGE: removes old flag"
    result = _result([message])
    assert result.level is BumpLevel.MAJOR


def test_bump_from_existing_tag() -> None:
    previous = TaggedVersion(tag="v1.2.3", version=Version(1, 2, 3))
    result = _result(["feat: add thing"], previous=previous)
    assert result.next_version == Version(1, 3, 0)
    assert result.next_tag == "v1.3.0"


def test_bump_with_no_previous_tag_starts_at_zero() -> None:
    result = _result(["fix: first ever fix"])
    assert result.next_version == Version(0, 0, 1)
    assert result.next_tag == "v0.0.1"


def test_no_commits_means_no_bump() -> None:
    result = _result([])
    assert result.level is BumpLevel.NONE
    assert result.next_tag is None
