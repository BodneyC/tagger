"""Command-line interface for repo-tagger.

Every setting in `.tagger.yaml` has a matching CLI flag, and a flag always
wins over the yaml file. Run `tagger --help`, `tagger current --help`, or
`tagger bump --help` for details.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable, TypeVar

import click

from tagger.bumper import compute_bump_result
from tagger.config import DEFAULT_CONFIG_FILENAME, Config, find_config_file
from tagger.git_ops import GitError, GitRepo
from tagger.models import BumpLevel
from tagger.patterns import CommitPattern, PatternError, TagPattern

F = TypeVar("F", bound=Callable[..., Any])


def config_options(f: F) -> F:
    """Options shared by every subcommand, mirroring `.tagger.yaml` fields."""
    f = click.option(
        "--tag-pattern",
        default=None,
        help='Tag template, e.g. "v{major}.{minor}.{patch}". Overrides .tagger.yaml.',
    )(f)
    f = click.option(
        "--commit-pattern",
        default=None,
        help="Commit subject regex with {type}/{scope}/{message} placeholders.",
    )(f)
    f = click.option(
        "--major-type",
        "major_types",
        multiple=True,
        help="Commit type that triggers a MAJOR bump (repeatable).",
    )(f)
    f = click.option(
        "--minor-type",
        "minor_types",
        multiple=True,
        help="Commit type that triggers a MINOR bump (repeatable).",
    )(f)
    f = click.option(
        "--patch-type",
        "patch_types",
        multiple=True,
        help="Commit type that triggers a PATCH bump (repeatable).",
    )(f)
    f = click.option(
        "--breaking-change-marker",
        default=None,
        help="Text that, if found anywhere in a commit body, forces a MAJOR bump "
        '(default: "BREAKING CHANGE"). Pass "" to disable.',
    )(f)
    return f


@click.group()
@click.option(
    "--repo-path",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=Path("."),
    show_default=True,
    help="Path to the git repository to scan.",
)
@click.option(
    "--config",
    "config_path",
    type=click.Path(path_type=Path),
    default=None,
    help=f"Path to the config yaml (default: <repo-path>/{DEFAULT_CONFIG_FILENAME}).",
)
@click.pass_context
def main(ctx: click.Context, repo_path: Path, config_path: Path | None) -> None:
    """Scan a repo's tags and commits, and bump the version accordingly."""
    ctx.ensure_object(dict)
    ctx.obj["repo_path"] = repo_path
    ctx.obj["config_path"] = config_path if config_path is not None else find_config_file(repo_path)


def _load_config(
    ctx: click.Context,
    tag_pattern: str | None,
    commit_pattern: str | None,
    major_types: tuple[str, ...],
    minor_types: tuple[str, ...],
    patch_types: tuple[str, ...],
    breaking_change_marker: str | None,
) -> Config:
    base = Config.load(ctx.obj["config_path"])
    overrides: dict[str, Any] = {
        "tag_pattern": tag_pattern,
        "commit_pattern": commit_pattern,
        "breaking_change_marker": breaking_change_marker,
        # multiple=True gives () when the flag wasn't used at all -- treat
        # that as "no override", not as "set the list to empty".
        "major_types": major_types or None,
        "minor_types": minor_types or None,
        "patch_types": patch_types or None,
    }
    return base.merged_with_overrides(**overrides)


