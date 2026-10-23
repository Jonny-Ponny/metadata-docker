"""Metadata and cover endpoints must return clear errors (B-12, B-13, B-14, B-15, B-17, B-18)."""

import io
from pathlib import Path

import pytest

import metadata_writer


def _relative(path, music_root):
    return Path(path).relative_to(music_root).as_posix()


def _make_audio(test_dir, name="song.mp3"):
    song = test_dir / name
    song.write_bytes(b"not real audio")
    return song


def test_delete_field_from_a_missing_path_returns_404(
    client, auth_headers, test_dir, music_root
):
    for name in ("missing.mp3", "missing-folder"):
        response = client.post(
            "/api/metadata/field/delete",
            headers=auth_headers,
            json={
                "path": _relative(test_dir / name, music_root),
                "field": "title",
            },
        )

        assert response.status_code == 404, name
        assert "not found" in response.get_json()["error"].lower()


def test_smart_rename_rejects_unreadable_metadata_for_a_file(
    client, auth_headers, test_dir, music_root, app_module, monkeypatch
):
    song = _make_audio(test_dir)
    monkeypatch.setattr(app_module, "extract_metadata", lambda *a, **k: None)

    response = client.post(
        "/api/apply-renaming-scheme",
        headers=auth_headers,
        json={
            "path": _relative(song, music_root),
            "scheme": "[TITLE]",
            "isFolder": False,
        },
    )

    assert response.status_code == 400
    assert "metadata" in response.get_json()["error"].lower()


def test_smart_rename_rejects_unreadable_metadata_for_a_folder(
    client, auth_headers, test_dir, music_root, app_module, monkeypatch
):
    album = test_dir / "album"
    album.mkdir()
    _make_audio(album)
    monkeypatch.setattr(app_module, "extract_metadata", lambda *a, **k: None)

    response = client.post(
        "/api/apply-renaming-scheme",
        headers=auth_headers,
        json={
            "path": _relative(album, music_root),
            "scheme": "[TITLE]",
            "isFolder": True,
        },
    )

    assert response.status_code == 400
    assert "metadata" in response.get_json()["error"].lower()


@pytest.mark.parametrize("scheme", [123, ["TITLE"], {"TITLE": 1}])
def test_smart_rename_rejects_a_non_string_scheme(
    client, auth_headers, test_dir, music_root, scheme
):
    song = _make_audio(test_dir)

    response = client.post(
        "/api/apply-renaming-scheme",
        headers=auth_headers,
        json={"path": _relative(song, music_root), "scheme": scheme},
    )

    assert response.status_code == 400
    assert response.is_json


