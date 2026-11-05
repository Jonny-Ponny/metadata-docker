"""File-tree sorting and concurrent-deletion handling (B-10, B-11)."""

import os

import library


def _find_node(items, name):
    for item in items:
        if item["name"] == name:
            return item
        found = _find_node(item.get("children") or [], name)
        if found:
            return found
    return None


def test_natural_key_handles_digits_int_rejects(app_module):
    # "²".isdigit() is True but int("²") raises ValueError.
    assert app_module.natural_key("²") == ["²"]
    assert app_module.natural_key("track²") == ["track²"]


def test_file_tree_sorts_naturally_and_lists_unicode_digits(
    client, auth_headers, test_dir
):
    for name in ("a10.mp3", "a2.mp3", "a².mp3"):
        (test_dir / name).write_bytes(b"audio")

    response = client.get("/api/files", headers=auth_headers)

    assert response.status_code == 200
    node = _find_node(response.get_json(), test_dir.name)
    assert [item["name"] for item in node["children"]] == [
        "a2.mp3",
        "a10.mp3",
        "a².mp3",
    ]


def test_file_tree_skips_a_file_that_disappears_mid_walk(
    client, auth_headers, test_dir, monkeypatch
):
    """A file deleted between listdir() and stat() is skipped (B-11).

    The walk lives in ``library``, so the race is installed on the module that
    actually runs it (``build_tree`` is re-exported by ``app`` for tests and
    older callers, which would not see the patch).
    """
    (test_dir / "keep.mp3").write_bytes(b"keep")
    (test_dir / "gone.mp3").write_bytes(b"gone")

    real_stat = library.os.stat

    def racing_stat(path, *args, **kwargs):
        if os.fspath(path).endswith("gone.mp3"):
            raise FileNotFoundError(path)
        return real_stat(path, *args, **kwargs)

    monkeypatch.setattr(library.os, "stat", racing_stat)

    response = client.get("/api/files", headers=auth_headers)

    assert response.status_code == 200
    node = _find_node(response.get_json(), test_dir.name)
    assert [item["name"] for item in node["children"]] == ["keep.mp3"]


def _by_path(items, path):
    """Find a node by its library-relative path (names are not unique)."""
    for item in items:
        if item["path"] == path:
            return item
        found = _by_path(item.get("children") or [], path)
        if found:
            return found
    return None


def test_file_tree_lists_a_folder_that_disappears_mid_walk_as_empty(
    client, auth_headers, test_dir, monkeypatch
):
    """A folder that disappears while being listed does not fail the request.

    ``os.listdir`` on a vanished folder yields no children (B-11), so the
    parent listing still returns 200 and the folder is simply empty until the
    next refresh.
    """
    (test_dir / "keep.mp3").write_bytes(b"keep")
    album = test_dir / "album"
    album.mkdir()
    (album / "track.mp3").write_bytes(b"audio")

    # Patch the module-level helper directly and restore it in ``finally``.
    # ``monkeypatch`` also works, but this test is order-sensitive on other
    # files (``library`` is process-wide), so the restore is explicit.
    real_listdir_names = library._listdir_names

    def vanished_children(path):
        if os.fspath(path) == str(album):
            return []
        return real_listdir_names(path)

    library._listdir_names = vanished_children
    try:
        response = client.get("/api/files", headers=auth_headers)
    finally:
        library._listdir_names = real_listdir_names

    assert response.status_code == 200
    tree = response.get_json()
    node = _find_node(tree, test_dir.name)
    assert [item["name"] for item in node["children"]] == ["album", "keep.mp3"]
    # Look the folder up by path: other tests leave folders with the same name
    # in the shared session library.
    album_path = f"{test_dir.name}/album"
    assert _by_path(tree, album_path)["children"] == []
