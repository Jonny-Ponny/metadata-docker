# Security Policy

## Supported versions

Only the latest release (`vX.Y.Z` tag) and the current `latest` image get fixes.

## Image trust model

Images are built by GitHub Actions in [`.github/workflows/container-release.yml`](.github/workflows/container-release.yml) and get a signed build-provenance attestation. See the [README](README.md#verifying-the-image) for the verification command.

What it proves: the image was built by this repo's workflow from a specific commit. An image pushed by hand or with a stolen token has no valid attestation and fails verification.

What it doesn't prove:

- **The workflow is benign.** Anyone with write access to this repo can change what CI builds, and the result still verifies.
- **Dependencies are safe.** Base images, npm/PyPI packages and addon `*requirements.txt` files come from outside this repo.
- **The image is reproducible.** Building the same commit locally may produce a different digest.

If you don't trust the maintainer, build from a reviewed tag:

```bash
git clone --branch v1.0.4 https://github.com/Jonny-Ponny/metadata-docker.git
cd metadata-docker
docker build -t metadata-docker .
```

## Container surface

- Runs as `PUID`/`PGID` (default `1000`), so non-root unless you set `0`.
- Needs read/write on the music library and `/logs`; treat it like code running with that file access.
- Addons are arbitrary Python from the mounted `addons` folder. Only mount addons you trust.
- Change the default `AUTH_USERNAME`/`AUTH_PASSWORD` before exposing the port.
- JWTs use a per-process secret, so a restart logs everyone out.
