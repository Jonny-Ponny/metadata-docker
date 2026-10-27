# Architecture

Technical notes for people working on the code. Deployment and configuration
live in [DEPLOYMENT.md](DEPLOYMENT.md); the security model is in
[SECURITY.md](../SECURITY.md).

## Shape of the app

One Flask process serves both the JSON API under `/api/*` and the compiled
Svelte bundle. Gunicorn runs it with one worker and eight threads. There is no
database and no task queue: the state is the files under `/music` plus the
logs under `/logs`, and every write goes straight to disk.

```text
browser (Svelte 5 SPA)
   │  fetch('/api/...')  Authorization: Bearer <session token>
   ▼
Flask (gunicorn, 1 worker / 8 threads)
   ├── routes/        HTTP layer: validation, status codes, JSON shapes
   ├── auth.py        login, token scopes, per-IP login limiter
   ├── paths.py       safe_path(), is_within() and rename-name guards
   ├── library.py     build_tree() and natural sorting
   ├── formats.py     audio format registry + image/text type registry
   ├── tag_backends.py  FIELD_SCHEMA and the mutagen backends
   ├── metadata_*.py  read/write entry points
   ├── renaming.py    smart-rename name generation
   ├── zip_stream.py  bounded producer/consumer ZIP streaming
   └── safe_fetch.py  SSRF-guarded cover downloads
```

## Repository layout

```text
backend/
  app.py                 create_app(), compatibility wrappers, SPA fallback
  config.py              every environment variable, read once at import
  errors.py              AccessDenied, public error mapping, JSON handlers
  paths.py               containment, safe_path, unique/generated names
  auth.py                login, token_required, rate limiter
  library.py             build_tree, natural_key, file classification
  renaming.py            scheme parsing and name generation
  formats.py             audio format registry, image/text registries
  tag_backends.py        FIELD_SCHEMA + ID3/FLAC/Vorbis/MP4 backends
  metadata_extractor.py  read tags into the API shape
  metadata_writer.py     write tags/covers (one dispatcher)
  plugin_manager.py      addon discovery
  addon_base.py          MetadataFetcher base class
  safe_fetch.py          image fetch with SSRF/size/timeout guards
  zip_stream.py          folder download stream
  logger_config.py       logging setup
  routes/
    __init__.py          register_blueprints(app)
    files.py             listing, upload, storage, mkdir, rename, move, copy,
                         delete, smart rename
    tags.py              metadata, cover art, audio/image serving
    text.py              .txt/.lrc read and atomic save
    logs.py              log read/clear
    addons.py            addon listing and proxy calls
    downloads.py         file/folder downloads and download tokens
    system.py            /api/ping, /api/version
frontend/
  src/App.svelte         the whole SPA (no router)
  src/components/        editor, player, browser, modals
  src/stores/            auth, tree, player, upload, settings, toasts
  src/utils/             pure helpers and the utils barrel
  src/utils/__tests__/       Vitest utility tests (jsdom)
  src/stores/__tests__/      Vitest store tests
  src/components/__tests__/  Vitest component tests
  src/__tests__/             App shell test
  src/test/setup.js      Vitest setup
  eslint.config.js       ESLint flat config
  .prettierrc.json       Prettier + Svelte plugin
tests/                   pytest suite (see below)
docs/                    this file, deployment, addons, fixed bugs
```

## Backend composition

`app.py` is the composition root. `create_app(settings=None)` builds the Flask
app, registers the error handlers and the blueprints, mounts `/api/login`,
`/api/validate` and the SPA fallback, and returns it. The module-level
`app = create_app()` keeps `gunicorn app:app` working. `settings` is merged into
`app.config`; the runtime values themselves come from `config.py`.

`backend/routes/__init__.py` registers one blueprint per route group. Route
modules import from the support modules; no route module imports another route
module.

`app.py` re-exports a handful of names (`safe_path`, `build_tree`,
`plugin_manager`, `_version_cache`, ...) for the test suite and for backwards
compatibility. New code should import the owning module directly.

