"""Minimal git access via subprocess -- deliberately no GitPython dependency.

Everything the tool needs (listing tags, listing commits since a tag,
creating a tag) is a couple of plain `git` invocations, so shelling out
keeps the dependency list short and the behaviour easy to reason about.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from tagger.models import Commit, TaggedVersion, Version
from tagger.patterns import TagPattern

_RECORD_SEP = "\x1e"  # separates commits
_FIELD_SEP = "\x1f"  # separates sha from message within a commit


class GitError(RuntimeError):
    """Raised when a git invocation fails."""


@dataclass(frozen=True, slots=True)
class GitRepo:
    """A git repository rooted at `path`."""

    path: Path

    def _run(self, *args: str) -> str:
        try:
            result = subprocess.run(
                ["git", "-C", str(self.path), *args],
                check=True,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError as exc:
            raise GitError("git executable not found on PATH") from exc
        except subprocess.CalledProcessError as exc:
            raise GitError(f"git {' '.join(args)} failed: {exc.stderr.strip()}") from exc
        return result.stdout

    def verify_repo(self) -> None:
        self._run("rev-parse", "--is-inside-work-tree")

    def list_tags(self) -> list[str]:
        output = self._run("tag", "--list")
        return [line for line in output.splitlines() if line]

    def latest_matching_tag(self, tag_pattern: TagPattern) -> TaggedVersion | None:
        """Find the highest tag matching `tag_pattern`, ordered by parsed semver.

        Ordering by parsed version (rather than tag creation date) means a
        late-created backport tag like `v1.2.4` still loses to an existing
        `v2.0.0`, matching normal semver precedence expectations.
        """
        candidates: list[TaggedVersion] = []
        for tag in self.list_tags():
            match = tag_pattern.regex.match(tag)
            if match is None:
                continue
            version = Version(
                major=int(match.group("major")),
                minor=int(match.group("minor")),
                patch=int(match.group("patch")),
            )
            candidates.append(TaggedVersion(tag=tag, version=version))
        if not candidates:
            return None
        return max(candidates, key=lambda tv: tv.version.as_tuple())

    def commits_since(self, tag: str | None) -> list[Commit]:
        """List commits reachable from HEAD, after `tag` (or all, if None)."""
        rev_range = f"{tag}..HEAD" if tag is not None else "HEAD"
        output = self._run(
            "log",
            rev_range,
            f"--pretty=format:%H{_FIELD_SEP}%B{_RECORD_SEP}",
        )
        commits: list[Commit] = []
        for record in output.split(_RECORD_SEP):
            record = record.strip("\n")
            if not record:
                continue
            sha, _, message = record.partition(_FIELD_SEP)
            commits.append(Commit(sha=sha, message=message.strip("\n")))
        return commits

    def create_tag(self, tag_name: str, message: str | None = None) -> None:
        if message:
            self._run("tag", "-a", tag_name, "-m", message)
        else:
            self._run("tag", tag_name)

    def get_remote_of_head(self) -> str | None:
        symbolic_head = self._run("symbolic-ref", "HEAD").strip()
        remote_name = self._run(
            "for-each-ref", "--format=%(upstream:remotename)", symbolic_head
        ).strip()
        if remote_name == "":
            return None
        return remote_name

    def push_tag(self, remote_name: str, tag_name: str) -> str:
        self._run("push", remote_name, tag_name)
        return remote_name
