# metadata-docker

A self-hosted web app for browsing an audio library and
editing tags (MP3/FLAC/OGG/Opus/M4A/WAV/AIFF) in the browser. It combines a file
browser, metadata editor, cover-art manager, audio player and
synchronized-lyrics editor. Personal project to manage a
Navidrome library, shared for anyone self-hosting a music server or
maintaining a large local collection.

![File browser and metadata editor](screenshots/image1.png)

## Features

- **Metadata editor** - common and custom tags for MP3, FLAC, OGG/Opus, M4A,
  WAV and AIFF, single files or whole folders (optionally recursive).
- **Cover art** - upload, view, delete, and extract to `cover.jpg`; addons can
  also apply covers from a remote URL.
- **File management** - upload files/folders via drag and drop, move items
  inside the tree, rename, copy and delete from the context menu.
- **Smart rename** - build a naming scheme from metadata fields and apply it to
  files or folders.
- **Player and lyrics** - built-in audio player plus an LRC editor for synced
  lyrics (import/export `.lrc`, timestamp sync, offset shifting).
- **Search and sort** - filter the library, preview images and read application
  logs in the UI.
- **Addons** - fetch metadata from external services through Python plugins.
- **Safe defaults** - login protection, container healthcheck, non-root
  execution, localhost-only binding and atomic uploads.

Known limitation: there is no undo. Changes are applied immediately; the log
viewer keeps a history of what the app did.

## Quick start

Using `docker-compose.yml`:

```yaml
services:
  app:
    image: ghcr.io/jonny-ponny/metadata-docker:latest
    container_name: metadata-docker
    ports:
      - "127.0.0.1:8888:5000"                       # Localhost only; see below
    restart: unless-stopped
    environment:
      - AUTH_USERNAME=USERNAME                      # Replace this
      - AUTH_PASSWORD=PASSWORD                      # Replace this
      - TOKEN_EXPIRE_HOURS=12                       # Optional
      - PUID=1000                                   # User (optional)
      - PGID=1000                                   # Group (optional)
      - TZ=UTC                                      # Timezone (optional)
    volumes:
      - ~/path/to/your/music:/music                 # Library
      - ./logs:/logs                                # Logs
      - ./addons:/app/addons:ro                     # Addons (read-only; trusted code)
```

Start it:

```bash
docker compose up -d
```

Open <http://localhost:8888> and log in with the credentials from the compose
file. If you left them empty, the app prints temporary credentials to the
container logs (`docker compose logs app`) at startup; they change on every
restart. Sessions last `TOKEN_EXPIRE_HOURS` and survive a restart when
`JWT_SECRET` is set; otherwise a new secret is generated for each run.

