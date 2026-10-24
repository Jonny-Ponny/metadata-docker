"""Rename guardrails for the file tree (B-05)."""

from pathlib import Path


def _relative(path, music_root):
    return Path(path).relative_to(music_root).as_posix()


def test_rename_cannot_overwrite_an_existing_file(
    client, auth_headers, music_root, test_dir
):
    source = test_dir / "a.mp3"
    source.write_bytes(b"source")
    target = test_dir / "b.mp3"
    target.write_bytes(b"target")

    response = client.post(
        "/api/rename",
        headers=auth_headers,
        json={"oldPath": _relative(source, music_root), "newName": "b.mp3"},
    )

    assert response.status_code == 409
    assert source.read_bytes() == b"source"
    assert target.read_bytes() == b"target"


def test_rename_to_the_same_name_is_a_noop(
    client, auth_headers, music_root, test_dir
):
    song = test_dir / "song.mp3"
    song.write_bytes(b"audio")

    response = client.post(
        "/api/rename",
        headers=auth_headers,
        json={"oldPath": _relative(song, music_root), "newName": "song.mp3"},
    )

    assert response.status_code == 200
    assert song.read_bytes() == b"audio"


def test_rename_still_renames(client, auth_headers, music_root, test_dir):
    song = test_dir / "song.mp3"
    song.write_bytes(b"audio")

    response = client.post(
        "/api/rename",
        headers=auth_headers,
        json={"oldPath": _relative(song, music_root), "newName": "renamed.mp3"},
    )

    assert response.status_code == 200
    assert not song.exists()
    assert (test_dir / "renamed.mp3").read_bytes() == b"audio"


# --- Smart renaming helpers (Phase 3, renaming module) ---


def test_extract_year_reads_the_first_inferred_year():
    from renaming import extract_year

    assert extract_year("1999-12-31") == "1999"
    assert extract_year("the 2020 release") == "2020"
    assert extract_year("19991998") is None
    assert extract_year("") is None
    assert extract_year(None) is None


def test_generate_name_from_scheme_resolves_known_variables():
    from renaming import generate_name_from_scheme

    name = generate_name_from_scheme(
        "[ARTIST] - [TITLE] [TRACK]",
        {
            "artist": "Artist",
            "title": "Song",
            "trackNumber": "3/12",
        },
    )

    assert name == "Artist - Song 03"


def test_generate_name_from_scheme_requires_the_variables_to_have_values():
    from renaming import generate_name_from_scheme

    import pytest

    with pytest.raises(ValueError, match="Missing metadata"):
        generate_name_from_scheme("[ARTIST] - [TITLE]", {"title": "Song"})


def test_generate_name_from_scheme_cleans_and_optionally_underscores():
    from renaming import generate_name_from_scheme

    name = generate_name_from_scheme(
        "[ARTIST] - [TITLE] [YYYY]",
        {"artist": "A B", "title": "Song: Name", "date": "2020-01-02"},
    )

    # Invalid characters are stripped, collapsed whitespace is trimmed.
    assert name == "A B - Song Name 2020"

    underscored = generate_name_from_scheme(
        "[ARTIST] - [TITLE] [YYYY]",
        {"artist": "A B", "title": "Song", "date": "2020-01-02"},
        replace_spaces=True,
    )

    assert underscored == "A_B_-_Song_2020"


def test_find_first_audio_skips_non_audio_and_links(tmp_path):
    from renaming import find_first_audio

    (tmp_path / "notes.txt").write_text("not audio")
    album = tmp_path / "album"
    album.mkdir()
    (album / "a.mp3").write_bytes(b"a")
    (album / "b.flac").write_bytes(b"b")

    assert find_first_audio(str(album)).endswith("a.mp3")


def test_find_first_audio_returns_none_for_a_folder_without_audio(tmp_path):
    from renaming import find_first_audio

    (tmp_path / "folder").mkdir()

    assert find_first_audio(str(tmp_path / "folder")) is None


def test_unique_destination_appends_a_number_until_free(tmp_path):
    from renaming import unique_destination

    path = tmp_path / "song.mp3"
    path.write_bytes(b"audio")
    (tmp_path / "song (1).mp3").write_bytes(b"audio")

    assert str(unique_destination(str(path), is_folder=False)) == str(
        tmp_path / "song (2).mp3"
    )


def test_same_path_detects_aliases(tmp_path):
    from renaming import same_path

    song = tmp_path / "song.mp3"
    song.write_bytes(b"audio")

    assert same_path(str(song), str(song)) is True
    assert same_path(str(song), str(tmp_path / "other.mp3")) is False
