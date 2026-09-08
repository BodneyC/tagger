"""Load `.tagger.yaml`, merged with any CLI-supplied overrides.

Precedence, highest first: CLI flag > `.tagger.yaml` > built-in default.
Every config field below is reachable both from the yaml file and from a
matching `--flag` on the CLI (see cli.py).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, fields, replace
from pathlib import Path
from typing import Any

import yaml

DEFAULT_USER_CONFIG_FILENAME = Path(os.getenv("HOME") or "") / ".config" / "tagger" / "config.yaml"
DEFAULT_CONFIG_FILENAME = ".tagger.yaml"

DEFAULT_TAG_PATTERN = "v{major}.{minor}.{patch}"
DEFAULT_COMMIT_PATTERN = r"{type}(\({scope}\))?: {message}"

DEFAULT_MAJOR_TYPES: tuple[str, ...] = ("breaking",)
DEFAULT_MINOR_TYPES: tuple[str, ...] = ("feat",)
DEFAULT_PATCH_TYPES: tuple[str, ...] = ("fix", "perf")
DEFAULT_BREAKING_CHANGE_MARKER = "BREAKING CHANGE"


@dataclass(frozen=True, slots=True)
class Config:
    """Fully-resolved settings for one run of the tool."""

    tag_pattern: str = DEFAULT_TAG_PATTERN
    commit_pattern: str = DEFAULT_COMMIT_PATTERN
    commit_field_patterns: dict[str, str] = field(default_factory=dict)
    major_types: tuple[str, ...] = DEFAULT_MAJOR_TYPES
    minor_types: tuple[str, ...] = DEFAULT_MINOR_TYPES
    patch_types: tuple[str, ...] = DEFAULT_PATCH_TYPES
    breaking_change_marker: str = DEFAULT_BREAKING_CHANGE_MARKER

    @classmethod
    def load(cls, path: Path | None) -> Config:
        """Load config from a yaml file, falling back to defaults if absent."""
        if path is None or not path.exists():
            return cls()

        raw = yaml.safe_load(path.read_text()) or {}
        if not isinstance(raw, dict):
            raise ValueError(f"{path} must contain a YAML mapping at the top level")

        known_fields = {f.name for f in fields(cls)}
        unknown = set(raw) - known_fields
        if unknown:
            raise ValueError(
                f"{path} has unknown option(s): {sorted(unknown)}; "
                f"expected some of {sorted(known_fields)}"
            )

        kwargs: dict[str, Any] = dict(raw)
        for tuple_field in ("major_types", "minor_types", "patch_types"):
            if tuple_field in kwargs:
                kwargs[tuple_field] = tuple(kwargs[tuple_field])
        return cls(**kwargs)

    def merged_with_overrides(self, **overrides: Any) -> Config:
        """Return a copy with any non-None override values applied.

        Used to layer CLI flags on top of the yaml-loaded config: pass every
        CLI option through as a kwarg, using None for "flag not given".
        """
        actual = {k: v for k, v in overrides.items() if v is not None}
        for tuple_field in ("major_types", "minor_types", "patch_types"):
            if tuple_field in actual and isinstance(actual[tuple_field], (list, tuple)):
                actual[tuple_field] = tuple(actual[tuple_field])
        return replace(self, **actual)


def find_config_file(start_dir: Path, filename: str = DEFAULT_CONFIG_FILENAME) -> Path | None:
    """Look for `.tagger.yaml` in start_dir, matching repo-tagger's usual layout.

    Point --repo-path at the directory that has the config in it or use the user
    default ($HOME/.config/tagger/config.yaml).
    """
    return next(
        (f for f in [start_dir / filename, DEFAULT_USER_CONFIG_FILENAME] if f.exists()), None
    )
