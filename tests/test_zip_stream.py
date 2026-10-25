"""ZIP streaming must always terminate (B-30).

``iter_zip()`` builds the archive in a producer thread and hands the bytes to
the response generator through a bounded queue. The producer used to announce
completion with ``put_nowait()``: when the consumer had not drained the last
chunks yet, the queue was full, the sentinel was dropped and the generator
blocked on ``chunks.get()`` forever. One folder download in four hung in the
test client, and the same download would hang a real worker.
"""

import io
import os
import queue
import threading
import zipfile

import pytest

import zip_stream


def test_sentinel_waits_for_queue_space():
    chunks = queue.Queue(maxsize=1)
    chunks.put(b"first")
    stop = threading.Event()
    worker = threading.Thread(
        target=zip_stream._signal_finished,
        args=(chunks, stop),
        daemon=True,
    )

    worker.start()
    worker.join(0.3)

    # The queue is still full, so the sentinel cannot be delivered yet; it must
    # wait instead of being dropped.
    assert worker.is_alive()
    assert chunks.get(timeout=1) == b"first"

    worker.join(1)
    assert not worker.is_alive()
    assert chunks.get(timeout=1) is zip_stream._SENTINEL


def test_sentinel_is_skipped_when_the_consumer_is_gone():
    chunks = queue.Queue(maxsize=1)
    chunks.put(b"first")
    stop = threading.Event()
    stop.set()

    zip_stream._signal_finished(chunks, stop)

    assert chunks.qsize() == 1


def test_iter_zip_finishes_even_without_a_sentinel(monkeypatch, tmp_path):
    (tmp_path / "track.mp3").write_bytes(b"audio" * 100)

    # Simulate a completion signal that never arrives; the consumer must notice
    # the finished producer instead of blocking forever.
    monkeypatch.setattr(zip_stream, "_signal_finished", lambda chunks, stop: None)

    data = b"".join(zip_stream.iter_zip(str(tmp_path), chunk_size=256))

    assert data.startswith(b"PK")


def test_iter_zip_yields_every_chunk_of_a_folder(monkeypatch, tmp_path):
    for index in range(5):
        (tmp_path / f"track{index}.mp3").write_bytes(bytes([index]) * 1024)

    # A one-slot queue forces the producer to fill the queue and hit the same
    # full-queue race at completion on every run.
    monkeypatch.setattr(zip_stream, "QUEUE_SIZE", 1)

    data = b"".join(zip_stream.iter_zip(str(tmp_path), chunk_size=64))

    assert data.startswith(b"PK")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        assert sorted(archive.namelist()) == [
            f"{tmp_path.name}/track{index}.mp3" for index in range(5)
        ]


def test_queue_writer_stops_when_the_download_is_cancelled():
    stop = threading.Event()
    stop.set()
    writer = zip_stream._QueueWriter(queue.Queue(), stop)

    assert writer.writable() is True
    assert writer.seekable() is False
    assert writer.write(b"") == 0
    with pytest.raises(ConnectionAbortedError):
        writer.write(b"data")
    assert writer.tell() == 0


def test_queue_writer_waits_for_space_instead_of_dropping_data():
    chunks = queue.Queue(maxsize=1)
    chunks.put(b"first")
    stop = threading.Event()
    writer = zip_stream._QueueWriter(chunks, stop)
    result = []

    worker = threading.Thread(
        target=lambda: result.append(writer.write(b"second")),
        daemon=True,
    )
    worker.start()
    worker.join(0.3)

    # The queue is full, so the producer must block rather than lose a chunk.
    assert worker.is_alive()
    assert writer.tell() == 0
    assert chunks.get(timeout=1) == b"first"

    worker.join(1)
    assert result == [len(b"second")]
    assert writer.tell() == len(b"second")
    assert chunks.get(timeout=1) == b"second"


def test_iter_zip_skips_a_file_that_cannot_be_opened(tmp_path, monkeypatch):
    folder = tmp_path / "album"
    folder.mkdir()
    good = folder / "good.mp3"
    good.write_bytes(b"good audio")
    bad = folder / "bad.mp3"
    bad.write_bytes(b"bad audio")

    real_open = open

    def guarded(path, *args, **kwargs):
        if os.fspath(path) == str(bad):
            raise PermissionError(path)
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(zip_stream, "open", guarded, raising=False)

    data = b"".join(zip_stream.iter_zip(str(folder)))

    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        assert archive.namelist() == ["album/good.mp3"]
        assert archive.read("album/good.mp3") == b"good audio"