## API conventions

- Every route except `/api/login`, `/api/ping`, `/api/version` and the SPA
  fallback requires `Authorization: Bearer <session token>` via
  `@token_required`.
- Status codes are stable: `400` bad input, `401` missing/invalid token, `403`
  outside the library, `404` missing file or folder, `409` rename collision,
  `413` too large, `429` login lockout, `500` unexpected failure.
- Every user-supplied path is resolved through `safe_path()`, which rejects
  NUL bytes and anything that resolves outside `/music`. Paths derived from an
  already-validated path are re-checked with `is_within()`, which compares
  `realpath`s with `os.path.commonpath` (never `str.startswith`).
- JSON bodies are parsed with `_json_object()` from `errors.py`. Missing or
  wrong `Content-Type`, malformed JSON, and non-object JSON all return a JSON
  error, never an HTML page.
- Unhandled exceptions return a generic JSON message while the real exception is
  logged. Permission, missing-file, disk-space, read-only and upstream-network
  failures keep a clear category and status without leaking exception text.
- Downloads use short-lived download tokens (scope `download`) in the query
  string so a browser can save the file without putting the session token in a
  URL. Session routes reject download tokens and vice versa.

## Formats and metadata

`formats.py` is the single registry: extension -> (`AudioFormat`, MIME type, tag
family). Supported audio: `.mp3`, `.wav`, `.aiff`, `.aif`, `.flac`, `.ogg`,
`.oga`, `.opus`, `.m4a`, `.m4b`. Adding a format means adding a registry entry
and, if the tag family is new, a backend.

`tag_backends.py` holds `FIELD_SCHEMA` and the four backends (ID3, FLAC, Vorbis
comments, MP4). Adding a field means adding it there and to the UI list in
`frontend/src/utils/fieldMetadata.utils.js`. All mutagen-specific logic lives
in the backends; `metadata_extractor.py` and `metadata_writer.py` are thin
entry points, and every single-file write goes through `metadata_writer._modify`
so logging and unsupported-format handling cannot drift.

Files with a supported extension but unreadable tags are reported as a `500`
with a clear message; files without a supported extension are returned by the
API as read-only `read_only_metadata()` payloads.

## Library tree

`library.build_tree(current_path, relative_path, music_root)` walks the library
on every `/api/files` request and classifies each entry as `audio`, `image`,
`text` or `other` (everything else is listed read-only). Sorting is natural
(`a2` before `a10`), including filenames with Unicode digits that `int()`
rejects. Entries that disappear during the walk are skipped instead of failing
the request; a permission error yields an empty list for that directory.

Symlink policy: symlinked directories are never listed, symlinked files are
listed only when they resolve inside the library, and bulk tag/cover
operations, folder copies and ZIP downloads do not follow links out of the
selected folder.

Uploads write a hidden `.upload-*.part` file and claim the destination with an
atomic `os.link()` (falling back to `os.replace()`), so an interrupted upload
leaves no truncated track in the tree and two concurrent uploads cannot
overwrite each other. `build_tree()` hides `.upload-*.part` files.

## Frontend

Plain JavaScript Svelte 5 with runes (`$state`, `$derived`, `$props`). There is
no router and no component library: `App.svelte` owns the layout and switches
views, global state lives in `src/stores/`, shared helpers in
`src/utils/` (import from the barrel), and styling is CSS variables plus scoped
component styles in `src/app.css`.

API calls are direct `fetch('/api/...')` with `getAuthHeaders()` from
`stores/auth.store.js`; failures go through `readApiError()` so toasts show the
backend's message.

The upload queue (`stores/upload.store.js`, `UploadTray.svelte`) reads dropped
folders first (cancellable), checks free space, then sends four files at a time
with XHR byte progress, a conflict policy (`skip-identical` by default,
`keep-both` via Settings) and cancel/retry.

## Tests

