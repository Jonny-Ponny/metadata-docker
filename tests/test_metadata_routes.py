"""Authenticated success and failure cases for the metadata routes."""

import base64
import io
from pathlib import Path

import pytest

from metadata_extractor import extract_metadata


JPEG = b"\xff\xd8\xff\xe0" + b"jpeg-cover"
PNG = b"\x89PNG\r\n\x1a\n" + b"png-cover"


def _relative(path, music_root):
    return Path(path).relative_to(music_root).as_posix()


def _metadata(client, headers, path, music_root, **params):
    return client.get(
        "/api/metadata",
        headers=headers,
        query_string={"path": _relative(path, music_root), **params},
    )


def test_validate_reports_a_valid_session(client, auth_headers):
    response = client.get("/api/validate", headers=auth_headers)

    assert response.status_code == 200
    assert response.get_json() == {"valid": True}


def test_get_metadata_reads_a_track(
    client, auth_headers, audio_file, music_root
):
    song = audio_file(".mp3", name="song.mp3")

    response = _metadata(client, auth_headers, song, music_root)

    assert response.status_code == 200
    body = response.get_json()
    assert body["title"] == ""
    assert isinstance(body["customFields"], list)
    assert "picture" not in body


def test_get_metadata_marks_unsupported_files_read_only(
    client, auth_headers, write_library_file, music_root
):
    notes = write_library_file("notes.pdf", b"%PDF-1.4")

    response = _metadata(client, auth_headers, notes, music_root)

    assert response.status_code == 200
    body = response.get_json()
    assert body["readOnly"] is True
    assert body["supported"] is False
    assert body["format"] == "PDF"


def test_get_metadata_missing_file_is_404(client, auth_headers, music_root):
    response = client.get(
        "/api/metadata",
        headers=auth_headers,
        query_string={"path": "missing.mp3"},
    )

    assert response.status_code == 404


def test_get_metadata_reports_a_clear_error_for_corrupt_audio(
    client, auth_headers, write_library_file, music_root
):
    corrupt = write_library_file("corrupt.mp3", b"not real audio")

    response = _metadata(client, auth_headers, corrupt, music_root)

    assert response.status_code == 500
    assert response.get_json()["error"] == (
        "Could not read metadata (unsupported format?)"
    )


def test_get_metadata_requires_a_path(client, auth_headers):
    response = client.get("/api/metadata", headers=auth_headers)

    assert response.status_code == 400


def test_update_single_file_writes_the_tag(
    client, auth_headers, audio_file, music_root
):
    song = audio_file(".flac", name="song.flac")

    response = client.post(
        "/api/metadata/file",
        headers=auth_headers,
        json={
            "path": _relative(song, music_root),
            "field": "title",
            "value": "A Title",
        },
    )

    assert response.status_code == 200
    assert response.get_json()["success"] is True
    assert extract_metadata(song)["title"] == "A Title"


def test_update_single_file_rejects_missing_and_unsupported_paths(
    client, auth_headers, write_library_file, music_root
):
    notes = write_library_file("notes.txt", b"text")

    missing = client.post(
        "/api/metadata/file",
        headers=auth_headers,
        json={"path": "missing.mp3", "field": "title", "value": "x"},
    )
    unsupported = client.post(
        "/api/metadata/file",
        headers=auth_headers,
        json={
            "path": _relative(notes, music_root),
            "field": "title",
            "value": "x",
        },
    )

    assert missing.status_code == 404
    assert unsupported.status_code == 400
    assert unsupported.get_json()["error"] == "Unsupported file format"