Set `PUID`/`PGID` to the owner of your music folder, or both to `0` to run as
root (not recommended). A mixed pair such as `PUID=1000, PGID=0` is rejected at
startup: it would leave the app user in the root group without the root-mode
safeguards. When running non-root, `/logs` ownership is fixed on startup;
`/music` is only chowned when `CHOWN_MUSIC=true`, so otherwise the host folder
must already be writable by `PUID`/`PGID`. The compose port is bound to `127.0.0.1`; to reach the
app from other machines, put a TLS-terminating reverse proxy in front of it -
never expose plain HTTP to the internet. See
[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for the full environment reference,
healthcheck, volumes and troubleshooting.

## Usage

### File browser

- Click folders to expand/collapse, click files to load them in the player and
  show their metadata.
- Right-click for the context menu: rename, smart rename, copy, delete, create
  folder.
- Drag & drop files/folders from your computer to upload; drag items inside the
  tree to move them.

### Metadata editing

- Select an audio file, then edit fields in the right panel.
- Press Enter or use the icons to save: file icon applies to the current file,
  folder icon (hold) applies to every file in the folder, trash icon (hold)
  deletes the field.
- "Apply All Changes" saves several fields at once.
- Toggle "Include subfolders" for recursive folder operations.

### Cover art

- Hover over the cover to reveal the actions.
- Upload: file icon for one file, hold the folder icon for a batch.
- Remote URL: use the link icon, paste a public `http(s)` image URL, then the
  file icon applies it to the current file and holding the folder icon applies
  it to every file in the folder (honours the "Recursive" toggle). Click the
  link icon again to close the field. The server downloads the image through
  the same SSRF-guarded proxy as addon covers.
- Delete: hold the trash icon.
- Save as file: extract the embedded cover to `cover.jpg` in the same folder.
- Addon results (Fetch Song/Album Metadata) can still supply a remote cover URL;
  the fetched-metadata preview links back to its source.

### Smart rename

Create a scheme from the metadata fields (or use the default) and apply it from
the context menu to a file or a folder.

### Lyrics editor

Two kinds of lyrics are supported: unsynced plain text and synced LRC.

In the synced editor you can click a timestamp to jump in the audio, edit
timestamps manually, insert the current playback time, shift all timestamps,
import/export `.lrc` (including `[ti:]`/`[ar:]`/`[al:]` headers when known), copy
with or without timestamps, and clear all timestamps.

### Keyboard shortcuts

| Key | Action |
| --- | --- |
| `F2` | Rename selected item |
| `Delete` | Delete selected item |
| `Enter` | Apply current field changes |
| `Esc` | Close modals / cancel rename |

## Configuration

| Variable | Description | Default |
| --- | --- | --- |
| `AUTH_USERNAME` | Login username. Generated and logged if empty. | random per run |
| `AUTH_PASSWORD` | Login password. Generated and logged if empty. | random per run |
| `AUTH_PASSWORD_HASH` | Werkzeug password hash, used instead of `AUTH_PASSWORD`. | unset |
| `JWT_SECRET` | Stable session-token secret, at least 32 characters. Random per run if unset. | random per run |
| `TOKEN_EXPIRE_HOURS` | Session-token lifetime in hours. | `12` |
| `MAX_UPLOAD_MB` | Maximum size of one upload request (one file). | `4096` |
| `PUID` / `PGID` | UID/GID the container runs as. | `1000` |
| `CHOWN_MUSIC` | Recursively chown `/music` to `PUID`/`PGID` at startup. `/logs` is fixed when running non-root. | `false` |
| `MUSIC_FOLDER` / `LOG_DIR` | Library and log paths inside the container. | `/music`, `/logs` |
| `DISABLE_VERSION_CHECK` | Skip the GitHub release check. | `False` |

Uploads are capped per request, not per library: a 50 GB folder works as long
as each file is under `MAX_UPLOAD_MB`. A file with the same name and size is
skipped on re-upload; a different size is saved as `name (1).ext`. See
[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for password hashes, proxy body
limits, the update check and every remaining variable.

## Addons

Addons are Python plugins that fetch metadata from external services. The app
ships with none; drop the ones you want into the `addons` folder and restart.
In the file tree, right-click an audio file and choose **Fetch Song Metadata**,
or right-click a folder and choose **Fetch Album Metadata**. Working examples
include
[MusicBrainz](https://github.com/Jonny-Ponny/md-musicbrainz-addon),
[VocaDB](https://github.com/Jonny-Ponny/md-vocadb-addon),
[LrcLib](https://github.com/Jonny-Ponny/md-lrclib-addon) and
[Genius](https://github.com/Jonny-Ponny/md-genius-addon).

Addons are arbitrary Python code running with the app user's access to `/music`
and `/logs`; only mount addons you trust. Installation, folder layout, addon
environment variables and the fetcher API are documented in
[docs/ADDONS.md](docs/ADDONS.md).

## Security and releases

The shipped compose files bind to `127.0.0.1`. For remote access, terminate TLS
in a reverse proxy and set real credentials. The threat model, addon trust,
path/SSRF protections and hardening options are in [SECURITY.md](SECURITY.md).

Release model (commit -> CI checks -> build -> attestation -> release): every push
to `main` and every `v*` tag runs the pytest and Vitest suites first. Only a
passing commit is built into a multi-arch image, signed with a build-provenance
attestation and published to GHCR; a failing suite publishes nothing. `latest`
follows `main`, while `vX.Y.Z` tags produce versioned image tags. Run
`gh attestation verify`
(see [SECURITY.md](SECURITY.md#image-trust-and-verification)) to confirm an
image was built by this repository's workflow from the expected commit.

## Technology

- **Backend:** Python, Flask, Gunicorn, Mutagen
- **Frontend:** Svelte 5
- **Authentication:** JWT
- **Packaging:** Docker, multi-arch images (amd64, arm64, armv7)

Architecture and development notes live in
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). The backend test commands,
coverage snapshot and test conventions are in [docs/TESTING.md](docs/TESTING.md);
fixed defects and their regression tests are recorded in
[docs/BUGFIXES.md](docs/BUGFIXES.md). For contribution rules and the checks to
run before opening a PR, see [CONTRIBUTING.md](CONTRIBUTING.md).

## Acknowledgments

[mutagen](https://github.com/quodlibet/mutagen) - audio tag reading/writing

[Flask](https://github.com/pallets/flask) - backend framework

[Svelte](https://github.com/sveltejs/svelte) - frontend framework

[Gunicorn](https://github.com/benoitc/gunicorn) - WSGI server

[metadata-remote](https://github.com/wow-signal-dev/metadata-remote) - inspiration
for some features

## License

Copyright (c) 2026 [JonnyPonny](https://github.com/Jonny-Ponny)

This project is licensed under the **AGPLv3** - see [LICENSE](LICENSE).

It uses **Flask** (BSD-3), **Gunicorn** (MIT), **Mutagen** (GPLv2), **PyJWT**
(MIT) and **Svelte** (MIT). See [NOTICE](NOTICE) and
[THIRD-PARTY-LICENSES](THIRD-PARTY-LICENSES) for full attribution.

## Screenshots

LRC editor:
![Synced Lyrics Editor](screenshots/image2.png)

Image file preview:
![Image file preview](screenshots/image3.png)

Logs:
![Logs](screenshots/image4.png)

Settings:
![Settings](screenshots/image5.png)

Context menu options:
![Context menu options](screenshots/image6.png)

## AI disclaimer

AI tools were used for:

- regex and other pattern matching
- frontend CSS styling and JavaScript troubleshooting
- the backend test suite and the module/blueprint refactor

All changes were reviewed, tested and checked in CI before being merged.