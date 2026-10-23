# Metadata Docker — improvement plan

Status: **Phase 1 complete.** Phase 2 (tests) is in progress; see the
checkboxes below.

This file replaces the "Security patches plan" and "Suggested improvements
(backlog)" sections This file describes what to change, in what order.

Scope: the Flask backend (`backend/`) unless an item says otherwise. The
frontend has no test suite and has not had a bug pass yet — see
[Out of scope](#out-of-scope).

## Order of work

The order is fixed:

1. **Phase 1 — bugs.** Fix every confirmed bug, smallest diff per commit.
2. **Phase 2 — tests.** Grow `tests/` into real coverage and run it in CI.
3. **Phase 3 — refactor.** Split `backend/app.py` into modules without changing
   behaviour.
4. **Phase 4 — optional security hardening**.
5. **Phase 5 — feature backlog**.

Branches:

- Each phase lives on its own branch, stacked on the previous one because the
  later phases assert the behaviour of the earlier fixes:
  `fix/phase-1-bugs` → `test/phase-2-coverage` → `refactor/phase-3-modules`.
- A phase branch is merged only after its exit criteria are met and its
  `pytest` run is green. Phase 3 starts from the merged Phase 2 branch, so
  the refactor is checked against the complete suite.
- Release/version commits stay off these branches; the app version is bumped
  separately when a phase is merged.

Rules:

- Phase 1 does not move or rename modules. No refactoring while fixing bugs.
- Each bug lists the regression test that Phase 2 must add. If a fix is
  security-critical or data-loss related, add that one test in the same commit;
  the rest wait for Phase 2.
- Phase 3 is behaviour-preserving. Do not mix bug fixes into refactor commits.
- Keep the existing API conventions: `403` outside the library, `404` missing,
  `400` bad input, all user paths through `safe_path()`, derived paths checked
  with `_is_within()` (realpath + `commonpath`, never `str.startswith()`).

Severity legend: **P0** data loss / library escape, **P1** crash or wrong
status code, **P2** correctness or polish.

---

# Phase 1 — Bugs

All line numbers refer to the tree before any refactor. A bug is done when the
fix is in, `python -m py_compile backend/*.py` passes, and the listed test is
queued in Phase 2 (or added with the fix for P0 items).

## 1.1 Library root and path containment

- [x] **B-01 (P0) `DELETE /api/delete` can delete the whole library.**
  `delete_item()` (`app.py:1204`) accepts `path: "/"`, `"."` or `"./"`;
  `safe_path()` resolves them to `MUSIC_ROOT` and `shutil.rmtree()` removes it.
  **Fix:** refuse to delete the library root itself (`realpath(full_path) ==
  realpath(MUSIC_ROOT)`) with `400`.
  **Test:** delete `"."` and `"/"` → 400, `MUSIC_ROOT` still exists.

- [x] **B-02 (P0) `POST /api/mkdir` can create a folder outside the library.**
  `create_directory()` (`app.py:1129-1143`) validates `path`, then
  `_unique_path()` turns `MUSIC_ROOT` into `<parent>/music (1)` and creates it.
  **Fix:** reject a resolved path equal to `MUSIC_ROOT`, and re-check
  `_is_within(MUSIC_ROOT, full_path)` after every `_unique_path()` result.
  **Test:** `path: "/"` and `"."` with default and `merge` conflict → 400; no
  sibling folder appears.

- [x] **B-03 (P0) `POST /api/copy` copies the library to its parent.**
  `copy_item()` (`app.py:1318-1330`) builds `MUSIC_ROOT + " - Copy"` without a
  containment check, so copying `"/"` writes outside the library.
  **Fix:** reject the root item; re-check the generated destination with
  `_is_within()` before `shutil.copytree()` / `copy2()`.
  **Test:** copy `"/"` and `"."` → 400 and no `music - Copy` sibling.

- [x] **B-04 (P1) An empty `MUSIC_FOLDER` disables path containment.**
  `app.py:148` accepts `MUSIC_FOLDER=""`; `safe_path()` (`app.py:821`) then
  returns the raw user path (`if not MUSIC_FOLDER: return file_path`), so
  `/etc/passwd` and absolute upload targets are accepted.
  **Fix:** `MUSIC_FOLDER = os.getenv('MUSIC_FOLDER') or '/music'`, and remove
  the bypass branch from `safe_path()` (a resolved root always exists).
  **Test:** subprocess import with `MUSIC_FOLDER=""`; `safe_path("/etc/passwd")`
  raises `AccessDenied`.

- [x] **B-05 (P1) `POST /api/rename` silently overwrites an existing file.**
  On Linux `os.rename()` replaces the destination. Renaming `a.mp3` to an
  existing `b.mp3` (`app.py:1184-1188`) destroys `b.mp3` with no error.
  **Fix:** if the destination exists and is not the same file, return `409`
  (use `os.path.samefile()` for case-only renames when available).
  **Test:** rename onto an existing file → 409, both files unchanged; rename
  to the same name → 200.

- [x] **B-06 (P1) `POST /api/move` uses `startswith` for self-containment.**
  `app.py:1267-1269` checks `new_full.startswith(source_full + os.sep)`; the
  same folder reached through a symlink component bypasses the check and can
  be moved into its own subtree.
  **Fix:** `_is_within(source_full, new_full)` (or `dest_full`) with realpath.
  **Test:** move `album` into `album/sub` → 400; do the same through an
  inside-pointing symlink alias → 400.

- [x] **B-07 (P1) Concurrent uploads can overwrite each other.**
  `_unique_path()` (`app.py:176`) checked then returned a name; two threads
  uploading the same name could both pick `song (1).mp3` and the second
  `os.replace()` (`app.py:1057`) clobbered the first. Uploads now write the
  temp file first and claim the destination with an atomic `os.link()` that
  fails on `EEXIST`, then retry the next free name. The same check-then-act
  pattern still exists in `copy_item()` and in the duplicate-name loops of
  smart rename; those only copy or rename the same source, so they are tracked
  for Phase 3 rather than treated as data loss.
  **Test:** simulated race between the existence check and the claim; both
  files survive under different names, and an identical concurrent upload is
  skipped.

## 1.2 Requests, config, errors

- [x] **B-08 (P1) JSON body handling returns HTML or 500.**
  Twelve routes call `request.get_json()` without `silent=True` or a dict
  check (`app.py:895, 927, 1162, 1206, 1239, 1294, 1509, 1585, 1632, 1706,
  1862, 2297`; `1390` already uses `or {}`). Consequences: no/wrong
  `Content-Type` → Flask HTML 415; malformed JSON → HTML 400; a JSON list or
  string → `AttributeError` → 500.
  **Fix:** one helper, e.g. `_json_object()` returning `(data, error_response)`,
  used by every JSON route; add JSON handlers for `400` and `415`.
  **Test:** for each route: no body, `text/plain` body, malformed JSON, `[]` and
  `"x"` → JSON error with 400/415, never HTML and never 500.

- [x] **B-09 (P1) Invalid integer env vars crash the app at import.**
  `TOKEN_EXPIRE_HOURS` (`app.py:100`) and `CACHE_TTL_SECONDS` (`app.py:399`)
  use bare `int(os.getenv(...))`. `TOKEN_EXPIRE_HOURS=abc` or
  `CACHE_TTL_SECONDS=soon` raises `ValueError` before Flask starts.
  **Fix:** reuse the `_env_size_mib` pattern with a generic `_env_int(name,
  default, minimum)` that warns and falls back.
  **Test:** subprocess imports with invalid/zero/negative values and succeeds.

- [x] **B-10 (P1) `natural_key()` crashes on some Unicode digits.**
  `part.isdigit()` is true for `²` but `int("²")` raises `ValueError`, so a file
  named `track².mp3` makes `/api/files` return 500 (`app.py:679`).
  **Fix:** `part.isascii() and part.isdigit()`, or a `try/except ValueError`.
  **Test:** library containing `a².mp3` and `a10.mp3` lists in natural order.

- [x] **B-11 (P1) `build_tree()` returns 500 when an entry disappears mid-walk.**
  Only `PermissionError` is caught (`app.py:683-771`); a concurrent delete/rename
  between `listdir()` and `os.stat()` raises `FileNotFoundError`.
  **Fix:** wrap each entry's stat/classification in `try/except OSError:
  continue` (and keep the directory-level `PermissionError` handling).
  **Test:** monkeypatch `os.stat` to raise `FileNotFoundError` for one entry;
  `/api/files` returns 200 and omits that entry.

## 1.3 Metadata and file operations

- [x] **B-12 (P1) Deleting a field from a missing file returns 500, not 404.**
  `delete_metadata_field()` (`app.py:1594-1619`) has no existence check; a
  missing `.mp3` path is treated as a file, the writer returns `False`, and the
  route answers 500 "Failed to delete field". A missing path without an audio
  extension answers 400 "Unsupported file format" instead of 404.
  **Fix:** `os.path.isfile()` / `os.path.isdir()` checks up front → 404 (and
  keep the folder branch's 404).
  **Test:** missing file and missing folder → 404.

- [x] **B-13 (P1) Smart rename returns 500 for unreadable metadata or bad input.**
  `extract_metadata()` can return `None` for a corrupt supported file, and
  `generate_name_from_scheme()` then calls `None.get()`
  (`app.py:1988, 2044`). A non-string `scheme` raises in `re.findall`
  (`app.py:1868`).
  **Fix:** validate `scheme`/`path`/`isFolder` types up front; if metadata is
  `None`, return `400` with "Could not read metadata".
  **Test:** monkeypatch `extract_metadata` to return `None` for folder and file;
  non-string `scheme`; both → 400 JSON.

- [x] **B-14 (P1) Cover endpoints can 500 when metadata cannot be re-read.**
  `update_file_picture_endpoint` (`app.py:1370`), the URL variant (`1411`) and
  `delete_cover_art` (`1653`) call `metadata.get(...)` on a potentially `None`
  result.
  **Fix:** guard with `(metadata or {}).get('picture')`.
  **Test:** monkeypatch `extract_metadata` → `None`; response is 200/500 JSON
  without `AttributeError`.

- [x] **B-15 (P1) Cover-from-URL downloads before checking the file format.**
  `update_file_picture_from_url_endpoint()` (`app.py:1398-1408`) checks only
  `isfile`, spends a network request, then `update_file_picture()` returns
  `False` for an unsupported format and the route answers 500.
  **Fix:** `is_supported_audio()` check first → 400, mirroring the file-upload
  route.
  **Test:** target `notes.txt` → 400 and `fetch_image` is never called.

- [x] **B-16 (P2) Folder picture routes use the raw `MUSIC_FOLDER` for root.**
  `app.py:1480` and `1554` use `MUSIC_FOLDER` directly when `path == ""`, while
  every other route uses the resolved `MUSIC_ROOT`.
  **Fix:** use `safe_path('')` / `MUSIC_ROOT` consistently.
  **Test:** root folder picture update with a relative `MUSIC_FOLDER` behaves
  the same as `path: ""`.

- [x] **B-17 (P2) `save_cover_art_as_file` returns 500 on a corrupt picture.**
  `base64.b64decode()` (`app.py:1725-1745`) raises `binascii.Error` for a
  malformed `picture` payload; the generic handler turns it into 500.
  **Fix:** catch `binascii.Error`/`ValueError` → 400.
  **Test:** tagged file with a broken data URI → 400.

- [x] **B-18 (P2) `/api/image` serves any file type.**
  `serve_image()` (`app.py:1670`) only checks `isfile`; `/api/audio` does the
  same. It also duplicates the image MIME table used in `build_tree` and
  `_send_download`.
  **Fix:** restrict `/api/image` to the image extensions listed in the tree;
  move the MIME map to one constant (or `formats.py`).
  **Test:** `/api/image?path=track.mp3` → 400; a real `.png` → 200 with
  `image/png`.

- [x] **B-19 (P1) Text save accepts non-strings and is not atomic.**
  `save_text_file()` (`app.py:2301-2313`) calls `f.write(content)` without a
  type check (500 on an int/list) and truncates the file before writing (a
  failed write loses the `.lrc`).
  **Fix:** require `isinstance(content, str)` → 400; write to a temp file in
  the same directory and `os.replace()`.
  **Test:** non-string content → 400 and the original file is unchanged;
  monkeypatch the write to fail → original content survives.
  Also add a size cap (see B-27).

- [x] **B-20 (P1) Reading a non-UTF-8 or oversized text file returns 500.**
  `get_text_file()` (`app.py:2282`) uses strict UTF-8 and reads the whole file.
  **Fix:** decode with `errors='replace'` or return `400` with a clear message;
  cap the read size (e.g. 1 MiB) and return 413/400.
  **Test:** Latin-1 `.lrc` and a file over the cap → clear JSON error, no 500.

- [x] **B-21 (P2) `/api/logs` mishandles `lines <= 0`.**
  `all_logs[-lines:]` (`app.py:1785`) with `lines=0` returns everything and
  with a negative value returns an unexpected slice.
  **Fix:** clamp to `1..1000`.
  **Test:** `lines=0`, `-1`, `99999` return a bounded list.

## 1.4 Tag backends

- [x] **B-22 (P1) GIF/BMP/WebP covers are stored as `image/jpeg`.**
  `detect_image_mime()` (`tag_backends.py:135-141`) only recognises JPEG and
  PNG and falls back to JPEG for everything else (including arbitrary bytes).
  `resolve_image_mime()` then trusts any client `image/*`.
  **Fix:** detect GIF/BMP/WebP by magic bytes; return `application/octet-stream`
  or raise for unknown data; prefer magic bytes over the client MIME.
  **Test:** round-trip a GIF, PNG, JPEG, WebP and BMP cover per backend; the
  stored MIME matches the bytes.

- [x] **B-23 (P2) LRC parsing is narrower than the format.**
  `lrc_to_sylt_events()` (`tag_backends.py:182-194`) requires exactly two
  decimal places and two-digit minutes, so `[0:12.34]` and `[00:12.345]` are
  silently dropped. `format_sylt_timestamp()` can print `[00:60.00]` for
  `59.999`.
  **Fix:** accept 1-2 digit minutes and 2-3 decimal places; normalise rounding
  before formatting. Document the supported subset in the docstring.
  **Test:** table-driven cases including boundary `59.999`, `60.0`, `[1:02.5]`.

## 1.5 Addons and miscellaneous

- [x] **B-24 (P2) Addon GitHub links allow `http://` and credentials.**
  `_addon_github_url()` (`app.py:2349-2368`) accepts `http://` (mixed content on
  an HTTPS page) and `https://user:pass@github.com/...`.
  **Fix:** require `https`, reject `parsed.username`/`password`.
  **Test:** table of accepted/rejected URLs.

- [x] **B-25 (P2) Addon `limit` is unbounded and can be negative.**
  `search_songs()` / `search_albums()` (`app.py:2409, 2450`) pass any integer
  to the addon.
  **Fix:** clamp to `1..50`, default 5.
  **Test:** `limit=0`, `-1`, `10000` → clamped value passed to a fake fetcher.

- [x] **B-26 (P2) `get_version_info()` performs a network call at import.**
  `app.py:488` calls GitHub with a 5 s timeout during startup; offline installs
  and tests pay the delay.
  **Fix:** do the first check lazily on `/api/version` (or in a background
  thread), keeping the cache and `DISABLE_VERSION_CHECK` behaviour.
  **Test:** import with a patched `requests.get` that would fail; startup is
  immediate; the first request populates the cache once.

- [x] **B-27 (P2) Text writes are unbounded.**
  `/api/text/save` accepts up to the 4 GiB request limit for a `.lrc`.
  **Fix:** cap text content (e.g. 1 MiB) → 413/400; mirror the read cap.
  **Test:** oversized content → 413/400 and the original file unchanged.

- [x] **B-28 (P2) Upload creates target directories before validating the name.**
  `upload_file()` (`app.py:1006`) calls `os.makedirs()` before the filename
  check, so an invalid name still leaves a new empty folder.
  **Fix:** validate the filename first, then create the directory.
  **Test:** invalid name with a new `targetPath` leaves no folder.

- [x] **B-29 (P1) Pin the Flask version required by cover uploads.**
  `limit_cover_upload_size()` assigns `request.max_content_length`
  (`app.py:272`), a Flask 3.1+ feature; `backend/requirements.txt` just says
  `Flask`, so an older install breaks every cover upload with `AttributeError`.
  **Fix:** `Flask>=3.1,<4` (and pin the rest of the direct requirements as part
  of Phase 4 item 1).
  **Test:** import-time assertion that the Flask version satisfies the floor;
  CI installs from the pinned requirements.

- [x] **B-30 (P0) Folder downloads can hang forever.**
  `iter_zip()` (`zip_stream.py:151`) announced completion with
  `chunks.put_nowait(_SENTINEL)`. When the consumer had not drained the last
  chunks, the bounded queue was full, the sentinel was silently dropped and the
  response generator blocked on `chunks.get()` for good: the worker thread
  finished, but the client never received the end of the archive. Found while
  running CI: `tests/test_downloads.py` hung in roughly one run out of four.
  **Fix:** deliver the sentinel with a bounded retry (give up only when the
  consumer is gone and `stop` is set) and let the consumer stop polling when
  the producer thread has exited.
  **Test:** `tests/test_zip_stream.py` — sentinel delivery on a full queue,
  no signal when the consumer left, and a full `iter_zip()` over a one-slot
  queue.

## Phase 1 exit criteria

- Every P0/P1 item above is fixed.
- P2 items are either fixed or moved to "known issues" in this file with a
  reason.
- `python3 -m py_compile backend/*.py` passes.
- The existing `pytest` suite (once dependencies are installed) passes.
- Manual smoke: login, tree, upload one file, rename/move/copy/delete one file,
  edit one tag, download one folder, preview a remote cover.
- No module moves or renames in the same commits.

---

# Phase 2 — Tests

Goal: `tests/` stops being "security regressions only". Cover every route and
every non-trivial helper at least once, and make CI run the suite.

## 2.1 Infrastructure

- [x] Add a CI job to `.github/workflows/container-release.yml` (or a separate
      `tests.yml`) that runs `pip install -r requirements-dev.txt` and
      `python -m pytest -q` on pull requests and pushes. The release job stays
      independent.
- [x] `tests/conftest.py`:
  - autouse fixture resetting `_login_failures` and `_version_cache`;
  - a `library` fixture that guarantees each test starts with a clean,
    uniquely named subtree (keep the session-wide app import for now);
  - a `fake_fetcher` fixture that injects a class into
    `plugin_manager.fetchers` without writing files;
  - a helper for creating a valid audio file per format.
- [ ] Optional: `pytest-cov` (non-blocking) and `pytest-xdist` after Phase 3
      removes import-time globals.

## 2.2 Test files

- [x] `tests/test_security.py` / `tests/test_library_root.py` — empty
  `MUSIC_FOLDER` defaults to `/music` (B-04); root delete/mkdir/copy guards
  (B-01..B-03).
- [x] `tests/test_api_contract.py` — every JSON route rejects a missing body,
  `text/plain`, malformed JSON, `[]` and `"x"` with a JSON 400/415 (B-08).
- [ ] `tests/test_api_contract.py` (remaining)
  - every `/api/*` route without a token → 401 (table asserted against
    `app.url_map` so a new unprotected route fails the test);
  - security headers on a normal response;
  - unknown `/api/*` and `/api/*/*` → JSON 404, never HTML/SPA;
  - `_public_error_message` table (403/404/409/500/502/503/504).
- [x] `tests/test_config.py` — invalid integer environment values fall back
  instead of crashing at import (B-09).
- [ ] `tests/test_auth.py`
  - 5 failures → 429 + `Retry-After`; success clears the counter;
  - expired session token → 401; tampered signature → 401;
  - download token rejected on session routes (already covered) and accepted
    only by `/api/download?token=`.
- [ ] `tests/test_paths.py`
  - `safe_path` NUL, absolute `/etc/passwd`, `..`, sibling prefix
    (`/music-other`), inside/outside symlinks;
  - `_is_within` prefix and symlink cases;
  - `_generated_rename_path` separators, `.`/`..`, NUL, whitespace, escape.
- [ ] `tests/test_files.py`
  - `build_tree` classification (`audio`/`image`/`text`/`other`),
    `.upload-*.part` hidden, symlinked dir skipped, outside symlink
    skipped, permission error yields `[]`;
  - copy naming/symlinks, delete symlink vs target, mkdir rename/merge
    (existing cases stay).
- [x] `tests/test_tree.py` — natural sort with `²` names and entries that
  disappear between `listdir()` and `stat()` (B-10, B-11).
- [x] `tests/test_upload.py` — existing conflict/atomicity cases plus the
  simulated concurrent upload race (B-07).
- [x] `tests/test_rename.py` — overwrite rejection, same-name no-op, normal
  rename (B-05).
- [x] `tests/test_move.py` — self-move, symlink alias, normal move (B-06).
- [x] `tests/test_metadata_endpoints.py` — missing path → 404, unreadable
  metadata on smart rename, `None` metadata after cover changes, corrupt
  base64, image/audio type guards, root folder palettes (B-12..B-18).
- [ ] `tests/test_metadata.py`
  - tag round-trip for every `FIELD_SCHEMA` field on MP3/WAV/AIFF/FLAC/
    OGG/Opus/M4A/M4B using committed small fixtures (`tests/fixtures/`);
  - comment vs description vs custom fields; lyrics (SYLT) and unsynced
    lyrics (USLT);
  - cover set/get/delete on all three picture storages;
  - `delete_field` / `delete_cover_art`, `read_only_metadata`, empty payload
    invariant: `set(FIELD_SCHEMA) == set(empty_metadata()) - {'customFields'}`.
- [x] `tests/test_tag_backends.py` — magic-byte MIME detection and LRC/SYLT
  timestamp parsing (B-22, B-23).
- [ ] `tests/test_downloads.py`
  - file download headers, Unicode filenames (`_content_disposition`),
    folder ZIP contents, symlink exclusion, empty folder, `iter_zip` error
    before/after first byte, expired/tampered token, token path escape.
- [x] `tests/test_text_logs.py` — invalid UTF-8, size caps, non-string
  content, atomic write, log line clamping (B-19, B-20, B-21, B-27).
- [ ] `tests/test_text_logs.py` (remaining) — log level/search filters, clear,
  no log file → empty result.
- [x] `tests/test_addons.py` — GitHub URL validation and limit clamping
  (B-24, B-25).
- [ ] `tests/test_addons.py` (remaining)
  - list shape, legacy metadata normalisation, unimplemented methods → 400,
    failing fetcher → JSON error with `success: false`;
  - `PluginManager` discovery: underscore files ignored, broken module skipped,
    duplicate id last-wins.
- [ ] `tests/test_formats.py`
  - unique extensions, every family has a backend, MIME non-empty,
    case-insensitive lookup, default MIME.
- [x] `tests/test_version.py` — import does not fetch, first check is cached
  (B-26).
- [ ] `tests/test_version.py` (remaining) — `_compare_versions` table and
  `DISABLE_VERSION_CHECK`.

## 2.3 Regression matrix

Every `B-xx` item from Phase 1 must appear in at least one test name or
docstring, so the fix cannot be reverted silently. Add a short table at the end
of `tests/` (or keep it here) mapping bug → test.

## Phase 2 exit criteria

- `python -m pytest -q` passes locally and in CI.
- Every route has at least one authenticated success case and one failure case.
- Every helper listed above has a unit test.
- No test depends on network access, wall-clock timing or the developer's
  filesystem.

---

# Phase 3 — Refactor

Goal: `backend/app.py` becomes a composition root. No behaviour change; each
step is a separate commit with the Phase 2 suite green before and after.

## Target layout

```
backend/
  app.py                 # create_app(), blueprints, security headers, static fallback
  config.py              # env parsing -> Settings (music_root, log_dir, limits, auth, version)
  errors.py              # AccessDenied, public error mapping, JSON handlers
  paths.py               # safe_path, is_within, unique_path, generated_rename_path, root guard
  auth.py                # login, token_required, rate limiter + reset hook
  library.py             # build_tree, natural_key, file classification
  renaming.py            # scheme parsing + name generation (pure functions)
  downloads.py           # content disposition, send_download, download tokens
  routes/
    __init__.py          # register_blueprints(app)
    files.py             # files, mkdir, upload, storage, rename, move, copy, delete
    tags.py              # metadata + cover art + audio/image serving
    text.py
    logs.py
    addons.py
    system.py            # ping, version
```

`tag_backends.py`, `zip_stream.py`, `safe_fetch.py`, `metadata_extractor.py`
and `plugin_manager.py` stay single modules; they are already cohesive.
`metadata_writer.py` keeps its public functions but loses the internal
duplication (see step 7).

## Steps, in order

1. **`paths.py`.** Move `safe_path`, `_is_within`, `_unique_path`,
   `_generated_rename_path`, plus the new root guard from B-01..B-03. Delete the
   duplicate `_is_within` in `zip_stream.py` and import the shared one.
   Gate: path tests green.
2. **`errors.py`.** Move `AccessDenied`, `_public_error_message`,
   `_server_error`, `_permission_error`, the 400/413/415/500 handlers and the
   security headers. Gate: error-mapping and API-contract tests green.
3. **`config.py`.** One `Settings` object (or module constants) built from env
   with `_env_int` / `_env_size_mib`; remove the `MUSIC_FOLDER` vs `MUSIC_ROOT`
   split. Keep `logger_config` reading `LOG_DIR` as today.
4. **`renaming.py`.** Extract `generate_name_from_scheme`, `extract_year`,
   `find_first_audio` and the duplicate-name loop from the 245-line
   `apply_renaming_scheme()` route. Unit-test the pure functions; the route
   becomes a thin validator + `os.rename` call.
5. **`auth.py`.** Move `token_required`, login, `_constant_time_eq`,
   `_password_matches`, the limiter and its state. Expose
   `reset_rate_limiter()` for tests. Keep the decorator import path stable for
   routes.
6. **Route blueprints.** Move routes one file at a time, starting with
   `system.py` (ping/version), then `logs.py`, `text.py`, `addons.py`,
   `downloads.py`, `tags.py`, `files.py`, `library.py`. Move route-specific
   helpers with their routes. Gate: full suite green after each blueprint.
7. **`metadata_writer.py`.** Collapse the four near-identical single-file
   functions into one `_modify(path, action)` dispatcher; keep the public
   function names so routes do not change. This guarantees identical logging
   and unsupported-format handling.
8. **Deduplicate the folder routes.** `update_folder_files` /
   `update_folder_files_current_only` and the two picture-folder routes share
   one helper with a `recursive` flag. Keep response shapes and messages
   identical.
9. **Shared constants and MIME maps.** One image MIME map (B-18), one text
   extension set, one file-classification table inside `build_tree`.
10. **App factory last.** `create_app(settings=None)`; keep
    `app = create_app()` at module level so `gunicorn app:app` is unchanged.
    Update `tests/conftest.py` to build an app per test session (or per module),
    remove the subprocess hack in
    `test_unset_credentials_never_become_admin_admin`, and then enable
    `pytest-xdist`.
11. **Stop wildcard imports.** Replace `from metadata_extractor import *` and
    `from metadata_writer import *`; this also removes the route/function name
    collisions (`delete_metadata_field`, `delete_cover_art`) noted in Phase 1.

## Non-goals

- No service/repository layer, no classes around routes, no async, no database.
- Do not split `tag_backends.py` per format or redesign `zip_stream.py`.
- Do not change API response shapes or status codes during Phase 3.
- Do not add new features while refactoring.

## Phase 3 exit criteria

- `app.py` contains only app creation, blueprint registration, static fallback
  and startup logging.
- No module imports another route module; dependencies point one way
  (`routes -> paths/errors/auth/config/...`).
- `tests/` passes unchanged (except `conftest.py` when the factory lands).
- `gunicorn app:app` still boots and serves the SPA and API.
- `python3 -m py_compile backend/*.py` passes.

---

# Phase 4 — Optional security hardening

Threat model: this is a single-admin app intended to
run on localhost or a trusted LAN behind a TLS-terminating reverse proxy. The
operator manages the library, addons are arbitrary trusted Python, and the
container is not a boundary between mutually hostile users. The goal is to
prevent accidental exposure and low-effort attacks, not to build a multi-tenant
service.

## Baseline (already landed)

- Session tokens carry `scope: 'session'`; download tokens are accepted only by
  the download route.
- Login never falls back to default credentials: a missing username or password
  is generated randomly per process (unless `AUTH_PASSWORD_HASH` is used),
  comparison is constant-time, and failed attempts are rate-limited.
- Cover-from-URL fetches go through an SSRF guard with redirect revalidation,
  an `image/*` check, a size cap and timeouts. Browser previews use the same
  guard.
- Addons are treated as trusted code: both compose files mount `./addons`
  read-only, addon dependency installs run as the unprivileged user (skipped for
  root), and `/app` is not recursively chowned.
- Path handling resolves symlinks with `realpath`. `build_tree()` skips
  symlinked directories and outside-pointing files; bulk tag/cover operations,
  folder copies and ZIP downloads avoid following links out of the selected
  folder.
- Unhandled exceptions return a generic JSON error while the real exception is
  logged. Permission, missing-file, network, disk-space and read-only failures
  still return a clear category and status, without exposing exception text.
- Request bodies are bounded per request: `MAX_UPLOAD_MB` (default `4096`) for
  normal uploads and 20 MiB for cover-art uploads, with JSON `413` responses.
  Folder drag-and-drop uploads send one request per file, so this caps a single
  file rather than the whole library.
- Uploads are written to a hidden `.upload-*.part` file and moved into place
  with `os.replace()`; a full disk or an aborted save leaves no partial track in
  the tree. Free space in `/music` and the spool temp directory is checked
  before a drop starts, and files above `MAX_UPLOAD_MB` are rejected before any
  bytes are sent.
- Smart rename validates the generated name before `os.rename` in both the file
  and folder branches: empty/`.`/`..` names, separators and NUL are rejected,
  and `_is_within(MUSIC_ROOT, new_path)` must hold after duplicate handling.
- The app sends CSP, `X-Content-Type-Options`, `X-Frame-Options`,
  `Referrer-Policy` and `Permissions-Policy`. HSTS is left to the reverse proxy.

Phase 1 (B-01..B-29) is complete and strengthens this baseline: root
operations are refused, uploads claim their destination atomically, every JSON
route rejects non-object bodies with JSON errors, and text reads/writes are
bounded and atomic. Phase 2 extends the pytest suite beyond the security
invariants.

## P2 — optional and deployment-specific

1. **Supply-chain hygiene, kept proportionate.** Add a `.dockerignore`
   (`.git`, `node_modules`, `dist`, `backend/static`, `.env*`, `__pycache__`,
   `logs`), use `npm ci` with the existing lockfile, and pin the direct Python
   requirements (including `Flask>=3.1,<4`, see B-29). Pinning base images by
   digest and GitHub Actions by commit SHA is optional; if done, add an update
   bot so it does not rot. Run `pip-audit`/`npm audit` periodically or as a
   non-blocking CI job rather than making releases depend on them.
2. **Harden the shipped compose examples without breaking the entrypoint.**
   - Add `security_opt: [no-new-privileges:true]`, `pids_limit: 256`, generous
     `mem_limit`/`cpus` (for example `2g`/`2`), and `tmpfs: /tmp`.
   - Keep `./logs:/logs` as a bind mount; do not replace it with tmpfs in the
     shipped examples, because logs are user-facing history.
   - Add a `CHOWN_MUSIC` flag (default `false`) so the recursive
     `chown -R /music` runs only when explicitly enabled. Keep the small
     `/logs` ownership fix and document that a mismatched `PUID`/`PGID`
     otherwise needs a manual one-time chown.
   - Make the compose comments state that `PUID=0`/`PGID=0` runs the app as
     root and is not recommended.
   - `read_only: true` and `cap_drop: [ALL]` are reasonable only after the
     entrypoint stops writing `/etc` (no `adduser`/`usermod`; run gunicorn as
     numeric `PUID:PGID`) and `/app/.local` is a writable volume or tmpfs.
     `cap_drop: ALL` alone breaks user switching. Treat this as an optional
     later step, not a compose-only edit.
3. **Persist the JWT secret (availability).** Accept an optional `JWT_SECRET`
   environment variable; otherwise keep the random per-process secret. This
   avoids logging everyone out on restart but is not a security requirement.

## Verification

- Run the full `pytest` suite (Phase 2), not just the old security subset.
- Manual checks: `docker compose config`, a login/logout cycle, an addon cover
  fetch from a public URL, `curl` against `401`/`403`/`413` responses, and a
  container start as a non-root `PUID`/`PGID`.
- When touching paths, test both a symlink that resolves inside the library and
  one that resolves outside it.

## Accepted risks / non-goals

- TLS and HSTS are handled by the reverse proxy; Flask does not manage
  certificates.
- Addons remain arbitrary Python by design; only trusted addons should be
  mounted.
- Single-admin authentication stays single-admin; no per-user permissions,
  audit identities or sessions.
- The JWT stays in `localStorage` with a strict CSP instead of an `HttpOnly`
  cookie plus CSRF protection. This is an accepted trade-off for a single-admin
  app.
- No token revocation/`jti`; tokens are short-lived and a restart invalidates
  them.
- No full TOCTOU hardening (`O_NOFOLLOW`/`dir_fd`) and no blanket ban on
  symlinks. `realpath` containment plus skipping links in tree, bulk and ZIP
  operations is considered sufficient. The remaining race requires concurrent
  write access to the library and a deliberate attack; closing it would touch
  every file operation for little practical gain here. (The upload name race
  B-07 is in scope because it can happen without an attacker.)
- Builds are not hermetic or reproducible; dependency pinning and periodic
  audits are proportionate to the project size.

---

# Phase 5 — Feature backlog

These are proposals, not descriptions of current
behaviour. Ordered by impact.

## Correctness and security

- Add a structured operation journal (old/new tag values, rename/move/delete
  records) so changes are auditable and reversible.

## High-impact features

- Undo and trash: soft-delete into a hidden folder excluded from `build_tree`,
  plus an "Undo" toast action and a history panel. This is TODO #33 and the main
  limitation listed in the README.
- Batch operations as jobs: folder metadata/cover updates run synchronously in
  `_apply_to_folder`. Add `POST /api/jobs` + `GET /api/jobs/<id>` with
  progress, cancel, and a visible `failed_files` list. Uploads already have a
  client-side queue with byte progress, cancel and retry; making them survive a
  closed tab needs a resumable server-side upload session.
- Library-wide tag search: search currently filters filenames client-side
  (`filterTreeBySearch`). Add an mtime-invalidated tag index and reuse it for
  reports (missing fields, missing covers, duplicate artist/title).
- Stream audio instead of fetching a whole blob in `loadAudioFile`: reuse the
  download-token pattern so `<audio src="/api/audio?token=...">` gets Range
  requests. Add a play queue, next/prev, shuffle/repeat, and Media Session
  support.
- Multi-select in the tree with batch actions, plus copy/paste tags from one
  file onto a selection.

## UX and performance

- Lazy file tree (`?path=` per directory with mtime cache) instead of walking
  the whole library on every `/api/files`.
- Smart-rename dry-run preview with a conflict strategy instead of silently
  appending `(1)`; do not derive folder tags from only the first audio file.
- Addon reload from Settings, per-addon load-error/version display, and optional
  install from git URL.
- Responsive/mobile layout (there is one `@media` breakpoint), more keyboard
  shortcuts (`Ctrl/Cmd+F`, `Space`, arrows, `Ctrl+S`, `Ctrl+Z`), and
  aria/focus handling in modals and the context menu.
- Metadata CSV/JSON export-import and library normalisation tools (case,
  whitespace, album-artist fill, track padding).

---

# Out of scope

- **Frontend bug pass and tests.** `frontend/src/App.svelte` is ~17k lines of
  components in total and has no test runner. The backend plan above does not
  cover it. If wanted later: a Vitest pass over the pure utilities
  (`upload.utils.js`, `lyrics.utils.js`, `timestamp.utils.js`,
  `sort.utils.js`), then component tests.
- Container/runtime hardening beyond Phase 4.
- Multi-user authentication or per-user libraries.

# Commands

```bash
# Backend tests
pip install -r requirements-dev.txt
python -m pytest -q

# Offline syntax check
python3 -m py_compile backend/*.py

# Frontend build (the only current frontend check)
cd frontend && npm run build

# Local container
cp .env_example .env
docker compose -f docker-compose.dev.yml up --build
```
