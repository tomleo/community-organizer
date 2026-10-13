# Releasing

Releases are container images built for `linux/amd64` and `linux/arm64` and pushed to a registry.

1. Update `version` in `pyproject.toml` and add a section to `CHANGELOG.md`; commit.
2. Start the dev database and Valkey (`docker compose -f docker-compose.dev.yaml up -d postgres valkey`); the
   script runs the test suite.
3. Log in to the registry (e.g. `docker login ghcr.io`) and make sure `docker buildx` can build for both
   platforms (`docker buildx create --use` once; on Linux also install QEMU binfmt, e.g.
   `docker run --privileged --rm tonistiigi/binfmt --install arm64`).
4. Run `IMAGE=ghcr.io/your-org/community-organizer scripts/release.sh 1.2.0`.

It refuses a dirty working tree or a version that doesn't match `pyproject.toml`, runs ruff and pytest, then pushes
`:1.2.0`, `:1.2`, `:1` and `:latest`, and creates the tag `v1.2.0` (push it with `git push origin v1.2.0`).

Sites pin `VERSION` in their `.env` (`1` follows every 1.x release; `1.2` only patch releases), so a breaking change
needs a new major version and an upgrade note in `CHANGELOG.md`.