@main.command()
@config_options
@click.option(
    "--push/--push-to-remote",
    default=False,
    show_default=True,
    help="--push attempts to push the newly created tag.",
)
@click.pass_context
def current(
    ctx: click.Context,
    tag_pattern: str | None,
    commit_pattern: str | None,
    major_types: tuple[str, ...],
    minor_types: tuple[str, ...],
    patch_types: tuple[str, ...],
    breaking_change_marker: str | None,
    push: bool,
) -> None:
    """Print the latest tag matching tag_pattern, and its parsed version."""
    config = _load_config(
        ctx,
        tag_pattern=tag_pattern,
        commit_pattern=commit_pattern,
        major_types=major_types,
        minor_types=minor_types,
        patch_types=patch_types,
        breaking_change_marker=breaking_change_marker,
    )
    repo = GitRepo(ctx.obj["repo_path"])
    try:
        repo.verify_repo()
        compiled_tag_pattern = TagPattern.compile(config.tag_pattern)
        latest = repo.latest_matching_tag(compiled_tag_pattern)
    except (GitError, PatternError) as exc:
        raise click.ClickException(str(exc)) from exc

    if latest is None:
        click.echo(f"No tags matching {config.tag_pattern!r} found.")
        return
    v = latest.version
    click.echo(f"{latest.tag}  (major={v.major}, minor={v.minor}, patch={v.patch})")

    if not push:
        return

    remote_name = repo.get_remote_of_head()
    if not remote_name:
        click.echo("Failed to infer name of remote")
        sys.exit(1)

    repo.push_tag(remote_name, latest.tag)
    click.echo(f"Pushed tag: {latest.tag} to {remote_name}")


@main.command()
@config_options
@click.option(
    "--push/--push-to-remote",
    default=False,
    show_default=True,
    help="--push attempts to push the newly created tag.",
)
@click.option(
    "--apply/--dry-run",
    default=False,
    show_default=True,
    help="--apply actually creates the git tag; --dry-run (default) only reports.",
)
@click.option(
    "--tag-message",
    default=None,
    help="If set, create an annotated tag with this message instead of a lightweight tag.",
)
@click.pass_context
def bump(
    ctx: click.Context,
    tag_pattern: str | None,
    commit_pattern: str | None,
    major_types: tuple[str, ...],
    minor_types: tuple[str, ...],
    patch_types: tuple[str, ...],
    breaking_change_marker: str | None,
    apply: bool,
    push: bool,
    tag_message: str | None,
) -> None:
    """Scan commits since the last matching tag and bump accordingly."""
    config = _load_config(
        ctx,
        tag_pattern=tag_pattern,
        commit_pattern=commit_pattern,
        major_types=major_types,
        minor_types=minor_types,
        patch_types=patch_types,
        breaking_change_marker=breaking_change_marker,
    )
    repo = GitRepo(ctx.obj["repo_path"])
    try:
        repo.verify_repo()
        compiled_tag_pattern = TagPattern.compile(config.tag_pattern)
        compiled_commit_pattern = CommitPattern.compile(
            config.commit_pattern, config.commit_field_patterns
        )
        previous = repo.latest_matching_tag(compiled_tag_pattern)
        commits = repo.commits_since(previous.tag if previous else None)
        result = compute_bump_result(
            previous, commits, compiled_commit_pattern, compiled_tag_pattern, config
        )
    except (GitError, PatternError) as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo(f"Previous tag: {result.previous_tag or '(none found)'}")
    click.echo(f"Commits scanned: {len(result.classifications)}")
    for c in result.classifications:
        type_display = c.matched_type or "-"
        click.echo(f"- {c.commit.sha[:8]}  {c.level.name:<5}  [{type_display}]  {c.commit.subject}")

    click.echo(f"Bump level: {result.level.name}")

    if result.level is BumpLevel.NONE or result.next_tag is None:
        click.echo("No bump-worthy commits found since the last tag; nothing to do.")
        return

    click.echo(f"Next tag: {result.next_tag}")

    if not apply:
        click.echo("(dry run: no tag created -- pass --apply to actually create it)")
        return

    repo.create_tag(result.next_tag, message=tag_message)
    click.echo(f"Created tag: {result.next_tag}")

    if not push:
        click.echo("(local only: no tag pushed -- pass --push to attempt)")
        return

    remote_name = repo.get_remote_of_head()
    if not remote_name:
        click.echo("Failed to infer name of remote")
        sys.exit(1)

    repo.push_tag(remote_name, result.next_tag)
    click.echo(f"Pushed tag: {result.next_tag} to {remote_name}")


if __name__ == "__main__":
    main(obj={})
