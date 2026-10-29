# Security policy

## Supported versions

Only the latest release (`vX.Y.Z` tag) and the current `latest` image get fixes.

## Reporting a vulnerability

Open a private report through GitHub:
<https://github.com/Jonny-Ponny/metadata-docker/security/advisories/new>.
Please do not open a public issue for an unfixed vulnerability. Include the
affected version or commit, reproduction steps and what you expected to happen.
This is a single-maintainer project, so responses are best-effort.

## Threat model

This is a single-admin app meant to run on localhost or a trusted LAN behind a
TLS-terminating reverse proxy. The operator owns the library, addons are
arbitrary trusted Python, and the container is not a boundary between mutually
hostile users. The goal is to prevent accidental exposure and low-effort
attacks, not to build a multi-tenant service.

## Exposure checklist

- **Bind to localhost.** The shipped compose files publish
  `127.0.0.1:8888`, so the app is unreachable from other machines by default.
- **Terminate TLS in a proxy.** Never serve plain HTTP to the internet; the
  login password and bearer tokens would travel in clear text.
- **Set credentials explicitly.** Use `AUTH_USERNAME` and `AUTH_PASSWORD`, or
  `AUTH_PASSWORD_HASH` for a hash. If either is unset or empty, a random
  temporary credential is generated at startup and written to the logs; it
  changes on every restart. There is no default credential.
