# Testing guide

Two suites run in CI: `pytest` for the backend and Vitest for the frontend. Both
must pass before the image build starts.

## Backend

Run the suite from the repository root:

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

`pytest.ini` adds `backend/` to `pythonpath`, so the tests import `app` and the
route modules directly. `tests/conftest.py` creates one temporary music library
and log directory per session; every test gets a unique subtree. The Flask app
is imported once with the plugin manager pointed at a throwaway working
directory.

## Backend coverage

Line coverage is reported in CI as a non-blocking step: it prints the
`term-missing` table but has no threshold and cannot fail the required `pytest`
job. To see the same report locally:

```bash
pip install -r requirements-dev.txt
python -m pytest -q --cov=backend --cov-report=term-missing
```

| Measurement                       | Tests | Line coverage | Statements | Missed |
| --------------------------------- | ----: | ------------: | ---------: | -----: |
| Baseline before the coverage work |   616 |           83% |       2583 |    437 |
| Current (2026-10-25)              |   848 |           92% |       2591 |    206 |

`config.py` is under-reported because its tests import the app in a subprocess.

Lowest-covered areas:

| Area               |   Cover | Main gap                                          |
| ------------------ | ------: | ------------------------------------------------- |
| `config.py`        |     55% | parsed in a subprocess, so coverage cannot see it |
| `routes/tags.py`   |     83% | per-endpoint validation and generic error exits   |
| `logger_config.py` |     85% | fallback/error branches                           |
| `paths.py`         |     90% | symlink and `commonpath` edge cases               |
| `routes/text.py`   |     91% | stat and temp-file cleanup races                  |
| `routes/logs.py`   |     91% | empty and undecodable log lines                   |
| `renaming.py`      |     91% | remaining filename edge cases                     |
| everything else    | 92-100% |                                                   |

## Backend coverage backlog

All planned P0/P1/P2 test items are complete. The remaining misses are:

- repeated per-endpoint input validation and generic error exits in
  `routes/tags.py`;
- stat and temp-file cleanup races in `routes/text.py`;
- defensive cleanup in the upload and ZIP streaming paths;
- `config.py` execution hidden inside subprocess tests.

Add tests for these only when a real failure mode is found or a bug is fixed.
There are no open test tasks.

## Backend covered areas

- Path containment, library-root guards and symlink handling.
- Authentication, token scopes and the login rate limiter.
- Uploads: atomic claims, conflict policies, size/disk preconditions and
  cleanup after a failed write.
- File tree classification, rename, move, copy, delete and smart rename.
- Metadata: tag and cover round-trips for every format, folder-wide operations,
  and remote cover failures (SSRF guard, size cap, timeout, connection error).
- Text and log routes, JSON error handlers and static-file caching.
- Downloads: tokens, ZIP streaming, symlink exclusion, cancellation and
  unreadable-file handling.
- Addons, config parsing and the version cache.

## Backend conventions

- Patch the module that reads a global (`routes.files`, `routes.tags`,
  `routes.logs`, `routes.system`, `errors`), not the `app` re-export.
- Assert the JSON body and side effects for error responses, not only the
  status code.
- For uploads and text saves, assert that no `.upload-*.part` file is left
  behind after a failure.
- Prefer real audio fixtures from `tests/fixtures/audio` for route-level tag
  tests; use the tag helpers directly for format-specific round-trips.
- Use `monkeypatch` for clocks and sockets instead of sleeping or contacting
  the network.

## Backend test-quality fixes

- The upload/cover 413 tests patched `app.MAX_UPLOAD_BYTES` /
  `app.COVER_UPLOAD_BYTES`, while `errors.handle_request_too_large()` reads its
  own imported constants. They now patch `errors` as well and assert the exact
  limit.
- `test_api_contract.py` used `OSError(13)` and `OSError(2)`, which Python turns
  into `PermissionError` and `FileNotFoundError`; those rows duplicated the
  earlier cases instead of exercising the errno branches, so they were removed.
- `test_find_first_audio_skips_non_audio_and_links` did not create a symlink;
  it now covers both a symlinked file and a symlinked directory.
- The download-token scope check existed in both `test_security.py` and
  `test_auth.py`. The version that also exercises the positive download path is
  kept.

## Frontend

Run the checks from `frontend/`:

```bash
npm ci
npm run lint          # ESLint
npm run format:check  # Prettier, no writes
npm run check         # svelte-check
npm test              # vitest run
npm run build
```

`eslint.config.js` uses the flat config format with `@eslint/js`,
`eslint-plugin-svelte` (recommended rules) and `eslint-config-prettier` to turn
off formatting rules that would fight Prettier. Browser globals apply to
`src/`; Node globals apply to the config files.

`.prettierrc.json` enables `prettier-plugin-svelte`. Use `npm run format` to
rewrite files; `format:check` is the CI-facing read-only check.
`.prettierignore` excludes `dist/`, `node_modules/`, coverage output and
`package-lock.json`.

`svelte-check --tsconfig ./jsconfig.json` validates Svelte templates and
type-checks every JavaScript file under `src/`, including the tests: `checkJs`
is enabled, so a new type error fails `npm run check` without any per-file
opt-in. Components annotate their `$props()` destructuring with a JSDoc
`@typedef`/`@type`; utilities export typedefs for objects that cross module
boundaries. Prefer annotating or narrowing a value over suppressing the error.

