# Deployment

Running, configuring and updating the container. The security model and
hardening checklist are in [SECURITY.md](../SECURITY.md); the code layout is in
[ARCHITECTURE.md](ARCHITECTURE.md).

## Compose

The shipped `docker-compose.yml` is the starting point:

```yaml
services:
  app:
    image: ghcr.io/jonny-ponny/metadata-docker:latest
    container_name: metadata-docker
    ports:
      - "127.0.0.1:8888:5000"
    restart: unless-stopped
    environment:
      - AUTH_USERNAME=${AUTH_USERNAME:-}
      - AUTH_PASSWORD=${AUTH_PASSWORD:-}
      - AUTH_PASSWORD_HASH=${AUTH_PASSWORD_HASH:-}
      - TOKEN_EXPIRE_HOURS=${TOKEN_EXPIRE_HOURS:-12}
      - MAX_UPLOAD_MB=${MAX_UPLOAD_MB:-4096}
      - PUID=1000
      - PGID=1000
      - TZ=UTC
    volumes:
      - ~/path/to/your/music:/music
      - ./logs:/logs
      - ./addons:/app/addons:ro
```

Start it with `docker compose up -d` (or `docker-compose up -d` on Compose V1)
and open <http://localhost:8888>. The port is bound to `127.0.0.1` on purpose;
see [Exposure](#exposure) before changing that.

## Environment variables

| Variable | Description | Default |
| --- | --- | --- |
| `AUTH_USERNAME` | Login username. Generated and logged if empty. | random per run |
| `AUTH_PASSWORD` | Login password. Generated and logged if empty. | random per run |
| `AUTH_PASSWORD_HASH` | Werkzeug password hash, used instead of `AUTH_PASSWORD`. | unset |
| `TOKEN_EXPIRE_HOURS` | Session-token lifetime in hours. | `12` |
| `MAX_UPLOAD_MB` | Maximum size of one upload request (one file). Cover art has a separate 20 MiB cap. | `4096` |
| `PUID` | UID the container drops to. | `1000` (image) |
| `PGID` | GID the container drops to. | `1000` (image) |
| `MUSIC_FOLDER` | Library path inside the container. | `/music` |
| `LOG_DIR` | Log directory. | `/logs` |
| `CONTAINER_PORT` | Port gunicorn binds inside the container. | `5000` |
| `DEBUG` | Flask debug mode. | `False` |
| `CACHE_TTL_SECONDS` | How long the GitHub update check is cached. | `3600` |
| `DISABLE_VERSION_CHECK` | Skip the GitHub release check entirely. | `False` |
| `TZ` | Container timezone, used by log timestamps. | `UTC` |

Invalid or empty integer values (`TOKEN_EXPIRE_HOURS=abc`, `MAX_UPLOAD_MB=0`)
log a warning and fall back to the default instead of crashing at startup.

`APP_GIT_SHA` is not operator-configurable: the image build sets it to the
commit SHA and `/api/version` exposes it.

Set `PUID`/`PGID` to the owner of your music folder. `0` runs the container as
root; it is supported but not recommended. The container does not run as root
by default.

### Password hash instead of a plaintext password

Generate a Werkzeug hash and set `AUTH_PASSWORD_HASH`:

```bash
python -c "from werkzeug.security import generate_password_hash; print(generate_password_hash('your-password'))"
```

If both `AUTH_PASSWORD` and `AUTH_PASSWORD_HASH` are set, the hash wins and a
warning is logged. An invalid hash is logged and a temporary password is
generated for this run instead of failing startup, so a typo cannot put the
container into a restart loop. Fix the variable and restart to use the hash.

If neither password variable is set, a random password is generated at startup
and printed to the logs; it changes on every restart. The app never falls back
to a known default credential. After five failed logins from one address, login
is locked for 15 minutes.

## Volumes

| Mount | Purpose |
| --- | --- |
| `~/path/to/your/music:/music` | Music library (read/write) |
| `./logs:/logs` | Application logs (read/write) |
| `./addons:/app/addons:ro` | Addons (read-only; trusted Python code) |

## Uploads

Uploads are one request per file, so `MAX_UPLOAD_MB` caps a single file, not a
drop. Dragging a 50 GB folder still works as long as every file is under the
cap. If a reverse proxy sits in front of the app, its request-body limit must be
at least as large.

The client checks free space in `/music` and in the container's temp directory
(the spooled request bodies live there) before sending anything, reports byte
progress, and can cancel or retry. Files above the cap are rejected before any
bytes leave the browser. A file that already exists with the same name and size
is skipped by default, so re-dropping a folder only uploads what changed; a
same-name file of a different size is saved as `name (1).ext`. Switch to "Keep
both" under Settings -> Uploads to always rename the incoming file.

Inside the API, uploads write a hidden `.upload-*.part` file and rename it into
place, so an interrupted save never leaves a truncated track in the tree.

## Healthcheck

The image defines a `HEALTHCHECK` that polls the unauthenticated `/api/ping`
endpoint every 30 s (5 s timeout, 120 s start period, 5 retries). `docker ps`
shows the container as healthy once the app and its addon dependencies are
ready.

An unhealthy status alone does not restart the container. Addon dependency
installation happens before the app starts, so a slow first boot can briefly
show `(unhealthy)` and recover. To disable the check or adjust the timings:

```yaml
services:
  app:
    healthcheck:
      disable: true
      # interval: 30s
      # timeout: 5s
      # start_period: 120s
      # retries: 5
```

## Exposure

The compose file binds to `127.0.0.1`, so the app is not reachable from other
machines. For remote access, put a TLS-terminating reverse proxy in front of it
instead of publishing the Flask port:

```caddyfile
metadata.example.com {
    reverse_proxy 127.0.0.1:8888
}
```

Never expose plain HTTP to the internet: the login password and bearer tokens
would travel in clear text. If you deliberately bind to `0.0.0.0` for a trusted
LAN, anyone on that network can reach the login page.

The full exposure checklist (credentials, CSP, `localStorage` trade-off, addon
trust) is in [SECURITY.md](../SECURITY.md#exposure-checklist).

## Updates and version check

The app checks the latest GitHub release on the first `/api/version` request
and caches the result for `CACHE_TTL_SECONDS`. The first check is lazy, so an
offline install starts immediately. Set `DISABLE_VERSION_CHECK=true` to turn it
off; the Help footer then only shows the current version and commit.

`latest` moves with every push to `main`, while digests do not. To pin what you
run, reference the digest:

```bash
docker buildx imagetools inspect ghcr.io/jonny-ponny/metadata-docker:latest
# Digest: sha256:...
```

```yaml
image: ghcr.io/jonny-ponny/metadata-docker@sha256:...
```

To build the image yourself from a reviewed tag:

```bash
git clone --branch v1.0.4 https://github.com/Jonny-Ponny/metadata-docker.git
cd metadata-docker
docker build -t metadata-docker .
```

See [SECURITY.md](../SECURITY.md#image-trust-and-verification) for verifying
the published image.

## Troubleshooting

### Permission issues

- Verify `PUID`/`PGID` match your host user and group.
- Check folder permissions: `ls -la /path/to/your/music`.
- The app needs read/write on the library and `/logs`; a mismatch shows up as
  `403` or `500` responses and permission errors in the log.
- The container does not recursively `chown` `/music`; run a one-time
  `chown -R <PUID>:<PGID> /path/to/your/music` if the IDs differ.

### Can't reach the web interface

- Verify the container is running and healthy: `docker ps` (see `STATUS`).
- Check the logs: `docker logs metadata-docker` or `./logs/app.log`.
- Make sure the port (`8888` by default) is not blocked and that you are not
  trying to reach a `127.0.0.1` binding from another machine.
- If you left the credentials unset, copy the generated ones from the startup
  log; they change on every restart.

### Addon problems

Installation, dependency handling and write-your-own-fetcher details are in
[ADDONS.md](ADDONS.md). A broken addon is skipped with an error in the log and
does not stop the app.