def test_cover_upload_can_reread_missing_metadata(
    client, auth_headers, test_dir, music_root, app_module, monkeypatch
):
    song = _make_audio(test_dir)
    monkeypatch.setattr(app_module, "update_file_picture", lambda *a, **k: True)
    monkeypatch.setattr(app_module, "extract_metadata", lambda *a, **k: None)

    response = client.post(
        "/api/metadata/picture/file",
        headers=auth_headers,
        data={
            "file": (io.BytesIO(b"image-bytes"), "cover.jpg"),
            "path": _relative(song, music_root),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    assert response.get_json()["picture"] is None


def test_cover_from_url_can_reread_missing_metadata(
    client, auth_headers, test_dir, music_root, app_module, monkeypatch
):
    song = _make_audio(test_dir)
    monkeypatch.setattr(
        app_module, "fetch_image", lambda *a, **k: (b"image-bytes", "image/jpeg")
    )
    monkeypatch.setattr(app_module, "update_file_picture", lambda *a, **k: True)
    monkeypatch.setattr(app_module, "extract_metadata", lambda *a, **k: None)

    response = client.post(
        "/api/metadata/picture/url",
        headers=auth_headers,
        json={"url": "https://example.com/cover.jpg", "path": _relative(song, music_root)},
    )

    assert response.status_code == 200
    assert response.get_json()["picture"] is None


def test_delete_cover_can_reread_missing_metadata(
    client, auth_headers, test_dir, music_root, app_module, monkeypatch
):
    song = _make_audio(test_dir)
    monkeypatch.setattr(metadata_writer, "delete_cover_art", lambda *a, **k: True)
    monkeypatch.setattr(app_module, "extract_metadata", lambda *a, **k: None)

    response = client.post(
        "/api/metadata/picture/delete",
        headers=auth_headers,
        json={"path": _relative(song, music_root)},
    )

    assert response.status_code == 200
    assert response.get_json()["picture"] is None


def test_cover_from_url_checks_the_format_before_fetching(
    client, auth_headers, test_dir, music_root, app_module, monkeypatch
):
    notes = test_dir / "notes.txt"
    notes.write_bytes(b"text")
    calls = []
    monkeypatch.setattr(
        app_module, "fetch_image", lambda *a, **k: calls.append(a) or (b"", "image/jpeg")
    )

    response = client.post(
        "/api/metadata/picture/url",
        headers=auth_headers,
        json={
            "url": "https://example.com/cover.jpg",
            "path": _relative(notes, music_root),
        },
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "Unsupported file format"
    assert calls == []


def test_root_folder_cover_uses_the_resolved_library_root(
    client, auth_headers, app_module, monkeypatch, tmp_path
):
    """A relative library root must not break the root folder routes (B-16)."""
    (tmp_path / "relative-music").mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(app_module, "MUSIC_ROOT", "relative-music")
    monkeypatch.setattr(
        app_module,
        "update_folder_pictures",
        lambda *a, **k: {"updated": 0, "failed": 0, "total": 0},
    )

    response = client.post(
        "/api/metadata/picture/folder",
        headers=auth_headers,
        data={
            "file": (io.BytesIO(b"image-bytes"), "cover.jpg"),
            "path": "",
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 200


def test_save_cover_as_file_rejects_corrupt_base64(
    client, auth_headers, test_dir, music_root, app_module, monkeypatch
):
    song = _make_audio(test_dir)
    monkeypatch.setattr(
        app_module,
        "extract_metadata",
        lambda *a, **k: {"picture": "data:image/jpeg;base64,a"},
    )

    response = client.post(
        "/api/metadata/picture/save-as-file",
        headers=auth_headers,
        json={"path": _relative(song, music_root)},
    )

    assert response.status_code == 400
    assert "base64" in response.get_json()["error"].lower()


def test_save_cover_as_file_handles_missing_metadata(
    client, auth_headers, test_dir, music_root, app_module, monkeypatch
):
    song = _make_audio(test_dir)
    monkeypatch.setattr(app_module, "extract_metadata", lambda *a, **k: None)

    response = client.post(
        "/api/metadata/picture/save-as-file",
        headers=auth_headers,
        json={"path": _relative(song, music_root)},
    )

    assert response.status_code == 404
    assert "cover" in response.get_json()["error"].lower()


def test_image_endpoint_only_serves_images(client, auth_headers, test_dir, music_root):
    audio = _make_audio(test_dir)
    image = test_dir / "cover.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n")

    response = client.get(
        "/api/image",
        headers=auth_headers,
        query_string={"path": _relative(audio, music_root)},
    )
    assert response.status_code == 400
    assert response.get_json()["error"] == "Not an image file"

    response = client.get(
        "/api/image",
        headers=auth_headers,
        query_string={"path": _relative(image, music_root)},
    )
    assert response.status_code == 200
    assert response.mimetype == "image/png"


def test_audio_endpoint_only_serves_audio(client, auth_headers, test_dir, music_root):
    notes = test_dir / "notes.txt"
    notes.write_bytes(b"text")
    audio = _make_audio(test_dir)

    response = client.get(
        "/api/audio",
        headers=auth_headers,
        query_string={"path": _relative(notes, music_root)},
    )
    assert response.status_code == 400
    assert response.get_json()["error"] == "Not an audio file"

    response = client.get(
        "/api/audio",
        headers=auth_headers,
        query_string={"path": _relative(audio, music_root)},
    )
    assert response.status_code == 200
