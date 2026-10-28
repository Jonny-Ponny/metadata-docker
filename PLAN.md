# Roadmap

Status: Phases 1-3 are complete on `main` - the suite is green and CI gates the
image build. What remains is optional hardening and new features.

## Tracking work

- `B-xx (P0/P1/P2)` - confirmed bugs. While open, the item is listed below;
  once fixed, it moves to [docs/BUGFIXES.md](docs/BUGFIXES.md) with the fix and
  regression test.
- `T-xx (P2/P3)` - non-bug tasks, small fixes, polish and technical debt
  listed below. `P2` is user-visible or recurring; `P3` is low-impact.
- IDs are permanent and never reused. Last used: `T-12`, `B-39`. Next:
  `T-13`, `B-40`.
- Larger feature bullets are not numbered until work starts; split them into
  `T-xx` items then.

## Done

- **Phase 1 - bug fixes.** 30 confirmed bugs (data-loss guards, path
  containment, atomic uploads, error handling, text/tag edge cases) fixed and
  covered by regression tests. Details: [docs/BUGFIXES.md](docs/BUGFIXES.md).
- **Phase 2 - tests.** `tests/` grew from a security subset into a suite over
  every route and non-trivial helper: API contract, paths, auth/token scopes,
  uploads, rename/move/copy/delete, tag round-trips for every format and field,
  covers, LRC/SYLT, ZIP streaming, addons, config. CI runs `py_compile` and
  `pytest`, and the release build depends on that job.
- **Phase 3 - refactor.** `app.py` is a composition root with `create_app()`;
  routes live in `backend/routes/`, with `paths.py`, `errors.py`, `config.py`,
  `auth.py`, `library.py` and `renaming.py` as support modules. One dispatcher
  handles single-file tag writes, the folder-route pairs share a helper each,
  and one registry in `formats.py` owns the audio, image and text type lists.
  No wildcard imports remain. Details: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
- **Docs.** The README is an overview/usage guide; deployment, addons and
  architecture are separate documents and security is consolidated in
  [SECURITY.md](SECURITY.md).
- **Frontend tests (start).** Vitest + jsdom over the pure timestamp, lyrics,
  sort, upload, API-error and version-cache utilities. `npm test` and
  `npm run build` are a separate CI job that gates the image build.
- **Frontend component, store and utility tests (T-04).** Complete: every
  component including `App.svelte`, every store and the remaining utilities
  have Vitest coverage. The suite runs 41 files / 531 tests and includes the
  regression tests for B-33 to B-35.
- **Frontend coverage and CI parity (T-05).** Complete: `npm run test:coverage`
  uses `@vitest/coverage-v8` to print a summary and write HTML/LCOV reports.
  The pull-request and main-branch `frontend` job runs the report in a
  non-blocking step and uploads it as an artifact, matching the existing
  non-blocking backend coverage step.
- **Frontend coverage pass (T-10).** Complete: closed the large gaps left by
  T-04 in `App` (73% → 90% lines), `MetadataEditor` (38% → 81%), `TreeNode`
  (59% → 88%), `Player` (69% → 92%), `ToastContainer` (59% → 94%),
  `MetadataFetcher` (77% → 97%) and `upload.store` (→ 100%). Overall line
  coverage moved from 86% to 92%. The `frontend` CI job already runs the suite;
  branch protection must list it as a required check for a failure to block a
  merge.
- **Frontend static checks.** ESLint 10 flat config (`@eslint/js`,
  `eslint-plugin-svelte` recommended rules, `eslint-config-prettier`),
  Prettier 3 with `prettier-plugin-svelte`, and `svelte-check`. Scripts are
  `lint`, `format`, `format:check` and `check`; CI runs all of them before the
  tests and build. Details: [docs/TESTING.md](docs/TESTING.md).
- **Frontend type checking.** `checkJs` is enabled in `frontend/jsconfig.json`,
  so `svelte-check` type-checks the utilities, stores, every component
  (including `App.svelte`), the entry point and the Vitest helpers. Shared
  shapes are documented with JSDoc typedefs (tree nodes, metadata, upload
  batches, player API) instead of per-file opt-ins, and CI fails on a new type
  error.
- **Session persistence (T-11).** Optional `JWT_SECRET` (at least 32
  characters) keeps session tokens valid across restarts; unset or shorter
  values fall back to a random per-process secret with a warning. Compose,
  `.env_example`, README and DEPLOYMENT document it, and `tests/test_config.py`
  covers the configured, boundary, random and rejected cases.
- **Documentation refresh (T-12).** Updated the build-hygiene section in
  [SECURITY.md](SECURITY.md) for the existing `.dockerignore` and `npm ci`
  setup, and refreshed the frontend coverage snapshot in
  [docs/TESTING.md](docs/TESTING.md) with the `LRCEditor` gap.

## Planned

### Known issues and small fixes

No open items.

### Optional security hardening

- Build hygiene: pin the remaining direct Python requirements, optionally pin
  base images by digest and Actions by commit SHA with an update bot. Run
  `pip-audit`/`npm audit` periodically or as a non-blocking CI job. The
  `.dockerignore` and the frontend's `npm ci` install are done, and the
  frontend builder is pinned to Node 22 because Node 24+ has no armv7 image.
- Compose hardening: `no-new-privileges`, `pids_limit`, memory/CPU limits and
  `tmpfs: /tmp`; an opt-in `CHOWN_MUSIC` flag instead of the recursive chown;
  document the `PUID=0` trade-off clearly. `read_only` and `cap_drop: ALL` only
  after the entrypoint stops writing `/etc`.
- Persist the JWT secret through an optional `JWT_SECRET` variable so restarts
  do not log everyone out (availability, not security).

### Features

- **Operation journal** - record old/new tag values and rename/move/delete
  operations, as the basis for auditability and undo.
- **Undo and trash** - soft-delete into a hidden folder excluded from the tree,
  an "Undo" toast action and a history panel.
- **Batch jobs** - move folder-wide tag/cover updates out of the request into
  `POST /api/jobs` + `GET /api/jobs/<id>` with progress, cancel and a list of
  failed files. Make uploads resumable so they survive a closed tab.
- **Library-wide tag search** - replace the client-side filename filter with an
  mtime-invalidated tag index, and reuse it for reports (missing fields, missing
  covers, duplicate artist/title).
- **Multi-select** in the tree with batch actions, plus copy/paste tags from one
  file onto a selection.
- **UX and performance** - lazy per-directory tree loading, a smart-rename
  dry-run preview with a conflict strategy, addon reload from Settings,
  responsive/mobile layout, more keyboard shortcuts and modal focus handling,
  metadata CSV/JSON export-import and library normalisation tools.
- **More audio formats** - extend `formats.py` and `tag_backends.py`.

### Housekeeping

- Backend test coverage runs as a non-blocking CI step (no threshold); see
  [docs/TESTING.md](docs/TESTING.md) for the local command and remaining gaps.
- `pytest-xdist` in CI (optional; the suite is ~5 s serial, so the gain is
  small).

### Frontend checks and tests

The frontend has a Vitest suite over the utilities, stores and components, plus
ESLint, Prettier and `svelte-check` with full `checkJs` type checking in CI.
Remaining:

- A UI bug pass now that the tests exist, so fixes can be pinned by a
  regression test.

## Out of scope

- Multi-user authentication or per-user libraries.
- Container/runtime hardening beyond the items above.
- Playback and streaming features beyond the existing single-file player:
  Range-based streaming, a play queue, next/prev navigation, shuffle/repeat and
  Media Session. Main goal is library management, not playing or
  streaming a library.
