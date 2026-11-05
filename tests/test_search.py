"""Library-wide filename search (/api/files/search)."""

import os

import library


def _search(client, auth_headers, query, **params):
    return client.get(
        "/api/files/search",
        headers=auth_headers,
        query_string={"q": query, **params},
    )


def _paths(response):
    return sorted(hit["path"] for hit in response.get_json()["results"])


def test_search_finds_files_deep_in_the_library(
    client, auth_headers, test_dir, music_root
):
    album = test_dir / "Album"
    disc = album / "CD2"
    disc.mkdir(parents=True)
    # A unique marker: the test library is shared by the whole session.
    marker = f"deep-{test_dir.name}"
    (album / f"{marker}-one.flac").write_bytes(b"audio")
    (disc / f"{marker}-two.flac").write_bytes(b"audio")
    (album / "cover.jpg").write_bytes(b"image")

    response = _search(client, auth_headers, marker)

    assert response.status_code == 200
    assert response.get_json()["truncated"] is False
    found = _paths(response)
    assert f"{test_dir.name}/Album/{marker}-one.flac" in found
    assert f"{test_dir.name}/Album/CD2/{marker}-two.flac" in found
    assert len(found) == 2


def test_search_is_case_insensitive(
    client, auth_headers, test_dir, music_root
):
    (test_dir / f"MiXeD CaSe {test_dir.name}.mp3").write_bytes(b"audio")

    response = _search(client, auth_headers, f"mixed case {test_dir.name}")

    assert _paths(response) == [
        f"{test_dir.name}/MiXeD CaSe {test_dir.name}.mp3"
    ]


def test_search_returns_the_ancestor_chain(
    client, auth_headers, test_dir, music_root
):
    album = test_dir / "Parent"
    nested = album / "Child"
    nested.mkdir(parents=True)
    marker = f"wanted-{test_dir.name}"
    (nested / f"{marker}.mp3").write_bytes(b"audio")

    response = _search(client, auth_headers, marker)
    hit = next(
        hit
        for hit in response.get_json()["results"]
        if hit["path"].endswith(f"Parent/Child/{marker}.mp3")
    )

    assert hit["parents"] == [
        test_dir.name,
        f"{test_dir.name}/Parent",
        f"{test_dir.name}/Parent/Child",
    ]
    assert hit["type"] == "file"
    assert hit["file_type"] == "audio"


def test_search_finds_folders_too(
    client, auth_headers, test_dir, music_root
):
    folder_name = f"Matching Folder {test_dir.name}"
    target = test_dir / folder_name
    target.mkdir()
    (target / "song.mp3").write_bytes(b"audio")

    response = _search(client, auth_headers, folder_name.lower())

    assert response.status_code == 200
    hits = {hit["path"]: hit for hit in response.get_json()["results"]}
    hit = hits[f"{test_dir.name}/{folder_name}"]
    assert hit["type"] == "directory"
    assert hit["parents"] == [test_dir.name]


def test_search_caps_results_and_flags_the_cut(
    client, auth_headers, test_dir, music_root
):
    # A name other tests cannot collide with: the library is shared.
    marker = f"cap-probe-{test_dir.name}"
    for index in range(5):
        (test_dir / f"{marker}-{index}.mp3").write_bytes(b"audio")

    response = _search(client, auth_headers, marker, limit=3)
    body = response.get_json()

    assert body["truncated"] is True
    assert len(body["results"]) == 3

    complete = _search(client, auth_headers, marker, limit=5).get_json()
    assert complete["truncated"] is False
    assert len(complete["results"]) == 5


def test_search_limit_cannot_exceed_the_default(
    client, auth_headers, test_dir
):
    (test_dir / f"clamp-{test_dir.name}.mp3").write_bytes(b"audio")

    # A huge limit is clamped rather than trusted.
    response = _search(client, auth_headers, f"clamp-{test_dir.name}", limit=10**9)

    assert response.status_code == 200


def test_search_rejects_an_empty_query(client, auth_headers):
    response = _search(client, auth_headers, "   ")

    assert response.status_code == 400


def test_search_ignores_a_non_numeric_limit(
    client, auth_headers, test_dir, music_root
):
    """Flask's ``type=int`` falls back to the default for garbage input."""
    (test_dir / f"fallback-{test_dir.name}.mp3").write_bytes(b"audio")

    response = _search(client, auth_headers, f"fallback-{test_dir.name}", limit="abc")

    assert response.status_code == 200
    assert response.get_json()["results"]


def test_search_does_not_follow_symlinks(
    client, auth_headers, test_dir, music_root, tmp_path
):
    (test_dir / f"inside-{test_dir.name}.mp3").write_bytes(b"audio")
    marker = f"outside-secret-{test_dir.name}"
    outside = tmp_path / f"{marker}.mp3"
    outside.write_bytes(b"secret")
    os.symlink(outside, test_dir / f"{marker}.mp3")
    (test_dir / "linked-dir").symlink_to(tmp_path)

    response = _search(client, auth_headers, marker)

    assert _paths(response) == []


def test_search_skips_in_progress_uploads(
    client, auth_headers, test_dir, music_root
):
    marker = f"upload-probe-{test_dir.name}"
    (test_dir / f".upload-{marker}.part").write_bytes(b"partial")

    response = _search(client, auth_headers, marker)

    assert _paths(response) == []


def test_search_tree_stops_at_the_limit(music_root, test_dir):
    marker = f"limit-probe-{test_dir.name}"
    for index in range(4):
        (test_dir / f"{marker}-{index}.mp3").write_bytes(b"audio")

    results = library.search_tree(marker, music_root, limit=2)

    assert len(results) == 2