The suite runs against a temporary music library and log directory created by
`tests/conftest.py`; each test gets a unique subtree. The Flask app is imported
once per session, with the plugin manager pointed at the throwaway working
directory. Tests that patch a module-level global must target the module that
reads it (`routes/files.py`, `routes/tags.py`, `routes/logs.py`,
`routes/system.py`), not `app` - see the fixtures in `conftest.py`.

`tests/` covers path containment, auth/token scopes, the JSON contract, upload
races, rename/move/copy/delete, tag round-trips for every format and field,
cover art, LRC/SYLT parsing, ZIP streaming, addons, logs and configuration.
[BUGFIXES.md](BUGFIXES.md) maps every fixed bug to its regression test;
[TESTING.md](TESTING.md) documents the coverage workflow and the test backlog.

## Local development

```bash
# Frontend dev server (port 5173, proxies /api to localhost:5000)
cd frontend && npm run dev

# Frontend unit tests (Vitest + jsdom)
cd frontend && npm test

# Frontend coverage report (non-blocking in CI)
cd frontend && npm run test:coverage

# Frontend static checks (ESLint, Prettier, svelte-check)
cd frontend && npm run lint
cd frontend && npm run format:check
cd frontend && npm run check

# Production frontend build
cd frontend && npm run build

# Backend locally; run from backend/ so addons/ is found
cd backend && python app.py

# Offline Python syntax check
python3 -m py_compile backend/*.py backend/routes/*.py

# Backend tests (installs pytest from requirements-dev.txt)
pip install -r requirements-dev.txt
python -m pytest -q

# Build and run the container
cp .env_example .env
docker compose -f docker-compose.dev.yml up --build
```

Flask serves no UI outside the container: `backend/static/` is produced by the
frontend build stage in the `Dockerfile` and is not committed.

Use `MUSIC_FOLDER` and `LOG_DIR` to point a local backend at a test library and
log directory. The JWT secret is random per process, so a backend restart logs
the browser out.

## CI and release pipeline

`.github/workflows/tests.yml` has two jobs. The `pytest` job runs `py_compile`
and `pytest -q` on pull requests and on `main`, `master`, `fix/**`, `test/**`,
`refactor/**` and `ci/**`; a second, non-blocking step prints line coverage with
`pytest-cov`, with no threshold. The `frontend` job installs with `npm ci` and
runs `npm run lint`, `npm run format:check`, `npm run check`, `npm test`
(Vitest), a non-blocking `npm run test:coverage` step that uploads the HTML/LCOV
report as an artifact, and `npm run build` under `frontend/`. Both jobs are
required by the release workflow.

`.github/workflows/container-release.yml` runs on pushes to `main`/`master` and
on `v*` tags. It calls `tests.yml` as a `test` job and `build-and-push` declares
`needs: test`, so a failed, cancelled or timed-out suite publishes no image. A
passing build produces `linux/amd64`, `linux/arm64` and `linux/arm/v7` images,
embeds SBOM and provenance, and attests the multi-arch digest with Sigstore via
the workflow's OIDC identity. `latest` follows the default branch; `vX.Y.Z`
tags produce `X.Y.Z`, `X.Y` and `X` image tags.

The frontend is built once per build in a stage pinned to `$BUILDPLATFORM`, so
the bundle is not recompiled under QEMU for each target. The bundle is
platform-independent and is copied into every architecture's final stage. That
stage stays on `node:22-bookworm-slim`: Node 24 and newer publish no
`linux/arm/v7` image, while the final `python:3.12-alpine` stage does. The
frontend installs with `npm ci` from `frontend/package-lock.json`, and
`frontend/.nvmrc` plus the `engines` field in `frontend/package.json` document
the Node range the tooling needs.

The commit SHA is baked into the image (`APP_GIT_SHA`) and exposed by
`/api/version`, so a running container can be matched to its attestation. See
[SECURITY.md](../SECURITY.md#image-trust-and-verification) for the verification
commands.

Releases are cut by bumping `APP_VERSION` in `backend/config.py`, committing,
tagging `vX.Y.Z` and pushing the tag.
