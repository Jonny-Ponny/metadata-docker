# Roadmap

Status: Phases 1-3 are complete on `main` - the suite is green and CI gates the
image build. What remains is optional hardening and new features.

## Tracking work

- `B-xx (P0/P1/P2)` - confirmed bugs. While open, the item is listed below;
  once fixed, it moves to [docs/BUGFIXES.md](docs/BUGFIXES.md) with the fix and
  regression test.
- `T-xx (P2/P3)` - non-bug tasks, small fixes, polish and technical debt
  listed below. `P2` is user-visible or recurring; `P3` is low-impact.
- IDs are permanent and never reused. Last used: `T-02`, `B-31`. Next:
  `T-03`, `B-32`.
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

## Planned

### Known issues and small fixes

- **B-31 (P1) Invalid `AUTH_PASSWORD_HASH` crash-loops the app.** A malformed
  Werkzeug hash raises `RuntimeError` at import, so the container restarts
  forever and the UI never starts. The operator has to inspect the logs just
  to discover the cause.
  *Done when:* the validation error is logged, the bad hash is ignored, and a
  temporary password is generated and logged for this run.
  *Touch:* `backend/config.py`, `docs/DEPLOYMENT.md`, `tests/test_config.py`.

### Optional security hardening

- Build hygiene: add `.dockerignore`, build the frontend with `npm ci`, pin the
  remaining direct Python requirements, optionally pin base images by digest
  and Actions by commit SHA with an update bot. Run `pip-audit`/`npm audit`
  periodically or as a non-blocking CI job.
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
- **Streaming and playback** - stream audio with Range requests using the
  download-token pattern, then add a play queue, next/prev, shuffle/repeat and
  Media Session support.
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

The frontend currently has no linter or test runner; `npm run build` is the only
check. Add, in this order:

- ESLint (with the Svelte plugin) and Prettier, plus `svelte-check` for template
  and JSDoc type errors, with a `lint`/`check` script in `frontend/package.json`.
- Vitest over the pure utilities first: `upload.utils.js`, `lyrics.utils.js`,
  `timestamp.utils.js`, `sort.utils.js`.
- Component tests for the editor, upload tray and context menu once the
  utilities are covered.
- Run the checks in CI (extend `tests.yml` or add a frontend workflow) so a
  failing check blocks the release build, like `pytest` does.
- A UI bug pass once the checks and tests exist, so fixes can be pinned by a
  regression test.

## Out of scope

- Multi-user authentication or per-user libraries.
- Container/runtime hardening beyond the items above.
