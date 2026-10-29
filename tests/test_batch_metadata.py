"""POST /api/metadata/batch: set and delete several tags on chosen files."""

import os
from pathlib import Path

import pytest

import metadata_writer
from metadata_extractor import extract_metadata


FORMATS = [".mp3", ".flac", ".ogg", ".m4a"]


def _relative(path, music_root):
    return Path(path).relative_to(music_root).as_posix()


def _batch(client, headers, body):
    return client.post("/api/metadata/batch", headers=headers, json=body)


@pytest.mark.parametrize("extension", FORMATS)
def test_batch_sets_several_fields_on_every_file(
    client, auth_headers, audio_file, music_root, extension
):
    first = audio_file(extension)
    second = audio_file(extension)

    response = _batch(client, auth_headers, {
        "paths": [_relative(first, music_root), _relative(second, music_root)],
        "set": {
            "artist": "Bulk Artist",
            "album": "Bulk Album",
            "diskNumber": "1/2",
        },
    })

    assert response.status_code == 200, response.data
    body = response.get_json()
    assert body["success"] is True
    assert body["total"] == 2
    assert body["updated"] == 2
    assert body["failed"] == 0
    assert body["failed_files"] == []
    for song in (first, second):
        tags = extract_metadata(str(song))
        assert tags["artist"] == "Bulk Artist"
        assert tags["album"] == "Bulk Album"
        assert tags["diskNumber"] == "1/2"


def test_batch_saves_each_file_once(
    client, auth_headers, audio_file, music_root, monkeypatch
):
    song = audio_file(".flac")
    saves = []
    original = metadata_writer._backend_for_audio

    def counting_backend(file_path, audio):
        backend = original(file_path, audio)
        save = backend.save

        def counted(audio_obj):
            saves.append(file_path)
            return save(audio_obj)

        backend.save = counted
        return backend

    monkeypatch.setattr(metadata_writer, "_backend_for_audio", counting_backend)

    response = _batch(client, auth_headers, {
        "paths": [_relative(song, music_root)],
        "set": {"artist": "A", "album": "B", "genre": "C"},
    })

    assert response.status_code == 200, response.data
    assert saves == [str(song)]


def test_batch_deletes_fields_and_keeps_untouched_ones(
    client, auth_headers, audio_file, music_root
):
    song = audio_file(".mp3")
    metadata_writer.update_file_metadata(str(song), "genre", "Rock")
    metadata_writer.update_file_metadata(str(song), "title", "Keep me")

    response = _batch(client, auth_headers, {
        "paths": [_relative(song, music_root)],
        "set": {"artist": "New"},
        "delete": ["genre"],
    })

    assert response.status_code == 200, response.data
    tags = extract_metadata(str(song))
    assert tags["artist"] == "New"
    assert tags["genre"] == ""
    assert tags["title"] == "Keep me"


def test_batch_reports_missing_files_and_updates_the_rest(
    client, auth_headers, audio_file, music_root, test_dir
):
    song = audio_file(".mp3")
    missing = _relative(test_dir / "missing.mp3", music_root)
    notes = test_dir / "notes.txt"
    notes.write_text("hello")

    response = _batch(client, auth_headers, {
        "paths": [
            _relative(song, music_root),
            missing,
            _relative(notes, music_root),
        ],
        "set": {"artist": "Survivor"},
    })

    assert response.status_code == 200, response.data
    body = response.get_json()
    assert body["total"] == 3
    assert body["updated"] == 1
    assert body["failed"] == 2
    assert body["failed_files"] == [missing, _relative(notes, music_root)]
    assert extract_metadata(str(song))["artist"] == "Survivor"


def test_batch_failed_files_are_library_relative(
    client, auth_headers, music_root, test_dir
):
    corrupt = test_dir / "corrupt.mp3"
    corrupt.write_bytes(b"not real audio")

    response = _batch(client, auth_headers, {
        "paths": ["/" + _relative(corrupt, music_root)],
        "set": {"artist": "X"},
    })

    assert response.status_code == 200, response.data
    body = response.get_json()
    assert body["failed_files"] == [_relative(corrupt, music_root)]
    assert str(music_root) not in response.get_data(as_text=True)


