# Fixed bugs

Historical record of confirmed defects and the fixes that resolved them. All
items below are fixed and covered by a regression test; the test names are
listed in [Regression tests](#regression-tests).

Line references in B-01 to B-30 point at the tree *before* the Phase 3
refactor. The code now lives in `backend/routes/` and the support modules
(`paths.py`, `errors.py`, `auth.py`, `library.py`, `renaming.py`); new entries
should reference the current files. See [ARCHITECTURE.md](ARCHITECTURE.md) for
the current layout.

Severity legend: **P0** data loss / library escape, **P1** crash or wrong
status code, **P2** correctness or polish.

## Library root and path containment

- [x] **B-01 (P0) `DELETE /api/delete` can delete the whole library.**
  `delete_item()` (`app.py:1204`) accepts `path: "/"`, `"."` or `"./"`;
  `safe_path()` resolves them to `MUSIC_ROOT` and `shutil.rmtree()` removes it.
  **Fix:** refuse to delete the library root itself (`realpath(full_path) ==
  realpath(MUSIC_ROOT)`) with `400`.
  **Test:** delete `"."` and `"/"` -> 400, `MUSIC_ROOT` still exists.

- [x] **B-02 (P0) `POST /api/mkdir` can create a folder outside the library.**
  `create_directory()` (`app.py:1129-1143`) validates `path`, then
  `_unique_path()` turns `MUSIC_ROOT` into `<parent>/music (1)` and creates it.
  **Fix:** reject a resolved path equal to `MUSIC_ROOT`, and re-check
  `_is_within(MUSIC_ROOT, full_path)` after every `_unique_path()` result.
  **Test:** `path: "/"` and `"."` with default and `merge` conflict -> 400; no
  sibling folder appears.

- [x] **B-03 (P0) `POST /api/copy` copies the library to its parent.**
  `copy_item()` (`app.py:1318-1330`) builds `MUSIC_ROOT + " - Copy"` without a
  containment check, so copying `"/"` writes outside the library.
  **Fix:** reject the root item; re-check the generated destination with
  `_is_within()` before `shutil.copytree()` / `copy2()`.
  **Test:** copy `"/"` and `"."` -> 400 and no `music - Copy` sibling.

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
  **Test:** rename onto an existing file -> 409, both files unchanged; rename
  to the same name -> 200.

- [x] **B-06 (P1) `POST /api/move` uses `startswith` for self-containment.**
  `app.py:1267-1269` checks `new_full.startswith(source_full + os.sep)`; the
  same folder reached through a symlink component bypasses the check and can
  be moved into its own subtree.
  **Fix:** `_is_within(source_full, new_full)` (or `dest_full`) with realpath.
  **Test:** move `album` into `album/sub` -> 400; do the same through an
  inside-pointing symlink alias -> 400.

- [x] **B-07 (P1) Concurrent uploads can overwrite each other.**
  `_unique_path()` (`app.py:176`) checked then returned a name; two threads
  uploading the same name could both pick `song (1).mp3` and the second
  `os.replace()` (`app.py:1057`) clobbered the first. Uploads now write the
  temp file first and claim the destination with an atomic `os.link()` that
  fails on `EEXIST`, then retry the next free name. The same check-then-act
  pattern still exists in `copy_item()` and in the duplicate-name loops of
  smart rename; those only copy or rename the same source, so they are
  accepted rather than treated as data loss (see
  [SECURITY.md](../SECURITY.md#accepted-risks--non-goals)).
  **Test:** simulated race between the existence check and the claim; both
  files survive under different names, and an identical concurrent upload is
  skipped.

## Requests, config, errors

- [x] **B-08 (P1) JSON body handling returns HTML or 500.**
  Twelve routes call `request.get_json()` without `silent=True` or a dict
  check (`app.py:895, 927, 1162, 1206, 1239, 1294, 1509, 1585, 1632, 1706,
  1862, 2297`; `1390` already uses `or {}`). Consequences: no/wrong
  `Content-Type` -> Flask HTML 415; malformed JSON -> HTML 400; a JSON list or
  string -> `AttributeError` -> 500.
  **Fix:** one helper, e.g. `_json_object()` returning `(data, error_response)`,
  used by every JSON route; add JSON handlers for `400` and `415`.
  **Test:** for each route: no body, `text/plain` body, malformed JSON, `[]` and
  `"x"` -> JSON error with 400/415, never HTML and never 500.

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

## Metadata and file operations

- [x] **B-12 (P1) Deleting a field from a missing file returns 500, not 404.**
  `delete_metadata_field()` (`app.py:1594-1619`) has no existence check; a
  missing `.mp3` path is treated as a file, the writer returns `False`, and the
  route answers 500 "Failed to delete field". A missing path without an audio
  extension answers 400 "Unsupported file format" instead of 404.
  **Fix:** `os.path.isfile()` / `os.path.isdir()` checks up front -> 404 (and
  keep the folder branch's 404).
  **Test:** missing file and missing folder -> 404.

- [x] **B-13 (P1) Smart rename returns 500 for unreadable metadata or bad input.**
  `extract_metadata()` can return `None` for a corrupt supported file, and
  `generate_name_from_scheme()` then calls `None.get()`
  (`app.py:1988, 2044`). A non-string `scheme` raises in `re.findall`
  (`app.py:1868`).
  **Fix:** validate `scheme`/`path`/`isFolder` types up front; if metadata is
  `None`, return `400` with "Could not read metadata".
  **Test:** monkeypatch `extract_metadata` to return `None` for folder and file;
  non-string `scheme`; both -> 400 JSON.

- [x] **B-14 (P1) Cover endpoints can 500 when metadata cannot be re-read.**
  `update_file_picture_endpoint` (`app.py:1370`), the URL variant (`1411`) and
  `delete_cover_art` (`1653`) call `metadata.get(...)` on a potentially `None`
  result.
  **Fix:** guard with `(metadata or {}).get('picture')`.
  **Test:** monkeypatch `extract_metadata` -> `None`; response is 200/500 JSON
  without `AttributeError`.

- [x] **B-15 (P1) Cover-from-URL downloads before checking the file format.**
  `update_file_picture_from_url_endpoint()` (`app.py:1398-1408`) checks only
  `isfile`, spends a network request, then `update_file_picture()` returns
  `False` for an unsupported format and the route answers 500.
  **Fix:** `is_supported_audio()` check first -> 400, mirroring the file-upload
  route.
  **Test:** target `notes.txt` -> 400 and `fetch_image` is never called.

- [x] **B-16 (P2) Folder picture routes use the raw `MUSIC_FOLDER` for root.**
  `app.py:1480` and `1554` use `MUSIC_FOLDER` directly when `path == ""`, while
  every other route uses the resolved `MUSIC_ROOT`.
  **Fix:** use `safe_path('')` / `MUSIC_ROOT` consistently.
  **Test:** root folder picture update with a relative `MUSIC_FOLDER` behaves
  the same as `path: ""`.

- [x] **B-17 (P2) `save_cover_art_as_file` returns 500 on a corrupt picture.**
  `base64.b64decode()` (`app.py:1725-1745`) raises `binascii.Error` for a
  malformed `picture` payload; the generic handler turns it into 500.
  **Fix:** catch `binascii.Error`/`ValueError` -> 400.
  **Test:** tagged file with a broken data URI -> 400.

- [x] **B-18 (P2) `/api/image` serves any file type.**
  `serve_image()` (`app.py:1670`) only checks `isfile`; `/api/audio` does the
  same. It also duplicates the image MIME table used in `build_tree` and
  `_send_download`.
  **Fix:** restrict `/api/image` to the image extensions listed in the tree;
  move the MIME map to one constant (or `formats.py`).
  **Test:** `/api/image?path=track.mp3` -> 400; a real `.png` -> 200 with
  `image/png`.

- [x] **B-19 (P1) Text save accepts non-strings and is not atomic.**
  `save_text_file()` (`app.py:2301-2313`) calls `f.write(content)` without a
  type check (500 on an int/list) and truncates the file before writing (a
  failed write loses the `.lrc`).
  **Fix:** require `isinstance(content, str)` -> 400; write to a temp file in
  the same directory and `os.replace()`.
  **Test:** non-string content -> 400 and the original file is unchanged;
  monkeypatch the write to fail -> original content survives.
  Also add a size cap (see B-27).

- [x] **B-20 (P1) Reading a non-UTF-8 or oversized text file returns 500.**
  `get_text_file()` (`app.py:2282`) uses strict UTF-8 and reads the whole file.
  **Fix:** decode with `errors='replace'` or return `400` with a clear message;
  cap the read size (e.g. 1 MiB) and return 413/400.
  **Test:** Latin-1 `.lrc` and a file over the cap -> clear JSON error, no 500.

- [x] **B-21 (P2) `/api/logs` mishandles `lines <= 0`.**
  `all_logs[-lines:]` (`app.py:1785`) with `lines=0` returns everything and
  with a negative value returns an unexpected slice.
  **Fix:** clamp to `1..1000`.
  **Test:** `lines=0`, `-1`, `99999` return a bounded list.

## Tag backends

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

## Addons and miscellaneous

- [x] **B-24 (P2) Addon GitHub links allow `http://` and credentials.**
  `_addon_github_url()` (`app.py:2349-2368`) accepts `http://` (mixed content on
  an HTTPS page) and `https://user:pass@github.com/...`.
  **Fix:** require `https`, reject `parsed.username`/`password`.
  **Test:** table of accepted/rejected URLs.

- [x] **B-25 (P2) Addon `limit` is unbounded and can be negative.**
  `search_songs()` / `search_albums()` (`app.py:2409, 2450`) pass any integer
  to the addon.
  **Fix:** clamp to `1..50`, default 5.
  **Test:** `limit=0`, `-1`, `10000` -> clamped value passed to a fake fetcher.

- [x] **B-26 (P2) `get_version_info()` performs a network call at import.**
  `app.py:488` calls GitHub with a 5 s timeout during startup; offline installs
  and tests pay the delay.
  **Fix:** do the first check lazily on `/api/version` (or in a background
  thread), keeping the cache and `DISABLE_VERSION_CHECK` behaviour.
  **Test:** import with a patched `requests.get` that would fail; startup is
  immediate; the first request populates the cache once.

- [x] **B-27 (P2) Text writes are unbounded.**
  `/api/text/save` accepts up to the 4 GiB request limit for a `.lrc`.
  **Fix:** cap text content (e.g. 1 MiB) -> 413/400; mirror the read cap.
  **Test:** oversized content -> 413/400 and the original file unchanged.

- [x] **B-28 (P2) Upload creates target directories before validating the name.**
  `upload_file()` (`app.py:1006`) calls `os.makedirs()` before the filename
  check, so an invalid name still leaves a new empty folder.
  **Fix:** validate the filename first, then create the directory.
  **Test:** invalid name with a new `targetPath` leaves no folder.

- [x] **B-29 (P1) Pin the Flask version required by cover uploads.**
  `limit_cover_upload_size()` assigns `request.max_content_length`
  (`app.py:272`), a Flask 3.1+ feature; `backend/requirements.txt` just says
  `Flask`, so an older install breaks every cover upload with `AttributeError`.
  **Fix:** `Flask>=3.1,<4` (and pin the rest of the direct requirements as
  future hardening).
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
  **Test:** `tests/test_zip_stream.py` - sentinel delivery on a full queue,
  no signal when the consumer left, and a full `iter_zip()` over a one-slot
  queue.

## Startup and credentials

- [x] **B-31 (P1) An invalid `AUTH_PASSWORD_HASH` crash-loops the app.**
  `config.py` raised `RuntimeError` at import when the hash did not parse, so
  the container restarted on every start and the UI never came up.
  **Fix:** log the validation error, discard the malformed hash, and generate a
  temporary password for this run instead of raising. The existing random
  credential block prints it. A valid hash still wins over `AUTH_PASSWORD`.
  **Test:** subprocess import with a malformed hash succeeds, clears
  `AUTH_PASSWORD_HASH`, generates a password different from the configured
  plaintext, and logs both the warning and the temporary credentials.

## Frontend utilities

- [x] **B-32 (P2) Rounded lyrics timestamps can be written as `[00:60.00]`.**
  `secondsToTimestamp()` (`frontend/src/utils/timestamp.utils.js`) rounded the
  seconds field after splitting off the minutes, so `59.999` became
  `[00:60.00]`: a value `validateTimestampFormat()` rejects and players treat
  as invalid. Found by the first Vitest run.
  **Fix:** round to centiseconds first, then derive minutes, seconds and
  centiseconds so the value carries into the next minute.
  **Test:** `frontend/src/utils/__tests__/timestamp.utils.test.js` - `59.999`
  -> `[01:00.00]`; `lyrics.utils.test.js` - parsing `[00:59.999]` writes
  `[01:00.00]`.

## Regression tests

Each bug above is pinned by at least one test, so a fix cannot be reverted
silently.

| Bug | Test |
| --- | --- |
| B-01 | `test_library_root.py::test_delete_cannot_remove_the_library_root` |
| B-02 | `test_library_root.py::test_mkdir_cannot_create_the_library_root` |
| B-03 | `test_library_root.py::test_copy_cannot_duplicate_the_library_root` |
| B-04 | `test_security.py::test_empty_music_folder_falls_back_to_the_default` |
| B-05 | `test_rename.py::test_rename_cannot_overwrite_an_existing_file` |
| B-06 | `test_move.py::test_move_cannot_move_a_folder_into_itself` |
| B-07 | `test_upload.py::test_concurrent_upload_keeps_both_files` |
| B-08 | `test_api_contract.py::test_json_routes_reject_invalid_bodies` |
| B-09 | `test_config.py::test_invalid_integer_env_falls_back_to_the_default` |
| B-10 | `test_tree.py::test_natural_key_handles_digits_int_rejects` |
| B-11 | `test_tree.py::test_file_tree_skips_a_file_that_disappears_mid_walk` |
| B-12 | `test_metadata_endpoints.py::test_delete_field_from_a_missing_path_returns_404` |
| B-13 | `test_metadata_endpoints.py::test_smart_rename_rejects_unreadable_metadata_for_a_file` |
| B-14 | `test_metadata_endpoints.py::test_cover_upload_can_reread_missing_metadata` |
| B-15 | `test_metadata_endpoints.py::test_cover_from_url_checks_the_format_before_fetching` |
| B-16 | `test_metadata_endpoints.py::test_root_folder_cover_uses_the_resolved_library_root` |
| B-17 | `test_metadata_endpoints.py::test_save_cover_as_file_rejects_corrupt_base64` |
| B-18 | `test_metadata_endpoints.py::test_image_endpoint_only_serves_images` |
| B-19 | `test_text_logs.py::test_text_save_rejects_non_string_content` |
| B-20 | `test_text_logs.py::test_text_read_replaces_invalid_utf8` |
| B-21 | `test_text_logs.py::test_log_line_count_is_clamped` |
| B-22 | `test_tag_backends.py::test_detect_image_mime_reads_magic_bytes` |
| B-23 | `test_tag_backends.py::test_lrc_timestamps_accept_the_common_subset` |
| B-24 | `test_addons.py::test_addon_github_url_rejects_unsafe_values` |
| B-25 | `test_addons.py::test_addon_limit_is_clamped` |
| B-26 | `test_version.py::test_import_does_not_call_github_and_the_first_check_is_cached` |
| B-27 | `test_text_logs.py::test_text_save_rejects_oversized_content` |
| B-28 | `test_upload.py::test_invalid_filename_does_not_create_the_target_folder` |
| B-29 | `test_config.py::test_installed_flask_supports_per_request_upload_limits` |
| B-30 | `test_zip_stream.py::test_sentinel_waits_for_queue_space` |
| B-31 | `test_config.py::test_invalid_password_hash_generates_a_temporary_password` |
| B-32 | `frontend/src/utils/__tests__/timestamp.utils.test.js` - `secondsToTimestamp` rounds to centiseconds |
