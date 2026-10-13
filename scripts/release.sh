#!/usr/bin/env bash
# Build and push a multi-arch release image. See docs/releasing.md.
set -euo pipefail

version="${1:-}"
if [[ -z "$version" ]]; then
  echo "Usage: IMAGE=registry/name scripts/release.sh <version>" >&2
  exit 1
fi
if [[ ! "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "The version must look like 1.2.3, got $version." >&2
  exit 1
fi
if [[ -z "${IMAGE:-}" ]]; then
  echo "Set IMAGE, e.g. IMAGE=ghcr.io/your-org/community-organizer" >&2
  exit 1
fi

cd "$(dirname "$0")/.."
if [[ -n "$(git status --porcelain)" ]]; then
  echo "Commit or stash your changes first." >&2
  exit 1
fi
project_version=$(uv run python -c 'import tomllib; print(tomllib.load(open("pyproject.toml", "rb"))["project"]["version"])')
if [[ "$project_version" != "$version" ]]; then
  echo "pyproject.toml says $project_version; update it (and CHANGELOG.md) first." >&2
  exit 1
fi

uv run ruff check .
uv run ruff format --check .
uv run pytest -q

major="${version%%.*}"
minor="${version#*.}"
minor="${minor%%.*}"
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  --build-arg APP_VERSION="$version" \
  --tag "$IMAGE:$version" \
  --tag "$IMAGE:$major.$minor" \
  --tag "$IMAGE:$major" \
  --tag "$IMAGE:latest" \
  --push .

git tag -a "v$version" -m "Release $version"
echo "Pushed $IMAGE:$version. Push the tag with: git push origin v$version"
