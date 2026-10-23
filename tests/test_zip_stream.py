"""ZIP streaming must always terminate (B-30).

``iter_zip()`` builds the archive in a producer thread and hands the bytes to
the response generator through a bounded queue. The producer used to announce
completion with ``put_nowait()``: when the consumer had not drained the last
chunks yet, the queue was full, the sentinel was dropped and the generator
blocked on ``chunks.get()`` forever. One folder download in four hung in the
test client, and the same download would hang a real worker.
"""

import io
import queue
import threading
import zipfile

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
