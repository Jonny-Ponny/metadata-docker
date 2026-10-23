"""File-tree sorting and concurrent-deletion handling (B-10, B-11)."""

import os


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
    client, auth_headers, test_dir, app_module, monkeypatch
):
    (test_dir / "keep.mp3").write_bytes(b"keep")
    (test_dir / "gone.mp3").write_bytes(b"gone")

    real_stat = app_module.os.stat
    calls = []

    def racing_stat(path, *args, **kwargs):
        if os.fspath(path).endswith("gone.mp3"):
            calls.append(path)
            # isdir() and isfile() succeed; the entry vanishes before the
            # metadata stat.
            if len(calls) > 2:
                raise FileNotFoundError(path)
        return real_stat(path, *args, **kwargs)

    monkeypatch.setattr(app_module.os, "stat", racing_stat)

    response = client.get("/api/files", headers=auth_headers)

    assert response.status_code == 200
    node = _find_node(response.get_json(), test_dir.name)
    assert [item["name"] for item in node["children"]] == ["keep.mp3"]


def test_file_tree_skips_a_folder_that_disappears_mid_walk(
    client, auth_headers, test_dir, app_module, monkeypatch
):
    (test_dir / "keep.mp3").write_bytes(b"keep")
    album = test_dir / "album"
    album.mkdir()
    (album / "track.mp3").write_bytes(b"audio")

    real_listdir = app_module.os.listdir

    def racing_listdir(path):
        if os.fspath(path) == str(album):
            raise FileNotFoundError(path)
        return real_listdir(path)

    monkeypatch.setattr(app_module.os, "listdir", racing_listdir)

    response = client.get("/api/files", headers=auth_headers)

    assert response.status_code == 200
    node = _find_node(response.get_json(), test_dir.name)
    assert [item["name"] for item in node["children"]] == ["keep.mp3"]
