# Backend testing guide

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

## Coverage

Line coverage is not part of CI yet. To measure it locally:

```bash
pip install pytest-cov
python -m pytest -q --cov=backend --cov-report=term-missing
```

The first measurement on this branch was **83%** (2583 statements, 437 missed).
`config.py` is under-reported because its tests import the app in a subprocess.

Lowest areas at the time of writing:

| Area | Cover | Main gap |
|---|---:|---|
| `safe_fetch.py` | 63% | SSRF guard, redirects, size and content-type limits |
| `routes/tags.py` | 74% | error branches, folder field delete, save-as-file variants |
| `routes/files.py` | 75% | folder delete/move/rename, upload fallbacks, file smart rename |
| `routes/system.py` | 75% | version-check failure branches |
| `routes/text.py` | 78% | `GET /api/text` success path |
| `metadata_writer.py` | 81% | symlink skipping and failure accounting |
| `errors.py` | 84% | 400/415/500 handlers, generic 413 branch |

## Conventions

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

## Missing tests

Priority items still to cover, grouped by risk.

### P0 - security and data safety

- [x] Bulk tag/cover operations skip symlinked files and directories
  (`metadata_writer._iter_audio_files`), including the current-folder-only
  variants.
- [x] `find_first_audio()` skips symlinked audio and symlinked directories.
- [x] Upload claim fallback when `os.link()` is unsupported, and cleanup when
  `os.replace()` fails. `_stream_size()` and `_same_size()` failure paths.
- [x] Forged session tokens (wrong scope, wrong username), session tokens on
  `/api/download`, oversized login credentials, rate-limiter expiry/window
  rollover and table pruning.
- [x] `safe_fetch.py`: malformed URLs, DNS failures, IPv4-mapped/6to4/Teredo,
  redirects with no `Location`, too many redirects, HTTP errors, non-image
  responses, declared and streamed size caps.
- [x] Folder delete, folder move/rename success, missing-path branches, broken
  symlink deletion, and a rename attempt on the library root.
- [x] Unhandled exceptions return JSON, the 400/415 handlers return JSON, the
  generic 413 branch names the request limit, and security headers survive
  error responses.
- [x] `/api` exactly is a JSON 404, not the SPA.

### P1 - core features

- [x] Successful smart rename of a file, no-op when the name already matches,
  collision suffix, boolean validation for `isFolder`/`replaceSpaces`.
- [x] `GET /api/text` success, missing path, missing file, non-text file.
- [x] `/api/metadata/field/delete` on a folder (recursive and current-only).
- [x] Upload validation: no `file` part, empty filename, target is a file,
  backslash/original-filename normalisation.
- [x] `GET /api/metadata?includePicture=false` through the endpoint; behaviour
  for corrupt supported audio.
- [ ] `save-as-file` PNG/raw-base64 paths and the existing `cover.*` suffix
  loop.
- [ ] Download token negative cases and `Content-Disposition` sanitising for
  quotes, backslashes and CRLF.
- [ ] All addon methods advertised; non-dict results; legacy key precedence;
  `reload_plugins()`.
- [ ] Version API failure branches (non-200, empty tag, exception, invalid
  version strings).

### P2 - tag backends and helpers

- [ ] MP4 number-pair parsing/formatting and malformed freeform keys.
- [ ] Custom-field name normalisation and case-insensitive deletion.
- [ ] Clearing the last field removes the tag; multi-value and Unicode values.
- [ ] FLAC front-cover preference; Vorbis invalid base64; empty image data.
- [x] `_apply_to_folder` failure accounting and empty-folder results.
- [ ] Raw log line parsing; `serve()` revalidation for a non-asset static file.

## Test defects fixed on this branch

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
