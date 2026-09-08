<!-- markdownlint-disable MD013 -->

# Tagger

There's a great many [Conventional Commit](https://www.conventionalcommits.org/en/v1.0.0/) + [SemVer](https://semver.org/) bumpers out there but I'm currently on a project with some preordained rules about commit messages and tag formats so I needed one I could customize quite a bit.

For the config you can set, those customizations, see [.tagger.yaml](./.tagger.yaml).

## Install

The project uses [Poetry](https://python-poetry.org/) as dependency management/build:

```sh
poetry install
```

To make `tagger` available from anywhere on your system:

```sh
ln -s "$(poetry env info -p)/bin/tagger" ~/.local/bin/
```

(assuming `~/.local/bin` is on your path)

## Configure

The configuration as seen in [`.tagger.yaml`](./.tagger.yaml) can be per repo (top level).

Or these options can be user-wide in `~/.config/tagger/config.yaml`.

Each key can also be given as a CLI parameter, e.g. `--tag-pattern '{major}.{minor}.{patch}`.

There are some sane defaults to use without either of these two.

Precedence is CLI -> per repo -> user-wide -> defaults.

## Use

`cd` to a repo and run:

```sh
tagger current
```

to see the latest tag matching the configured (or default) pattern.

```sh
tagger bump
```

to dry-run a bump based on the configured (or default) commit message pattern.

```sh
tagger bump --apply
```

to make the tag locally, adding `--push` to push to the remote.
