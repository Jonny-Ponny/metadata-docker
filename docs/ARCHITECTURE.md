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
   ├── library.py     build_tree(), build_directory() and natural sorting
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
  library.py             build_tree, build_directory, summarize_tree,
                         search_tree, natural_key, classification
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
    files.py             listing (full tree, per-folder, summary, search),
                         upload, storage, mkdir, rename, move, copy, delete,
                         smart rename
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

The tree is loaded lazily. `GET /api/files/dir?path=<folder>` lists one folder
(`library.build_directory`); the SPA fetches the root once, then each folder
when it is expanded, so opening the app no longer walks the whole library.
`GET /api/files` still returns the full nested tree (`library.build_tree`) for
callers that want it in one request.

Both endpoints share `_scan_entries`, so classification, natural sorting,
symlink handling and the hidden `.upload-*.part` rule cannot drift. Entries are
classified as `audio`, `image`, `text` or `other` (everything else is listed
read-only). Sorting is natural (`a2` before `a10`), including filenames with
Unicode digits that `int()` rejects. Entries that disappear during the walk are
skipped instead of failing the request; a permission error or a folder that
vanishes mid-walk yields an empty listing rather than a 500.

Every directory node carries `folder_count`, `file_count` and `file_size`
describing its **direct** children, computed from the listing already in hand.
Directory entries from `/api/files/dir` have no `children` and set
`has_children` so the client can tell an empty folder from an unloaded one.

The tooltip still shows **deep** totals. Hovering a folder for 150 ms requests
`GET /api/files/summary?path=<folder>` (`library.summarize_tree`), which walks
that subtree once and returns the recursive folder/file counts, total size and
per-extension counts. The client shows `Calculating…` above the direct-child
numbers until that answer arrives, caches the result for the session, and drops
it whenever a mutation touches the folder or one of its ancestors. At most five
format lines are shown; the rest collapse into `+N more formats` so a folder
with many extensions cannot grow the tooltip past the viewport.

Search is server-side: `GET /api/files/search?q=<text>&limit=<n>`
(`library.search_tree`) walks the library and returns name matches with the
`parents` chain above each hit. Results stop at `DEFAULT_SEARCH_LIMIT` (200)
and the response sets `truncated`. The SPA debounces input by 250 ms,
cancels a superseded request, loads the folders above every hit and expands
them, so a match inside a collapsed folder is still reachable. An active search
never shows "No music files found"; it shows `No matches for "<query>"`.

On the client, `stores/tree.store.js` keeps the per-path cache, one in-flight
request per folder, and re-fetches only the folders a mutation touched.

Symlink policy: symlinked directories are never listed, symlinked files are
listed only when they resolve inside the library, and bulk tag/cover
operations, folder copies and ZIP downloads do not follow links out of the
selected folder.

Uploads write a hidden `.upload-*.part` file and claim the destination with an
atomic `os.link()` (falling back to `os.replace()`), so an interrupted upload
leaves no truncated track in the tree and two concurrent uploads cannot
overwrite each other. Both listing functions hide `.upload-*.part` files.

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

### Tree keyboard navigation

`TreeNode` is recursive and only folders the user opened are fetched, so
walking the DOM would be fragile. Instead `utils/tree.utils.js` turns the
lazy cache, the expanded set and the current sort into a flat row list
(`flattenVisibleRows`) and the cursor is an index into it. The helpers there
(`stepRow`, `pageRow`, `parentRow`, `firstChildRow`, `findByPrefix`) are pure
and unit-tested.