def test_update_folder_is_recursive(
    client, auth_headers, audio_file, test_dir, music_root
):
    top = audio_file(".mp3", name="top.mp3")
    nested = audio_file(".flac", name="sub/nested.flac")

    response = client.post(
        "/api/metadata/folder",
        headers=auth_headers,
        json={
            "path": _relative(test_dir, music_root),
            "field": "genre",
            "value": "Ambient",
        },
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["updated"] == 2
    assert body["failed"] == 0
    assert body["total"] == 2
    assert extract_metadata(top)["genre"] == "Ambient"
    assert extract_metadata(nested)["genre"] == "Ambient"


def test_update_folder_current_only_skips_subfolders(
    client, auth_headers, audio_file, test_dir, music_root
):
    top = audio_file(".mp3", name="top.mp3")
    nested = audio_file(".flac", name="sub/nested.flac")

    response = client.post(
        "/api/metadata/folder/current",
        headers=auth_headers,
        json={
            "path": _relative(test_dir, music_root),
            "field": "genre",
            "value": "Current",
        },
    )

    assert response.status_code == 200
    assert response.get_json()["updated"] == 1
    assert extract_metadata(top)["genre"] == "Current"
    assert extract_metadata(nested)["genre"] == ""


def test_update_folder_missing_is_404(client, auth_headers, music_root):
    response = client.post(
        "/api/metadata/folder",
        headers=auth_headers,
        json={"path": "missing", "field": "title", "value": "x"},
    )

    assert response.status_code == 404


def _upload_cover(client, headers, path, image=JPEG, name="cover.jpg"):
    return client.post(
        "/api/metadata/picture/file",
        headers=headers,
        data={
            "file": (io.BytesIO(image), name),
            "path": path,
        },
        content_type="multipart/form-data",
    )


def test_upload_cover_stores_the_picture(
    client, auth_headers, audio_file, music_root
):
    song = audio_file(".mp3", name="song.mp3")

    response = _upload_cover(client, auth_headers, _relative(song, music_root))

    assert response.status_code == 200
    body = response.get_json()
    assert body["success"] is True
    assert body["picture"].startswith("data:image/jpeg;base64,")
    assert extract_metadata(song)["picture"].startswith("data:image/jpeg;base64,")


def test_get_metadata_can_skip_the_picture(
    client, auth_headers, audio_file, music_root
):
    song = audio_file(".mp3", name="song.mp3")
    assert _upload_cover(
        client, auth_headers, _relative(song, music_root)
    ).status_code == 200

    response = _metadata(
        client, auth_headers, song, music_root, includePicture="false"
    )

    assert response.status_code == 200
    body = response.get_json()
    assert "picture" not in body
    assert "picture" in extract_metadata(song)


def test_upload_cover_from_url_uses_the_fetched_image(
    client, auth_headers, audio_file, music_root, tags_module, monkeypatch
):
    song = audio_file(".flac", name="song.flac")
    fetched = []

    def fake_fetch(url, user_agent, **kwargs):
        fetched.append(url)
        return PNG, "image/png"

    monkeypatch.setattr(tags_module, "fetch_image", fake_fetch)

    response = client.post(
        "/api/metadata/picture/url",
        headers=auth_headers,
        json={
            "url": "https://example.com/cover.png",
            "path": _relative(song, music_root),
        },
    )

    assert response.status_code == 200
    assert fetched == ["https://example.com/cover.png"]
    assert response.get_json()["picture"].startswith("data:image/png;base64,")
    assert extract_metadata(song)["picture"].startswith("data:image/png;base64,")


def test_upload_cover_from_an_unsafe_url_is_rejected(
    client, auth_headers, audio_file, music_root, tags_module, monkeypatch
):
    song = audio_file(".mp3", name="song.mp3")

    def unsafe(url, user_agent, **kwargs):
        raise tags_module.UnsafeURLError("URL is not public")

    monkeypatch.setattr(tags_module, "fetch_image", unsafe)

    response = client.post(
        "/api/metadata/picture/url",
        headers=auth_headers,
        json={"url": "http://127.0.0.1/secret", "path": _relative(song, music_root)},
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "URL is not public"


def test_preview_proxies_a_remote_picture(client, auth_headers, tags_module, monkeypatch):
    monkeypatch.setattr(
        tags_module,
        "fetch_image",
        lambda url, user_agent, **kwargs: (PNG, "image/png"),
    )

    response = client.get(
        "/api/metadata/picture/preview",
        headers=auth_headers,
        query_string={"url": "https://example.com/cover.png"},
    )

    assert response.status_code == 200
    assert response.data == PNG
    assert response.mimetype == "image/png"
    assert response.headers["Cache-Control"] == "private, max-age=300"


def test_preview_rejects_an_unsafe_url(
    client, auth_headers, tags_module, monkeypatch
):
    def unsafe(url, user_agent, **kwargs):
        raise tags_module.UnsafeURLError("URL is not public")

    monkeypatch.setattr(tags_module, "fetch_image", unsafe)

    response = client.get(
        "/api/metadata/picture/preview",
        headers=auth_headers,
        query_string={"url": "http://127.0.0.1/secret"},
    )

    assert response.status_code == 400


def _upload_folder_cover(client, headers, path, image=JPEG):
    return client.post(
        "/api/metadata/picture/folder",
        headers=headers,
        data={
            "file": (io.BytesIO(image), "cover.jpg"),
            "path": path,
        },
        content_type="multipart/form-data",
    )


def test_folder_cover_updates_every_track(
    client, auth_headers, audio_file, test_dir, music_root
):
    top = audio_file(".mp3", name="top.mp3")
    nested = audio_file(".flac", name="sub/nested.flac")

    response = _upload_folder_cover(
        client, auth_headers, _relative(test_dir, music_root)
    )

    assert response.status_code == 200
    body = response.get_json()
    assert (body["updated"], body["failed"], body["total"]) == (2, 0, 2)
    assert extract_metadata(top)["picture"]
    assert extract_metadata(nested)["picture"]


def test_folder_cover_current_only_skips_subfolders(
    client, auth_headers, audio_file, test_dir, music_root
):
    top = audio_file(".mp3", name="top.mp3")
    nested = audio_file(".flac", name="sub/nested.flac")

    response = client.post(
        "/api/metadata/picture/folder/current",
        headers=auth_headers,
        data={
            "file": (io.BytesIO(JPEG), "cover.jpg"),
            "path": _relative(test_dir, music_root),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    assert response.get_json()["updated"] == 1
    assert extract_metadata(top)["picture"]
    assert "picture" not in extract_metadata(nested)


def test_folder_cover_missing_folder_is_404(
    client, auth_headers, music_root
):
    response = _upload_folder_cover(client, auth_headers, "missing")

    assert response.status_code == 404


def test_folder_cover_from_url_downloads_the_image_once(
    client, auth_headers, audio_file, test_dir, music_root, tags_module, monkeypatch
):
    top = audio_file(".mp3", name="top.mp3")
    nested = audio_file(".flac", name="sub/nested.flac")
    fetched = []

    def fake_fetch(url, user_agent, **kwargs):
        fetched.append(url)
        return PNG, "image/png"

    monkeypatch.setattr(tags_module, "fetch_image", fake_fetch)

    response = client.post(
        "/api/metadata/picture/url/folder",
        headers=auth_headers,
        json={
            "url": "https://example.com/cover.png",
            "path": _relative(test_dir, music_root),
        },
    )

    assert response.status_code == 200
    body = response.get_json()
    assert (body["updated"], body["failed"], body["total"]) == (2, 0, 2)
    assert fetched == ["https://example.com/cover.png"]
    assert extract_metadata(top)["picture"].startswith("data:image/png;base64,")
    assert extract_metadata(nested)["picture"].startswith("data:image/png;base64,")


def test_folder_cover_from_url_current_only_skips_subfolders(
    client, auth_headers, audio_file, test_dir, music_root, tags_module, monkeypatch
):
    top = audio_file(".mp3", name="top.mp3")
    nested = audio_file(".flac", name="sub/nested.flac")
    monkeypatch.setattr(
        tags_module,
        "fetch_image",
        lambda url, user_agent, **kwargs: (JPEG, "image/jpeg"),
    )

    response = client.post(
        "/api/metadata/picture/url/folder/current",
        headers=auth_headers,
        json={
            "url": "https://example.com/cover.jpg",
            "path": _relative(test_dir, music_root),
        },
    )

    assert response.status_code == 200
    assert response.get_json()["updated"] == 1
    assert extract_metadata(top)["picture"]
    assert "picture" not in extract_metadata(nested)


def test_folder_cover_from_url_rejects_an_unsafe_url(
    client, auth_headers, test_dir, music_root, tags_module, monkeypatch
):
    def unsafe(url, user_agent, **kwargs):
        raise tags_module.UnsafeURLError("URL is not public")

    monkeypatch.setattr(tags_module, "fetch_image", unsafe)

    response = client.post(
        "/api/metadata/picture/url/folder",
        headers=auth_headers,
        json={
            "url": "http://127.0.0.1/secret",
            "path": _relative(test_dir, music_root),
        },
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "URL is not public"


def test_folder_cover_from_url_rejects_an_oversized_image(
    client, auth_headers, test_dir, music_root, tags_module, monkeypatch
):
    def too_large(url, user_agent, **kwargs):
        raise tags_module.ImageTooLargeError("Image is too large")

    monkeypatch.setattr(tags_module, "fetch_image", too_large)

    response = client.post(
        "/api/metadata/picture/url/folder",
        headers=auth_headers,
        json={
            "url": "https://example.com/huge.png",
            "path": _relative(test_dir, music_root),
        },
    )

    assert response.status_code == 413


@pytest.mark.parametrize(
    "body",
    [
        {"path": ""},
        {"url": "https://example.com/cover.png"},
    ],
    ids=["missing-url", "missing-path"],
)
def test_folder_cover_from_url_requires_url_and_path(
    client, auth_headers, body
):
    response = client.post(
        "/api/metadata/picture/url/folder", headers=auth_headers, json=body
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "Missing url or path parameter"


def test_folder_cover_from_url_missing_folder_is_404(
    client, auth_headers, music_root
):
    response = client.post(
        "/api/metadata/picture/url/folder",
        headers=auth_headers,
        json={"url": "https://example.com/cover.png", "path": "missing"},
    )

    assert response.status_code == 404


def test_delete_field_route_clears_a_tag(
    client, auth_headers, audio_file, music_root
):
    song = audio_file(".mp3", name="song.mp3")
    assert extract_metadata(song)["composer"] == ""
    client.post(
        "/api/metadata/file",
        headers=auth_headers,
        json={
            "path": _relative(song, music_root),
            "field": "composer",
            "value": "Composer",
        },
    )

    response = client.post(
        "/api/metadata/field/delete",
        headers=auth_headers,
        json={"path": _relative(song, music_root), "field": "composer"},
    )

    assert response.status_code == 200
    assert extract_metadata(song)["composer"] == ""


def test_custom_field_deletion_is_case_insensitive(
    client, auth_headers, audio_file, music_root
):
    song = audio_file(".mp3", name="song.mp3")
    response = client.post(
        "/api/metadata/file",
        headers=auth_headers,
        json={
            "path": _relative(song, music_root),
            "field": "Release Type",
            "value": "Single",
        },
    )
    assert response.status_code == 200
    assert {"name": "Release Type", "value": "Single"} in extract_metadata(
        song
    )["customFields"]

    response = client.post(
        "/api/metadata/field/delete",
        headers=auth_headers,
        json={"path": _relative(song, music_root), "field": "release_type"},
    )

    assert response.status_code == 200
    assert "Release Type" not in {
        entry["name"] for entry in extract_metadata(song)["customFields"]
    }


def test_delete_field_from_a_folder_is_recursive(
    client, auth_headers, audio_file, test_dir, music_root
):
    from metadata_writer import update_file_metadata

    album = test_dir / "album"
    top = audio_file(".mp3", name="album/top.mp3")
    nested = audio_file(".mp3", name="album/nested/inner.mp3")
    for track in (top, nested):
        assert update_file_metadata(str(track), "composer", "Composer")

    response = client.post(
        "/api/metadata/field/delete",
        headers=auth_headers,
        json={
            "path": _relative(album, music_root),
            "field": "composer",
            "recursive": True,
        },
    )

    assert response.status_code == 200
    body = response.get_json()
    assert (body["total"], body["updated"], body["failed"]) == (2, 2, 0)
    assert extract_metadata(top)["composer"] == ""
    assert extract_metadata(nested)["composer"] == ""


def test_delete_field_from_a_folder_current_only_skips_subfolders(
    client, auth_headers, audio_file, test_dir, music_root
):
    from metadata_writer import update_file_metadata

    album = test_dir / "album"
    top = audio_file(".mp3", name="album/top.mp3")
    nested = audio_file(".mp3", name="album/nested/inner.mp3")
    for track in (top, nested):
        assert update_file_metadata(str(track), "composer", "Composer")

    response = client.post(
        "/api/metadata/field/delete",
        headers=auth_headers,
        json={"path": _relative(album, music_root), "field": "composer"},
    )

    assert response.status_code == 200
    body = response.get_json()
    assert (body["total"], body["updated"]) == (1, 1)
    assert extract_metadata(top)["composer"] == ""
    assert extract_metadata(nested)["composer"] == "Composer"


def test_delete_cover_route_clears_the_picture(
    client, auth_headers, audio_file, music_root
):
    song = audio_file(".mp3", name="song.mp3")
    assert _upload_cover(client, auth_headers, _relative(song, music_root)).status_code == 200

    response = client.post(
        "/api/metadata/picture/delete",
        headers=auth_headers,
        json={"path": _relative(song, music_root)},
    )

    assert response.status_code == 200
    assert response.get_json()["picture"] is None
    assert "picture" not in extract_metadata(song)


def test_save_cover_as_file_writes_cover_jpg(
    client, auth_headers, audio_file, test_dir, music_root
):
    song = audio_file(".mp3", name="song.mp3")
    assert _upload_cover(client, auth_headers, _relative(song, music_root)).status_code == 200

    response = client.post(
        "/api/metadata/picture/save-as-file",
        headers=auth_headers,
        json={"path": _relative(song, music_root)},
    )

    assert response.status_code == 200
    cover = test_dir / "cover.jpg"
    assert cover.read_bytes() == JPEG
    assert response.get_json()["path"].endswith("cover.jpg")


def test_save_cover_as_file_uses_the_png_extension(
    client, auth_headers, audio_file, test_dir, music_root
):
    song = audio_file(".flac", name="song.flac")
    assert _upload_cover(
        client, auth_headers, _relative(song, music_root), image=PNG, name="cover.png"
    ).status_code == 200

    response = client.post(
        "/api/metadata/picture/save-as-file",
        headers=auth_headers,
        json={"path": _relative(song, music_root)},
    )

    assert response.status_code == 200
    cover = test_dir / "cover.png"
    assert cover.read_bytes() == PNG
    assert response.get_json()["path"].endswith("cover.png")


def test_save_cover_as_file_accepts_raw_base64(
    client, auth_headers, audio_file, test_dir, music_root, tags_module, monkeypatch
):
    song = audio_file(".mp3", name="song.mp3")
    monkeypatch.setattr(
        tags_module,
        "extract_metadata",
        lambda *args, **kwargs: {
            "picture": base64.b64encode(JPEG).decode("ascii")
        },
    )

    response = client.post(
        "/api/metadata/picture/save-as-file",
        headers=auth_headers,
        json={"path": _relative(song, music_root)},
    )

    assert response.status_code == 200
    assert (test_dir / "cover.jpg").read_bytes() == JPEG


def test_save_cover_as_file_does_not_overwrite_an_existing_cover(
    client, auth_headers, audio_file, test_dir, music_root
):
    song = audio_file(".mp3", name="song.mp3")
    assert _upload_cover(
        client, auth_headers, _relative(song, music_root)
    ).status_code == 200
    (test_dir / "cover.jpg").write_bytes(b"existing")

    response = client.post(
        "/api/metadata/picture/save-as-file",
        headers=auth_headers,
        json={"path": _relative(song, music_root)},
    )

    assert response.status_code == 200
    assert (test_dir / "cover.jpg").read_bytes() == b"existing"
    assert (test_dir / "cover (1).jpg").read_bytes() == JPEG


def test_text_save_writes_the_new_content(
    client, auth_headers, write_library_file, music_root
):
    lyrics = write_library_file("song.lrc", b"old")

    response = client.post(
        "/api/text/save",
        headers=auth_headers,
        json={
            "path": _relative(lyrics, music_root),
            "content": "[00:01.00] new",
        },
    )

    assert response.status_code == 200
    assert lyrics.read_text() == "[00:01.00] new"


@pytest.mark.parametrize("missing_field", ["path", "field"])
def test_metadata_file_requires_path_and_field(
    client, auth_headers, audio_file, music_root, missing_field
):
    song = audio_file(".mp3")
    payload = {
        "path": _relative(song, music_root),
        "field": "title",
        "value": "x",
    }
    payload.pop(missing_field)

    response = client.post(
        "/api/metadata/file", headers=auth_headers, json=payload
    )

    assert response.status_code == 400
    assert response.is_json
