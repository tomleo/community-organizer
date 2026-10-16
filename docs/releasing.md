# Releasing

Versions, tags and `CHANGELOG.md` are managed by [Commitizen](https://commitizen-tools.github.io/commitizen/) from
[Conventional Commits](https://www.conventionalcommits.org/) messages. Images are built by GitHub Actions
(`.github/workflows/ci.yml`) for `linux/amd64` and `linux/arm64` and pushed to the GitHub Container Registry at
`ghcr.io/<owner>/<repo>`.

## Commit messages

Commit messages become the changelog, so they must look like `type(optional scope): description`. Pull requests
fail CI otherwise (`uv run cz check --rev-range main..HEAD` checks a branch locally).

| Commit | Changelog section | Version bump |
|---|---|---|
| `feat: …` | Added | minor |
| `fix: …` | Fixed | patch |
| `refactor: …`, `perf: …` | Changed | patch |
| `feat!: …` or a `BREAKING CHANGE: …` footer | Breaking changes | major (minor before 1.0.0) |
| `docs:`, `test:`, `chore:`, `ci:`, `build:`, `style:` | not listed | none |

Write a `BREAKING CHANGE:` footer as an upgrade note for site operators; its text goes into the changelog verbatim:

```
feat!: rename the VERSION setting

BREAKING CHANGE: rename VERSION to IMAGE_TAG in your .env before upgrading.
```

## Making a release

1. On an up-to-date, clean `main`, run `scripts/release.sh`. It works out the next version from the commits since
   the last tag (or pass `major`, `minor` or `patch` to choose), updates `pyproject.toml`, `uv.lock` and
   `CHANGELOG.md`, commits `chore: release X.Y.Z` and creates the tag `vX.Y.Z`. In a terminal it then offers to
   open the new changelog entry in `$EDITOR` for extra upgrade notes, and folds your edits into the release commit.
2. Push the commit and the tag: `git push origin main vX.Y.Z`.

Nothing is published until the tag is pushed; to start over, `git tag -d vX.Y.Z && git reset --hard HEAD~1`.

Changelog entries use `scripts/changelog.md.j2` in the [Keep a Changelog](https://keepachangelog.com/) format.
Entries already in `CHANGELOG.md` are never regenerated, so hand edits to past releases stick.

## What CI publishes

Every run first passes the commit message check (pull requests only), ruff and the test suite.

- Pull requests: an amd64 build that isn't pushed.
- Pushes to `main`: `:main` and `:sha-<commit>`, for trying out unreleased changes.
- Tags `vX.Y.Z`: `:X.Y.Z`, `:X.Y`, `:X` and `:latest`. CI also checks the tag matches `pyproject.toml`.

The first published package is private; to let sites pull it without logging in, open the package on GitHub
(Packages → Package settings) and change its visibility to public.

Sites pin `VERSION` in their `.env` (`1` follows every 1.x release; `1.2` only patch releases), so a breaking change
needs a new major version and an upgrade note in `CHANGELOG.md`.