`App.svelte` keeps a cursor path (`activeRowPath`), separate from the
selection: moving it only highlights a row, so scrolling with the arrow keys
never loads audio or fetches metadata. A click moves the cursor onto the clicked
row but hides its dashed outline (it is a keyboard affordance); the next arrow
key shows it again, so the cursor and the selection never show two highlighted
rows after mouse use. Enter selects (file to the editor, folder toggles), Ctrl/Cmd+Enter
selects and moves focus into the right panel (rows forward it themselves).
Ctrl/Cmd+Shift+E switches between the tree and the right panel from anywhere,
including a metadata field, and is the way back to the tree without the mouse.
Space is the global play/pause key: it plays and pauses wherever focus is, and
is ignored only on typing surfaces (and while a dialog or the context menu owns
the keyboard). It is deliberately _not_ handed back to a focused button or link,
because closing a dialog returns focus to its opener (see [Dialogs](#dialogs))
and Space would otherwise activate that button again; buttons are activated with
Enter or a click, and a select opens with Enter. Space is therefore checked
before the shared guard, which treats a `<select>` like a typing field;
`spaceBelongsToControl` decides instead and keeps Space only where it types a
character (text, search, number, email, url and password inputs, textareas,
contenteditable, `role="textbox"`). A range input is excluded: Space did nothing
on a slider, so reserving it only silenced playback after the volume was
touched. The tree
itself uses Right/Left to expand and collapse. A roving tabindex keeps exactly one row in the Tab order; focus follows the cursor while the keyboard is
in the tree, which a `focusin` listener tracks (typing targets and open overlays
keep the tree keys off). Rows forward their keys through `onRowKeys` with their
own path, and the tree panel forwards keys pressed on it, so both start from a
visible row. When a rename input unmounts (Enter, Esc or a blur), focus returns
to the renamed row (or stays in the right panel if the rename started there),
so the tree keeps working without the switch shortcut. Row elements get their
id from `treeRowId(path, prefix)` (`utils/tree.utils.js`), which encodes every
character outside `[A-Za-z0-9]` as `-<code point>`: the cursor moves DOM focus
by looking the row up with `getElementById`, so ids must stay unique for names
that differ only in non-ASCII characters (see B-44 in
[BUGFIXES.md](BUGFIXES.md)). The guards live in
`stores/keyboard.store.js` (`shouldIgnoreShortcut`, `isTypingTarget`,
`isOverlayOpen`); F2 and Delete read the same cursor, so they act on the row
the keyboard is on.

The rows are exposed as an ARIA tree (T-18). The `.file-tree` `<ul>` carries
`role="tree"`, a label ("Music library", or "Search results" while searching)
and `aria-activedescendant`, pointing at the cursor row. Focus stays on the
row itself, so the row's own `id` is what gets announced; the rows report it up
through `onRowId`, because the search view renders the same rows with a
`search-` prefix. Each row is `role="treeitem"` with `aria-level` from its
depth, `aria-selected` from the selection, and `aria-posinset`/`aria-setsize`
from its position among its siblings (folders and files are sorted separately,
so the count is not simply the folder listing length). Only folders get
`aria-expanded`, since a file cannot expand. Nested lists are `role="group"`
and their `<li>` wrappers are `role="none"`, so the tree is flat to a screen
reader as it is to the keyboard model.

The tree element, not the panel, is the keyboard element: it handles `keydown`
and the press that marks the tree as keyboard-active, and it is a Tab stop only
when no row holds one. DOM focus stays on the activated row, so after moving
into a folder no top-level row holds the stop (the roving path prefers one of
those); the tree then keeps the keyboard reachable by focusing itself. The
search box sits outside the tree rather than inside its `role="tree"`
container, and the rows keep DOM focus, which is why the panel no longer needs
a `role` or a tabindex of its own.

### Dialogs

Every dialog is an overlay plus a panel, and the panel carries the semantics:
`role="dialog"`, `aria-modal="true"`, a label, and `tabindex="-1"` so the panel
itself can hold focus when it has no controls. `utils/focus.utils.js` provides
the two handlers they share: `keepTabInDialog` (Tab wraps from the last control
to the first and Shift+Tab the other way, and focus that has escaped is pulled
to the first control) and `keepFocusInDialog` (focus landing on `body` or on a
control behind the overlay is sent back into the dialog). Both read the panel
from `event.currentTarget`, so they are wired straight onto the panel's
`onkeydown` / `onfocusin` and never need a selector - two dialogs that share a
class name, or are mounted together, cannot capture each other's keys. The
overlay click still closes a dialog; that is the pointer path and needs no
help.

Escape is owned by the **topmost** dialog. Dialogs are mounted while closed and
nested (the synced lyrics editor opens its own text and timestamp dialogs), so a
plain window listener in each one closed all of them on a single keypress.
`dialogOpenEffect(panel, isOpen, onClose)` registers a dialog while it is open,
closes it on Escape only when it is on top of the stack (stopping the event so
the dialogs underneath and the app's own Escape handling never see it), and
gives focus back to the element that opened it when it closes. Without that
last part a keyboard user's next Tab restarted from the top of the page. Focus
is captured synchronously, before a dialog auto-focuses its first field, so it
is the trigger and not that field that gets restored. A nested dialog returns
focus to the control inside its parent (closing the lyrics text editor puts
focus back on the "Edit lyrics" button, not past it). Use
it in every dialog: `let panel = $state(null)`, `bind:this={panel}` on the
panel, and `$effect(() => dialogOpenEffect(panel, isOpen, onClose))`.

`openDialog`/`closeDialog` also mark everything outside the topmost dialog
`inert`. The elements are each ancestor's siblings, walking up from the panel,
not `body`'s children: the app is mounted inside one wrapper, so a dialog is
never a child of `<body>` and hiding `body`'s children would hide the dialog
along with it. Only what this module marked is restored on close, so an `inert`
set elsewhere survives. This is the mechanism that keeps the browser's Tab
inside the dialog: `keepTabInDialogWith` only wraps at the ends of a dialog's
control list and leaves moves in the middle to the browser, so after the last
control the browser stepped into a dialog underneath (the text dialog renders
as a sibling of the lyrics editor, not inside it) or out into the page.
`openDialog` marks synchronously, then re-runs after a microtask, because the
open usually happens in an effect before the new dialog's DOM update lands; the
window-level Tab listener re-runs it too, so the state is right whenever the
browser is about to move focus.

The player bar is app chrome, not page content, and the lyrics editor needs it
to play and pause while the user taps along. It is marked
`data-dialog-companion` and `hidingOutside()` skips those subtrees, so the bar
stays clickable under every dialog (its own stacking keeps it above the
overlay). The lyrics panel also carries `data-player-space`: Space is the
player key there instead of activating the focused editor button.
`topDialogTakesPlayerSpace()` reads that marker, so other dialogs (settings
checkboxes, for example) keep their native Space handling.

Dialogs that also block app shortcuts (the lyrics text and timestamp editors)
stop those keys in the capture phase but must let **Escape and Tab** through:
Escape has to reach the close handler, and a capture-phase stop swallowed Tab
before the stack's bubble-phase listener ran, leaving that dialog with no
containment at all so Tab walked out into the browser chrome.

**Every dialog must register through `dialogOpenEffect`.** Calling
`openDialog`/`closeDialog` directly from an effect is what broke the log viewer
(B-48): the effect runs before `bind:this` binds the panel, so the cleanup
unregistered `null` and the dialog stayed on the stack after it closed. The
helper captures the element it registered and owns Escape and focus return.
`isOverlayOpen()` reads the stack for the same reason, rather than keeping a
separate list of dialog class names.

Every scrollable pane inside a dialog carries `tabindex="-1"` (`.modal-body`,
`.settings-content`, `.help-content`, `.log-display`,
`.modal-scrollable-content`). Firefox adds scrollable regions to the tab order
so they can be scrolled from the keyboard, which placed a focusable,
non-control element between the close button and the first field: Tab appeared
to stop on the dialog's own edge, while Shift+Tab - which never met it - looked
fine. An explicit `tabindex` opts out, and the pane still scrolls with the
arrow keys once focus is on a control inside it. A new dialog with a scrolling
body needs the same attribute.

### Context menu

A row's menu lives in the `contextMenu` store (`stores/context.store.js`), which
records the target path, the anchor point and how the menu was opened. Only the
target row renders it, as a sibling of the row rather than inside it.

The pointer path opens it at the cursor. The keyboard path - `Alt+Enter`,
`Shift+F10` or the context-menu key, handled by the row itself and by
`handleTreeNavigation` when the panel has focus - centres it on the row and
moves focus to the first item. `aria-keyshortcuts` on every row lists those
keys and `aria-controls` points at the menu. `Alt+Enter` is the one to document
as primary: Firefox opens its own context menu for `Shift+F10` and no handler
can stop it (MDN: with Shift held, the native menu appears without a
`contextmenu` event), and screen readers may not send the Menu key. Both
standard keys are still accepted because they work for people whose
environment sends them.
The items are real controls
(`role="menu"` / `role="menuitem"`, `tabindex="-1"`, roving focus), so Arrow
up/down, Home/End, Enter and Space work; Escape closes and returns focus to the
row. That focus return only happens for keyboard opens, since the pointer path
never moved focus.

Placement is `placeMenu` in `utils/contextMenu.utils.js`, which is pure and
unit-tested: it opens in the pointer quadrant, flips to the other side when the
menu would overflow, and - when the menu is taller than the free area and fits
on neither side - pins it to the top edge and caps its height so the list
scrolls. The old code flipped up and then clamped to the top margin, which
pushed a tall menu's bottom past the window edge.

The free area excludes the **player bar**, which is fixed to the bottom of the
window with the same `z-index` as the menu, so a menu placed there is painted
behind it. `positionMenu` measures the bar at open time (it is absent when the
player is disabled) and passes its height as the viewport's `bottom` inset; an
anchor that sits behind the bar gets the menu slid into the free area instead of
flipped. A unit test sweeps every anchor and menu size and asserts the menu
never overlaps the bar or leaves the window.

Delete is a `HoldButton` with `role="menuitem"`, so it keeps its hold-to-confirm
behaviour: the same `createHold` timer runs for a pointer press and for Enter or
Space held on the item, and releasing early cancels both.

### Metadata editor keyboard handling

The editor is a long list of text fields with per-field action icons, so the
icons are pointer-only (`tabindex="-1"`) and each action is a shortcut on the
focused field: Enter applies to the file, holding Ctrl/Cmd+Enter applies to the
folder, holding Ctrl/Cmd+Delete deletes the field (from the folder when "Tag
deletion applies to folder" is on), and Alt+ArrowUp/Down move between fields.
Native word-wise arrows and selection are left alone.

Holding rather than confirming in a dialog keeps it consistent with the mouse
hold-to-confirm buttons and reuses the same durations from Settings. Both
gestures run on `createHold()` from `utils/hold2confirm.utils.js`, which owns
the timing and progress; `holdToConfirm` is the pointer action on top of it.
Releasing the key cancels, so a folder-wide change needs a deliberate hold.

### Lyrics editor

`LRCEditor.svelte` shows one row per lyric line: the timestamp in a narrow
gutter on the left, the text centred in the column that takes the remaining
width. Both cells are children of the same grid row (`grid-template-columns:
subgrid`), so they can never drift apart and nothing needs to be re-measured
after a line wraps; the resize-observer height equalisation the three-column
layout needed is gone.

Two states live on a row and they are deliberately separate. The **active**
line is where playback is (`findActiveLine` in `utils/lyrics.utils.js`, which
returns the last timed line at or before the current time and skips untimed
lines; a gap made by a blank line used to pin the highlight, B-50). The
**selection** is where edits go, and only the lyrics column produces it: plain
click selects one line, Shift+click a range from the anchor, Ctrl/Cmd+click
toggles one. The timestamp cell never selects, it seeks (a placeholder line has
nothing to seek to and is disabled), so one column has one job and every line
behaves the same for selection. Both states are marked on their own cell (the
playing line gets the left-edge marker in the timestamp column, the selection in
the lyrics column and its timestamp) so the playing line stays visible inside a
multi-line selection.

Editing actions all act on the selection:

- **In place** - double-clicking a line swaps its text for a single-line input;
  Enter or blur commits, Escape cancels and is stopped so the editor underneath
  stays open. Editing is pointer-only until keyboard row navigation exists: a
  click re-renders the row it selected, so there is no stable focused element
  for Enter to act on.
- **Footer shift** - the −/+ buttons move every timestamp, or only the
  selection when the `Selected (n)` scope is active. `shiftTimestampSelection`
  moves exactly those lines and refuses a move that would cross the nearest
  timed line on either side, including a neighbour that moves with the
  selection. The selection survives a shift, so one capture is rarely the
  right amount and the buttons can be pressed repeatedly.
- **Per-row −/+** - the same amount applied to one line, leaving the selection
  alone.
- **+ Line / Delete** - `insertLyricLine`/`deleteLyricLines` keep the lyrics
  and the timestamp array aligned; the new line starts untimed and opens for
  typing, and deleting everything leaves one empty line.

Bulk operations (import, the whole-lyrics modal, clearing) call
`refreshAfterBulkEdit()`, which also clears the selection because the indices
only mean something for the text they were picked on; shifts pass
`keepSelection` because they do not change the line count. Line indices are the
`{#each}` keys, so a reordered line rebuilds its row rather than reusing the
wrong DOM.

## Tests

The suite runs against a temporary music library and log directory created by
`tests/conftest.py`; each test gets a unique subtree. The Flask app is imported
once per session, with the plugin manager pointed at the throwaway working
directory. Tests that patch a module-level global must target the module that
reads it (`routes/files.py`, `routes/tags.py`, `routes/logs.py`,
`routes/system.py`), not `app` - see the fixtures in `conftest.py`.
`build_tree` runs in `library.py` (and `app.build_tree` is only a wrapper), so
the B-11 race tests patch `library`, not `app`.

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
the workflow's OIDC identity. `edge` follows the default branch, `latest` moves
only when a final `vX.Y.Z` tag is pushed, and `vX.Y.Z` tags produce `X.Y.Z` and
`X.Y` image tags. Pre-release tags such as `vX.Y.Z-rc.1` produce only their own
`X.Y.Z-rc.1` tag and never move `latest`.

The frontend is built once per build in a stage pinned to `$BUILDPLATFORM`, so
the bundle is not recompiled under QEMU for each target. The bundle is
platform-independent and is copied into every architecture's final stage. That
stage stays on `node:22-bookworm-slim`: Node 24 and newer publish no
`linux/arm/v7` image, while the final `python:3.15-alpine` stage does. The
frontend installs with `npm ci` from `frontend/package-lock.json`, and
`frontend/.nvmrc` plus the `engines` field in `frontend/package.json` document
the Node range the tooling needs.

The commit SHA is baked into the image (`APP_GIT_SHA`) and exposed by
`/api/version`, so a running container can be matched to its attestation. See
[SECURITY.md](../SECURITY.md#image-trust-and-verification) for the verification
commands.

Releases are cut by bumping `APP_VERSION` in `backend/config.py`, committing,
tagging `vX.Y.Z` and pushing the tag.