- **Only mount addons you trust.** See [Addons](#addons).
- **Pin the image digest** if you need a stable deployment; see
  [Image trust and verification](#image-trust-and-verification).

If you deliberately bind to `0.0.0.0` for a trusted LAN, understand that
everyone on that network can reach the login page.

## Authentication and sessions

- Single-admin login with a JWT. Session tokens carry `scope: 'session'` and are
  accepted by the API; download tokens carry `scope: 'download'` and are
  accepted only by `/api/download?token=...`, so a leaked download URL cannot be
  replayed as a session.
- Credential comparison is constant-time. A hash set through
  `AUTH_PASSWORD_HASH` is validated at startup, so a typo fails loudly instead
  of rejecting every login.
- Login is rate-limited per client address: five failed attempts trigger a
  15-minute lockout with `Retry-After`. The limiter is in-memory, is shared by
  the single gunicorn worker's threads, and resets on restart. Behind a reverse
  proxy it sees the proxy address, so it degrades to a global limit; deploy
  behind a trusted proxy only.
- The JWT secret is random per process unless `JWT_SECRET` is set to at least
  32 characters. Without a configured secret a restart invalidates every token
  and logs everyone out; with one, sessions survive restarts until they expire
  or the secret changes.
- The SPA stores the token in `localStorage`, so it is exposed to XSS. A
  restrictive `Content-Security-Policy` and the related headers are sent as
  defense-in-depth (`X-Content-Type-Options`, `X-Frame-Options`,
  `Referrer-Policy`, `Permissions-Policy`), but that is not equivalent to an
  `HttpOnly` cookie. HSTS is left to the reverse proxy.

## File and path safety

- Every user-supplied path goes through `safe_path()`, which rejects NUL bytes
  and resolves the path with `realpath` inside `/music`. A sibling such as
  `/music-other` is never treated as inside the library.
- Paths derived from a validated path are re-checked with `is_within()`
  (`realpath` + `os.path.commonpath`, never `str.startswith`).
- The library root itself cannot be deleted, copied or used as a rename/mkdir
  target.
- `build_tree()` does not list symlinked directories and lists symlinked files
  only when they resolve inside the library. Bulk tag/cover operations, folder
  copies and ZIP downloads do not follow links out of the selected folder.
- Renames refuse to overwrite an existing file (409) and smart rename rejects
  empty/`.`/`..` names, separators and NUL, then re-checks containment.

## Outbound requests

Cover images fetched from a user-supplied URL go through an SSRF guard
(`safe_fetch.py`):

- only public `http`/`https` hosts, with every redirect hop revalidated;
- an `image/*` content type is required;
- a size cap is enforced while streaming (10 MB) and requests use explicit
  timeouts.

Browser cover previews are proxied through the same guard
(`/api/metadata/picture/preview`). The CSP allows images only from the app
itself, `data:` and `blob:`, so the browser does not contact addon- or
user-provided hosts directly. A hover link shows the original URL and opens it
only on an explicit click.

## Addons

Addons are arbitrary Python from the read-only mounted `addons` folder. They
run with the app user's access to `/music` and `/logs`, so only mount addons you
trust.

- `*requirements.txt` installs run as the unprivileged `PUID`/`PGID` user into
  `/app/.local`, never as root.
- Application code in `/app` is not recursively chowned.
- Running with `PUID=0` and `PGID=0` disables runtime dependency installation;
  preinstall addon dependencies in a custom image instead. A mixed pair (only
  one of the two is `0`) is rejected at startup.
- A broken addon is skipped with a logged error and does not stop the app.

See [docs/ADDONS.md](docs/ADDONS.md) for the addon interface.

## Container surface

- Runs as `PUID`/`PGID` (default `1000` in the image), so non-root unless you
  set `0`.
- When running non-root, the entrypoint recursively chowns `/logs` on every
  start and `/music` only when `CHOWN_MUSIC=true`; otherwise the host library
  permissions must already match `PUID`/`PGID`.
- Needs read/write on the music library and `/logs`; treat it like code running
  with that file access.
- The healthcheck polls the unauthenticated `/api/ping` endpoint from inside the
  container.
- Addons folder is mounted read-only; logs and the library are the only
  writable host paths in the shipped compose file.

## Uploads and data safety

- `MAX_UPLOAD_MB` (default 4096) bounds one request, i.e. one file, with a JSON
  `413`; cover-art routes have a separate 20 MiB cap. Text files are capped at
  1 MiB for reads and writes.
- Uploads write a hidden `.upload-*.part` file and claim the destination with an
  atomic `os.link()`, so concurrent uploads cannot overwrite each other and an
  interrupted save leaves no truncated track in the tree.
- Text-file writes use a temp file and `os.replace()`, so a failed save does not
  truncate the previous lyrics.
- Free space in `/music` and the spool temp directory is checked before an
  upload starts; files above the cap are rejected before any bytes are sent.
- Unhandled exceptions return a generic JSON error while the real exception is
  logged; permission, missing-file, network, disk-space and read-only failures
  keep a clear category and status without exposing exception text.

## Image trust and verification

Images are built by GitHub Actions in
[`.github/workflows/container-release.yml`](.github/workflows/container-release.yml)
and get a signed build-provenance attestation.

You need the [GitHub CLI](https://cli.github.com/) and the digest of the image
you are running:

```bash
docker login ghcr.io   # gh and buildx read the image digest from the registry

# Resolve the tag you run to its digest; the output shows
# Digest: sha256:...
docker buildx imagetools inspect ghcr.io/jonny-ponny/metadata-docker:latest

gh attestation verify \
  oci://ghcr.io/jonny-ponny/metadata-docker@sha256:<digest> \
  --repo Jonny-Ponny/metadata-docker \
  --signer-workflow Jonny-Ponny/metadata-docker/.github/workflows/container-release.yml
```

A tag reference (`oci://ghcr.io/jonny-ponny/metadata-docker:latest`) also works
and verifies the digest the tag currently resolves to, but pinning the digest
verifies exactly the image you run, even if the tag moves later.

For a release tag, add `--source-ref refs/tags/v1.0.4` and verify the digest of
the matching image tag (`1.0.4`). On older `gh` versions, drop
`--signer-workflow` and keep `--repo`.

What it proves: the image was built by this repo's workflow from a specific
commit. An image pushed by hand or with a stolen token has no valid attestation
and fails verification. The same commit is stored in the
`org.opencontainers.image.revision` label and shown in the app's Help footer, so
you can match a running container to the attestation.

What it doesn't prove:

- **The workflow is benign.** Anyone with write access to this repo can change
  what CI builds, and the result still verifies.
- **Dependencies are safe.** Base images, npm/PyPI packages and addon
  `*requirements.txt` files come from outside this repo.
- **The image is byte-for-byte reproducible.** Pinning base images and Actions
  removes one source of drift, but other inputs still vary: `apk add` resolves
  from live Alpine repositories, transitive Python packages are resolved by
  pip, and BuildKit/attestation metadata can differ. Building the same commit
  may still produce a different digest.

If you don't trust the maintainer, build from a reviewed tag:

```bash
git clone --branch v1.0.4 https://github.com/Jonny-Ponny/metadata-docker.git
cd metadata-docker
docker build -t metadata-docker .
```

## Build and dependency hygiene

Proportionate hardening for the project size, and what to watch when changing
the build:

- Direct Python requirements are exact-pinned in `backend/requirements.txt`,
  and Dependabot (`.github/dependabot.yml`) updates them weekly. Transitive
  packages are still resolved by pip rather than locked.
- The `Dockerfile` builds the frontend in a separate stage with `npm ci`, so it
  consumes the committed `package-lock.json` exactly, and copies only
  `frontend/dist/` into the image.
- A `.dockerignore` (`.git`, `node_modules`, `dist`, `backend/static`, `.env*`,
  `__pycache__`, `logs`) keeps accidental local files and development-only
  files out of the build context.
- Base images are pinned by manifest-list digest and workflow Actions by
  commit SHA; Dependabot (`.github/dependabot.yml`) refreshes them weekly so
  the pins do not silently miss upstream security fixes.
- Run `pip-audit` / `npm audit` periodically or as a non-blocking CI job rather
  than making every release depend on it.

## Accepted risks / non-goals

- TLS and HSTS are handled by the reverse proxy; Flask does not manage
  certificates.
- Addons remain arbitrary Python by design; only trusted addons should be
  mounted.
- Single-admin authentication stays single-admin; there are no per-user
  permissions, audit identities or sessions.
- The JWT stays in `localStorage` with a strict CSP instead of an `HttpOnly`
  cookie plus CSRF protection. This is an accepted trade-off for a single-admin
  app.
- No token revocation/`jti`; tokens are short-lived, and a restart invalidates
  them unless a stable `JWT_SECRET` is configured.
- No full TOCTOU hardening (`O_NOFOLLOW`/`dir_fd`) and no blanket ban on
  symlinks. `realpath` containment plus skipping links in tree, bulk and ZIP
  operations is considered sufficient. The remaining race requires concurrent
  write access to the library and a deliberate attack; closing it would touch
  every file operation for little practical gain here. The upload name race is
  in scope because it can happen without an attacker.
- Builds are not hermetic or reproducible even with pinned base images:
  Alpine package repositories, transitive Python packages and BuildKit metadata
  remain variable inputs. Dependency pinning and periodic audits are
  proportionate to the project size.
