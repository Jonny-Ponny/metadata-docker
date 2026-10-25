"""Folder iteration, failure accounting and single-file write guards."""

import metadata_writer


def test_recursive_iteration_skips_symlinks(tmp_path):
    album = tmp_path / "album"
    album.mkdir()
    first = album / "a.mp3"
    first.write_bytes(b"a")
    second = album / "b.flac"
    second.write_bytes(b"b")
    (album / "notes.txt").write_text("not audio")

    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "target.mp3").write_bytes(b"outside")
    (album / "0-link.mp3").symlink_to(outside / "target.mp3")
    (album / "0-linked-dir").symlink_to(outside, target_is_directory=True)

    assert list(metadata_writer._iter_audio_files(str(album))) == [
        str(first),
        str(second),
    ]


def test_current_only_iteration_skips_subfolders_and_symlinks(tmp_path):
    album = tmp_path / "album"
    album.mkdir()
    track = album / "a.mp3"
    track.write_bytes(b"a")
    subfolder = album / "sub"
    subfolder.mkdir()
    (subfolder / "b.mp3").write_bytes(b"b")

    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "target.mp3").write_bytes(b"outside")
    (album / "0-link.mp3").symlink_to(outside / "target.mp3")

    assert list(
        metadata_writer._iter_audio_files(str(album), recursive=False)
    ) == [str(track)]


def test_apply_to_folder_counts_successes_and_failures(tmp_path):
    for name in ("bad.mp3", "ok.mp3", "skip.mp3"):
        (tmp_path / name).write_bytes(b"audio")

    def operation(path):
        if path.endswith("bad.mp3"):
            raise RuntimeError("boom")
        return not path.endswith("skip.mp3")

    result = metadata_writer._apply_to_folder(str(tmp_path), operation)

    assert result == {
        "total": 3,
        "updated": 1,
        "failed": 2,
        "failed_files": [
            str(tmp_path / "bad.mp3"),
            str(tmp_path / "skip.mp3"),
        ],
    }


def test_apply_to_an_empty_folder_reports_nothing(tmp_path):
    result = metadata_writer.update_folder_metadata(
        str(tmp_path), "title", "value"
    )

    assert result == {
        "total": 0,
        "updated": 0,
        "failed": 0,
        "failed_files": [],
    }


def test_unsupported_extension_is_not_modified(tmp_path):
    notes = tmp_path / "notes.txt"
    notes.write_bytes(b"text")

    assert metadata_writer.update_file_metadata(str(notes), "title", "x") is False


def test_corrupt_audio_returns_false_instead_of_raising(tmp_path):
    corrupt = tmp_path / "corrupt.mp3"
    corrupt.write_bytes(b"not real audio")

    assert metadata_writer.update_file_metadata(str(corrupt), "title", "x") is False


def test_unknown_action_returns_false(audio_file):
    song = audio_file(".mp3", name="song.mp3")

    assert metadata_writer._modify(str(song), "not-an-action") is False
