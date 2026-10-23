"""Path containment and generated-name validation helpers."""

from pathlib import Path

import pytest


def test_safe_path_rejects_nul_bytes(app_module):
    with pytest.raises(app_module.AccessDenied):
        app_module.safe_path("song\0.mp3")


def test_safe_path_treats_absolute_input_as_library_relative(
    app_module, music_root
):
    """Leading slashes select the library root, not the host filesystem."""
    resolved = app_module.safe_path("/etc/passwd")

    assert Path(resolved) == music_root / "etc" / "passwd"
    assert app_module._is_within(app_module.MUSIC_ROOT, resolved)


@pytest.mark.parametrize("path", ["../outside.mp3", "album/../../outside.mp3"])
def test_safe_path_rejects_parent_traversal(app_module, path):
    with pytest.raises(app_module.AccessDenied):
        app_module.safe_path(path)


def test_safe_path_accepts_a_normal_relative_path(app_module, music_root):
    assert Path(app_module.safe_path("album/song.mp3")) == (
        music_root / "album" / "song.mp3"
    )


def test_is_within_does_not_use_a_string_prefix(app_module, tmp_path):
    """``/music-other`` is a sibling of ``/music``, not a child."""
    music = tmp_path / "music"
    music.mkdir()
    sibling = tmp_path / "music-other"
    sibling.mkdir()

    assert app_module._is_within(music, music / "album")
    assert app_module._is_within(music, music)
    assert not app_module._is_within(music, sibling)
    assert not app_module._is_within(music, sibling / "song.mp3")


def test_is_within_resolves_inside_and_outside_symlinks(app_module, tmp_path):
    music = tmp_path / "music"
    album = music / "album"
    outside = tmp_path / "outside"
    for directory in (album, outside):
        directory.mkdir(parents=True)

    inside_link = music / "inside-link"
    inside_link.symlink_to(album)
    outside_link = music / "outside-link"
    outside_link.symlink_to(outside)

    assert app_module._is_within(music, inside_link / "song.mp3")
    assert not app_module._is_within(music, outside_link / "song.mp3")


@pytest.mark.parametrize(
    "name",
    [
        "",
        ".",
        "..",
        "album/song",
        "album\\song",
        "/absolute",
        "song\0",
        " leading",
        "trailing ",
    ],
)
def test_generated_rename_path_rejects_unsafe_names(app_module, name):
    with pytest.raises(ValueError):
        app_module._generated_rename_path(app_module.MUSIC_ROOT, name)


def test_generated_rename_path_accepts_a_bare_name(app_module, music_root):
    resolved = app_module._generated_rename_path(music_root, "Artist - Title")

    assert Path(resolved) == music_root / "Artist - Title"