`frontend/vitest.config.js` uses a jsdom environment, picks up
`src/**/*.test.js`, and registers the Svelte plugin plus
`@testing-library/svelte`'s `svelteTesting()` plugin for the component tests.
The plugin resolves Svelte's browser build and runs the DOM cleanup after every
test. `src/test/setup.js` clears `localStorage` after every test.

Tests live next to the code they cover: utilities in `src/utils/__tests__/`,
components in `src/components/__tests__/` and stores in `src/stores/__tests__/`.
There is no frontend coverage report yet. As of 2026-10-27 the suite has 41
files and 387 tests.

Covered areas:

- Timestamp parsing, formatting and range validation.
- LRC parsing and building: ID tags, BOM/CRLF, placeholders, multiple
  timestamps, comma decimals and timestamp shifts.
- Tree sorting by name, creation and modification time.
- Upload helpers: junk-file filtering, drop/folder scanning and cancellation,
  existing-file index, directory creation, storage and upload-limit lookups,
  free-space preflight, byte/duration formatting and the XHR upload request
  (progress, success, HTTP/network/timeout/abort failures).
- API error parsing and the cached `/api/version` request.
- Remaining utilities: audio format labels and detection, field metadata,
  folder summaries and byte formatting, colour theme generation, DOM helpers
  (debounce, scroll, text download, height equalisation), favicon accents,
  remote cover previews (caching, deduplication, eviction and failure
  reporting), settings migration/persistence/theme application/smart rename,
  and the hold-to-confirm action.
- Stores: auth session restore, login, logout and authorization headers; the
  context-menu and rename targets; toast creation, removal and timing; theme
  preference, toggling and transition suppression; and the upload queue
  (preflight blocking, duplicate skipping, size limits, queued batches,
  cancellation, retry, 401/413/ENOSPC handling and dismissal).
- `App.svelte`: the login gate, tree loading (including the empty and
  failed/retry states), search and clearing, file-type routing in the right
  panel, the folder overview toggle, root folder creation, keyboard rename and
  delete, logout/re-login, tree refresh events, drag-and-drop and folder-picker
  uploads, the upload progress bar and the disabled-player path.
- Components: `Toast` and `ToastContainer` rendering, type styling, manual
  dismiss, auto-dismiss and store updates; `SortButton` menu, selection and
  direction; the `Login` form states, backend error and theme toggle;
  `CoverPreview` data/remote/placeholder/failure rendering; `HoldButton` hold,
  cancel and disabled states; `MetadataEditor` loading, read-only mode, dirty
  tracking and file saves; `UploadTray` phases, progress, failure details and
  auto-hide; `TreeNode` selection, context-menu actions and inline rename;
  `TextEditor` load, save and clipboard; `EditModal` save and close paths;
  `FolderOverview` missing-field reports; `ImageViewer` loading, retry and the
  full-size view; `TimestampEditModal` validation, range hints and keyboard
  shortcuts; `Player` playback, seeking, clock, volume and disabled state;
  `HelpModal` tabs, version footer and close paths; `LogViewer` loading,
  filtering, clearing, export and auto-refresh; `LRCEditor` columns, timestamp
  editing, import/export, shifting and keyboard shortcuts; `MetadataFetcher`
  addon loading, search, song/album previews and batch apply; `SettingsModal`
  addon list, scheme previews, overview fields and save/cancel.

Conventions:

- Import the utility or component directly; do not go through the
  `utils/index.js` barrel.
- Render components with `render(Component, { props })` from
  `@testing-library/svelte` and query by role or label, not by CSS class,
  unless the class is the behaviour under test.
- Use fake timers for components that schedule work in `onMount`; advance them
  with `await vi.advanceTimersByTimeAsync()` so Svelte flushes the update.
- Store updates made after `render()` and input events need `await tick()`
  from `svelte` before asserting on the DOM.
- Stub browser globals with `vi.stubGlobal()` and restore them in `afterEach`.
- Reset modules with `vi.resetModules()` before testing module-level caches
  such as `version.utils.js` and the upload store's queue runtime.
- Mock a module's dependencies with `vi.hoisted()` plus `vi.mock()`; the
  upload-store test replaces `upload.utils.js` this way.
- Stub `URL.createObjectURL`/`revokeObjectURL` with
  `Object.defineProperty()` instead of replacing the `URL` constructor.
- Mock `fetch`/`XMLHttpRequest`; the suite must not contact the network.
- Keep jsdom prototype stubs such as `scrollIntoView` and
  `HTMLMediaElement.pause` installed for the whole test file; deleting them in
  `afterEach` breaks the component teardown that runs afterwards.
- Add a regression test for every frontend bug, as for the backend.

CI runs `npm run lint`, `npm run format:check`, `npm run check`, `npm test` and
`npm run build` in the `frontend` job of `.github/workflows/tests.yml`; a
failure blocks image publication.

## Maintaining this guide

Update this file when:

- the test count or line coverage moves materially;
- CI or the local test commands change;
- a new test convention is adopted;
- a new area becomes a known coverage gap.

Keep the coverage snapshot and the open backlog current; do not add per-test
history here. The coverage numbers were last measured on 2026-10-25.
