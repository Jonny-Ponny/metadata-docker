# Addons

Addons are small Python plugins that fetch metadata from outside sources. Open
the fetcher from the file tree: right-click an audio file and choose **Fetch
Song Metadata**, or right-click a folder and choose **Fetch Album Metadata**.
Pick a fetcher, search for a song or album, then apply the results to the file or
the folder.

> **Addons are arbitrary Python code.** They run inside the container with the
> app user's access to `/music` and `/logs`, so only mount addons you trust.
> The folder is mounted read-only, and addon dependency installs run as the
> unprivileged `PUID`/`PGID` user, never as root (root mode skips runtime
> dependency installation). See [SECURITY.md](../SECURITY.md).

The app ships with no addons. You install the ones you want by dropping them
into the `addons` folder, which `docker-compose.yml` mounts at `/app/addons`.
Everything in that folder is scanned once at container start.

## Installing an existing addon

Working examples: [MusicBrainz](https://github.com/Jonny-Ponny/md-musicbrainz-addon),
[VocaDB](https://github.com/Jonny-Ponny/md-vocadb-addon),
[LrcLib](https://github.com/Jonny-Ponny/md-lrclib-addon) (lyrics, songs only), and
[Genius](https://github.com/Jonny-Ponny/md-genius-addon).

Clone an addon repo into its own subfolder inside `addons`:

```bash
mkdir -p addons
git clone https://github.com/Jonny-Ponny/md-musicbrainz-addon.git addons/musicbrainz
git clone https://github.com/Jonny-Ponny/md-lrclib-addon.git addons/lrclib
```

Then restart the container so it discovers the new files:

```bash
docker compose restart
```

The addon now appears in the **Fetch Song Metadata** / **Fetch Album Metadata**
dialogs (and in **Settings -> Addons**, which also lists the methods and
environment variables it supports).

### Folder layout

A subfolder per addon is the easiest option. You can also drop a single `.py`
file directly into `addons/`, with no subfolder:

```text
addons/
├── musicbrainz/                 # subfolder layout
│   ├── MusicBrainz.py
│   └── MusicBrainz_requirements.txt
├── lrclib/
│   ├── LrcLib.py
│   └── requirements.txt         # name does not matter in a subfolder
└── simple_addon.py              # flat layout
```

Only files ending in `requirements.txt` are installed, so the dependency file
must be named accordingly. In a subfolder any `*requirements.txt` works
(e.g. `requirements.txt` or `LrcLib_requirements.txt`). Directly in `addons/` it
must end with `_requirements.txt`, e.g. `simple_addon_requirements.txt` - a
plain `requirements.txt` in the flat root is ignored.

### Environment variables

Some addons need an API key or a setting. Read the addon's README to see which
variables it expects, then add them to the `environment` section of your
`docker-compose.yml` and recreate the container:

```yaml
services:
  app:
    environment:
      - AUTH_USERNAME=USERNAME
      - AUTH_PASSWORD=PASSWORD
      - MD_MUSICBRAINZ_FETCH_COVER=true   # example addon setting
      - MY_API_KEY=your-key-here          # example API key
```

The names shown under **Settings -> Addons** are informational - the addon
decides whether a missing value is a hard error or just falls back to a default.
In practice, set what the addon's README asks for.

A restart is not enough after changing `environment` values; recreate the
container so Docker applies them:

```bash
docker compose up -d
```

A few things to keep in mind:

- The container installs `*requirements.txt` dependencies on every start as the
  unprivileged `PUID`/`PGID` user (into `/app/.local`), before the app launches.
  The first start after adding an addon can take a bit longer.
- If you run the container as root (`PUID=0`), runtime addon dependency
  installation is disabled. Install the dependencies in a custom image derived
  from this one, or run with a non-root `PUID`/`PGID`.
- Dependencies are installed inside the container, so changing an addon's
  requirement file requires a container restart.
- The addons folder is read-only inside the container. Addons that write cache
  files must use `/tmp` or another writable location.
- The host addons folder must be readable by `PUID`/`PGID`; normal `755`/`644`
  permissions are sufficient. The container does not chown it because it is
  mounted read-only.
- Plugins are loaded once at startup; editing a `.py` file or adding a new one
  has no effect until you restart.
- A broken addon is skipped with an error in the logs (`docker compose logs`).
  One bad addon will not stop the app.

## Writing your own fetcher

An addon is a single Python file that subclasses `MetadataFetcher` from
`addon_base.py`. Subclass it, set the attributes, and implement only the methods
you need.

```python
# addons/my_service/MyService.py
import os
import requests
from addon_base import MetadataFetcher


class MyService(MetadataFetcher):
    name = "My Service"                 # shown in the UI
    id = "my_service"                   # unique, lowercase, no spaces
    description = "Fetches metadata from My API"
    version = "1.0.0"                   # optional, shown in Settings
    github = "https://github.com/you/md-my-service-addon"  # optional, shown as a link
    required_env_vars = ["MY_API_KEY"]  # informational only

    BASE_URL = "https://api.example.com"

    def __init__(self):
        self.api_key = os.getenv("MY_API_KEY", "")
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "metadata-docker-addon/1.0"})

    def search_songs(self, query, limit=5):
        resp = self.session.get(
            f"{self.BASE_URL}/search",
            params={"q": query, "limit": limit, "key": self.api_key},
            timeout=10,
        )
        resp.raise_for_status()
        return [
            {
                "id": str(item["id"]),          # required: passed back to fetch_song_metadata
                "title": item.get("title", ""),
                "artist": item.get("artist", ""),
                "extraInfo": item.get("duration", ""),  # optional, display-only
            }
            for item in resp.json().get("results", [])
        ]

    def fetch_song_metadata(self, song_id):
        resp = self.session.get(
            f"{self.BASE_URL}/track/{song_id}",
            params={"key": self.api_key},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "title": data.get("title", ""),
            "artist": data.get("artist", ""),
            "album": data.get("album", ""),
            "albumArtist": data.get("album_artist", ""),
            "date": data.get("release_date", ""),
            "trackNumber": data.get("track_number", ""),
            "genre": data.get("genre", ""),
            "picture": data.get("cover_url"),   # URL or data:image/... value
        }
```

Save the file as `addons/my_service/MyService.py`, restart the container, and
the fetcher is available.

### Required attributes

| Attribute | Purpose |
| --- | --- |
| `name` | Display name in the frontend |
| `id` | Unique identifier. Used in API URLs and stored in the browser, so keep it stable |
| `description` | Short line shown in Settings |
| `version` | Optional version string shown in Settings |
| `github` | Optional GitHub URL shown as a clickable link in Settings. Only `github.com` links are displayed |
| `required_env_vars` | List of env var names to display in Settings. Not enforced by the app |

### The four methods

You do not need all of them. Leave out the ones your service cannot support -
the UI only shows fetchers that implement the matching search method.

| Method | Called when | Returns |
| --- | --- | --- |
| `search_songs(query, limit)` | Song search | List of result dicts, each with an `id` |
| `fetch_song_metadata(song_id)` | A song result is selected | One metadata dict |
| `search_albums(query, limit)` | Album search | List of result dicts, each with an `id` |
| `fetch_album_metadata(album_id)` | An album result is selected | List of metadata dicts, one per track |

The `id` from a search result is passed to the matching `fetch_*` method. Search
results also feed the result list in the UI, so include `title`/`artist` for
songs and `album`/`artist`/`coverart` for albums where available. `coverart` is
only a thumbnail for the search results; use `picture` in fetched metadata to
actually embed artwork.

### Metadata fields

Return plain key/value dictionaries using the app's field names (`title`,
`artist`, `album`, `albumArtist`, `date`, `genre`, `trackNumber`, `diskNumber`,
`comment`, `composer`, `publisher`, `releaseType`, `lyrics`, `unsyncedLyrics`,
`picture`, ...). Unknown keys are kept and written as custom tags, so
service-specific IDs (e.g. `musicbrainz_trackid`) can be returned too.

Older addons may return `year`, `track`, or `disk`. Those are still accepted and
treated as `date`, `trackNumber`, and `diskNumber`, but they are not written as
literal YEAR/TRACK/DISK tags. New addons should use the current names.

### Extra information in the UI

Search results and fetched metadata may include an optional display-only
`extraInfo` key. It is shown under the result title and above the field picker,
but it is never offered as a tag or written to a file. Use it for short plain
text that helps identify a result or explain where it came from, such as song
duration, the source, or how metadata was aggregated. Omit the key or return an
empty string when there is nothing to show.

### Practical tips

- Use `os.getenv()` for API keys and settings, and give sensible defaults where
  possible.
- Set a `User-Agent` and a `timeout` on HTTP requests; rate-limit if the service
  requires it.
- Raising an exception is fine - the API returns it as an error and the UI shows
  the message. Returning an empty list from a search is often friendlier for
  "no results".
- Avoid doing network calls at import time. Keep them in `__init__` or in the
  methods, so a temporarily unavailable service does not break loading.
- Dependencies go in a `*requirements.txt` file next to the addon, one package
  per line. The container installs them on the next start as the unprivileged
  `PUID`/`PGID` user; installation is skipped when running as root (`PUID=0`).
- `addon_base` is importable because the backend runs from the directory
  containing it. Outside Docker, the addons folder is resolved relative to the
  process working directory (`backend/addons` if you run the backend from
  `backend/`).

For reference check the working examples linked above.