def test_batch_rejects_whole_request_when_a_path_escapes(
    client, auth_headers, audio_file, music_root
):
    song = audio_file(".mp3")

    response = _batch(client, auth_headers, {
        "paths": [_relative(song, music_root), "../outside.mp3"],
        "set": {"artist": "Nope"},
    })

    assert response.status_code == 403
    assert "error" in response.get_json()
    assert extract_metadata(str(song))["artist"] == ""


def test_batch_refuses_symlink_pointing_outside_the_library(
    client, auth_headers, audio_file, music_root, test_dir, tmp_path
):
    song = audio_file(".mp3")
    outside = tmp_path / "outside.mp3"
    outside.write_bytes(song.read_bytes())
    link = test_dir / "link.mp3"
    os.symlink(outside, link)

    response = _batch(client, auth_headers, {
        "paths": [_relative(song, music_root), _relative(link, music_root)],
        "set": {"artist": "Nope"},
    })

    assert response.status_code == 403
    assert extract_metadata(str(outside))["artist"] == ""
    assert extract_metadata(str(song))["artist"] == ""


@pytest.mark.parametrize("body, message", [
    ({"set": {"artist": "A"}}, "paths"),
    ({"paths": [], "set": {"artist": "A"}}, "paths"),
    ({"paths": "song.mp3", "set": {"artist": "A"}}, "paths"),
    ({"paths": [1], "set": {"artist": "A"}}, "paths"),
    ({"paths": ["song.mp3"]}, "Nothing to change"),
    ({"paths": ["song.mp3"], "set": {}, "delete": []}, "Nothing to change"),
    ({"paths": ["song.mp3"], "set": ["artist"]}, "set"),
    ({"paths": ["song.mp3"], "delete": "genre"}, "delete"),
    ({"paths": ["song.mp3"], "set": {"title": "T"}}, "title"),
    ({"paths": ["song.mp3"], "set": {"lyrics": "L"}}, "lyrics"),
    ({"paths": ["song.mp3"], "delete": ["trackNumber"]}, "trackNumber"),
    ({"paths": ["song.mp3"], "set": {"bogus": "x"}}, "bogus"),
    ({"paths": ["song.mp3"], "set": {"artist": 3}}, "artist"),
    ({"paths": ["song.mp3"], "set": {"artist": "A"}, "delete": ["artist"]},
     "artist"),
    ({"paths": ["song.mp3"], "set": {"diskNumber": "one"}}, "diskNumber"),
    ({"paths": ["song.mp3"], "set": {"diskNumber": "1/"}}, "diskNumber"),
])
def test_batch_rejects_bad_input(client, auth_headers, body, message):
    response = _batch(client, auth_headers, body)

    assert response.status_code == 400
    assert message in response.get_json()["error"]


def test_batch_rejects_too_many_paths(client, auth_headers):
    response = _batch(client, auth_headers, {
        "paths": [f"song-{i}.mp3" for i in range(501)],
        "set": {"artist": "A"},
    })

    assert response.status_code == 400
    assert "500" in response.get_json()["error"]


def test_batch_rejects_non_object_body(client, auth_headers):
    response = client.post(
        "/api/metadata/batch", headers=auth_headers, json=["not", "object"]
    )

    assert response.status_code == 400
    assert "error" in response.get_json()


def test_batch_bad_input_leaves_files_untouched(
    client, auth_headers, audio_file, music_root
):
    song = audio_file(".mp3")

    response = _batch(client, auth_headers, {
        "paths": [_relative(song, music_root)],
        "set": {"artist": "A", "diskNumber": "x"},
    })

    assert response.status_code == 400
    assert extract_metadata(str(song))["artist"] == ""


def test_batch_requires_a_token(client, audio_file, music_root):
    song = audio_file(".mp3")

    response = client.post("/api/metadata/batch", json={
        "paths": [_relative(song, music_root)],
        "set": {"artist": "A"},
    })

    assert response.status_code == 401
    assert extract_metadata(str(song))["artist"] == ""
