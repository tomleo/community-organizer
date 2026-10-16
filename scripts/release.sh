#!/usr/bin/env bash
# Bump the version and CHANGELOG.md from commit messages, then commit and tag. Pushing the tag makes CI
# build and publish the image. See docs/releasing.md.
set -euo pipefail

increment="${1:-}"
case "$increment" in
  "" | major | minor | patch) ;;
  *)
    echo "Usage: scripts/release.sh [major|minor|patch]  (default: worked out from commit messages)" >&2
    exit 1
    ;;
esac

cd "$(dirname "$0")/.."
if [[ "$(git branch --show-current)" != "main" ]]; then
  echo "Release from main." >&2
  exit 1
fi
if [[ -n "$(git status --porcelain)" ]]; then
  echo "Commit or stash your changes first." >&2
  exit 1
fi

args=(--yes)
if [[ -n "$increment" ]]; then
  args+=(--increment "${increment^^}")
fi
# Before 1.0.0, breaking changes bump the minor version.
if [[ "$(uv run cz version --project)" == 0.* ]]; then
  args+=(--major-version-zero)
fi
uv run cz bump "${args[@]}"
version="$(uv run cz version --project)"

if [[ -t 0 ]]; then
  read -rp "Edit the CHANGELOG.md entry (e.g. to add upgrade notes)? [y/N] " answer
  if [[ "$answer" == [yY]* ]]; then
    "${VISUAL:-${EDITOR:-vi}}" CHANGELOG.md
    if ! git diff --quiet CHANGELOG.md; then
      git commit --quiet --amend --no-edit CHANGELOG.md
      git tag --force --annotate "v$version" --message "v$version" >/dev/null
    fi
  fi
fi
echo "Tagged v$version. Publish it with: git push origin main v$version"
