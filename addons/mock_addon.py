"""Mock metadata fetcher for testing the addon UI.

Copy this file into the configured addons folder (``./addons`` for Docker,
``backend/addons`` when running the backend from ``backend/``) and restart the
app. It needs no network access and no extra dependencies.

It implements every fetcher method so both song and album modes can be tested,
and it deliberately returns different kinds of ``extraInfo`` values: short,
multi-line, very long, and missing.
"""

from addon_base import MetadataFetcher


SONGS = {
    "mock-song-1": {
        "title": "Mock Song One",
        "artist": "Test Artist",
        "album": "Mock Album One",
        "albumArtist": "Test Artist",
        "date": "2024",
        "genre": "Electronic",
        "trackNumber": "1",
        "diskNumber": "1",
        "comment": "Metadata returned by the mock addon.",
        "composer": "Mock Composer",
        "publisher": "Mock Records",
        "releaseType": "Album",
        "unsyncedLyrics": "First mock lyric line\nSecond mock lyric line",
        "mock_source": "mock_addon",
        "extraInfo": "3:42 · album version · source: mock addon",
    },
    "mock-song-2": {
        "title": (
            "Mock Song Two With A Deliberately Long Title That Should Wrap "
            "In The Results List And Preview"
        ),
        "artist": "Another Test Artist",
        "album": "Mock Album Two",
        "albumArtist": "Another Test Artist",
        "date": "2023-05-17",
        "genre": "Ambient",
        "trackNumber": "2",
        "diskNumber": "1",
        "comment": "This result has a deliberately long extraInfo value.",
        "composer": "Another Mock Composer",
        "extraInfo": (
            "Duration 4:05 · 320 kbps · source: mock addon\n"
            "Aggregated from three imaginary sources. This extraInfo value is "
            "deliberately long so the result row and the preview banner can be "
            "checked for line wrapping, preserved newlines, and vertical growth. "
            "It also mentions which fields came from which source: title and "
            "artist from Source A, album and date from Source B, and lyrics from "
            "Source C."
        ),
    },
    "mock-song-3": {
        "title": "Mock Song Three Without Extra Info",
        "artist": "Third Test Artist",
        "album": "Mock Album Three",
        "albumArtist": "Third Test Artist",
        "date": "2022",
        "genre": "Jazz",
        "trackNumber": "3",
        "diskNumber": "1",
    },
}


ALBUMS = {
    "mock-album-1": {
        "title": "Mock Album One",
        "artist": "Test Artist",
        "date": "2024",
        "extraInfo": "3 tracks · 2024 · source: mock addon",
    },
    "mock-album-2": {
        "title": "Mock Album Two Without Extra Info",
        "artist": "Another Test Artist",
        "date": "2023-05-17",
    },
}


ALBUM_TRACKS = {
    "mock-album-1": [
        {
            "title": "Mock Track One",
            "artist": "Test Artist",
            "album": "Mock Album One",
            "albumArtist": "Test Artist",
            "date": "2024",
            "genre": "Electronic",
            "trackNumber": "1",
            "diskNumber": "1",
            "extraInfo": "3:42 · track 1 · mock metadata",
        },
        {
            "title": "Mock Track Two With A Longer Title",
            "artist": "Test Artist",
            "album": "Mock Album One",
            "albumArtist": "Test Artist",
            "date": "2024",
            "genre": "Electronic",
            "trackNumber": "2",
            "diskNumber": "1",
            "extraInfo": (
                "4:05 · track 2 · source: mock addon\n"
                "Long per-track extraInfo for testing the folder batch file "
                "cards. This line is intentionally long enough to wrap."
            ),
        },
        {
            "title": "Mock Track Three Without Extra Info",
            "artist": "Test Artist",
            "album": "Mock Album One",
            "albumArtist": "Test Artist",
            "date": "2024",
            "genre": "Electronic",
            "trackNumber": "3",
            "diskNumber": "1",
        },
    ],
    "mock-album-2": [
        {
            "title": "Mock Album Two Track One",
            "artist": "Another Test Artist",
            "album": "Mock Album Two",
            "albumArtist": "Another Test Artist",
            "date": "2023-05-17",
            "genre": "Ambient",
            "trackNumber": "1",
            "diskNumber": "1",
            "extraInfo": "2:58 · extra info only, no newlines",
        },
    ],
}


def _clamp_limit(limit):
    try:
        return max(1, int(limit))
    except (TypeError, ValueError):
        return 5


class MockAddon(MetadataFetcher):
    name = "Mock Addon"
    id = "mock_addon"
    description = (
        "Returns local mock data for testing search results, album batches, "
        "and the display-only extraInfo field"
    )
    version = "1.0.0"
    github = "https://github.com/Jonny-Ponny/metadata-docker"
    required_env_vars = []

    def search_songs(self, query, limit=5):
        results = []
        for song_id, song in SONGS.items():
            result = {
                "id": song_id,
                "title": song["title"],
                "artist": song["artist"],
                "album": song["album"],
                "date": song.get("date", ""),
            }
            if song.get("extraInfo"):
                result["extraInfo"] = song["extraInfo"]
            results.append(result)
        return results[: _clamp_limit(limit)]

    def fetch_song_metadata(self, song_id):
        song = SONGS.get(song_id)
        if song is None:
            raise ValueError(f"Unknown mock song id: {song_id}")
        return dict(song)

    def search_albums(self, query, limit=5):
        results = []
        for album_id, album in ALBUMS.items():
            result = {
                "id": album_id,
                "title": album["title"],
                "artist": album["artist"],
                "date": album.get("date", ""),
            }
            if album.get("extraInfo"):
                result["extraInfo"] = album["extraInfo"]
            results.append(result)
        return results[: _clamp_limit(limit)]

    def fetch_album_metadata(self, album_id):
        tracks = ALBUM_TRACKS.get(album_id)
        if tracks is None:
            raise ValueError(f"Unknown mock album id: {album_id}")
        return [dict(track) for track in tracks]
