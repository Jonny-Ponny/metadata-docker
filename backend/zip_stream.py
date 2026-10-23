"""Stream a directory as a ZIP archive without buffering it in memory.

``zipfile`` writes an archive to a file-like object. To stream it, the archive
is built in a background thread that writes into a bounded queue, and the HTTP
response generator yields those chunks as they appear. Backpressure comes from
the queue's ``maxsize``: when the client is slow, the producer blocks instead
of growing the buffer.

The writer is non-seekable, so ``zipfile`` falls back to data descriptors and
supports ZIP64 archives (folders larger than 4 GiB) without seeking.
"""

import io
import os
import queue
import shutil
import threading
import zipfile

from logger_config import log_error, log_warning

# Chunks handed to the WSGI server.
CHUNK_SIZE = 256 * 1024
# Chunks buffered ahead of the client before the archive thread blocks.
QUEUE_SIZE = 8
# Read size when copying a file into the archive. Keeping this equal to the
# chunk size bounds the size of each piece handed to the WSGI server.
READ_SIZE = CHUNK_SIZE

_SENTINEL = object()
_POLL_INTERVAL = 0.2


class _QueueWriter(io.RawIOBase):
    """Non-seekable file object that forwards writes to a queue."""

    def __init__(self, chunks, stop):
        self._chunks = chunks
        self._stop = stop
        self._position = 0

    def writable(self):
        return True

    def seekable(self):
        return False

    def write(self, data):
        if not data:
            return 0
        data = bytes(data)
        while not self._stop.is_set():
            try:
                self._chunks.put(data, timeout=_POLL_INTERVAL)
            except queue.Full:
                continue
            self._position += len(data)
            return len(data)
        raise ConnectionAbortedError('download cancelled')

    def tell(self):
        return self._position

    def flush(self):
        pass

    def close(self):
        # zipfile closes the sink when it is done. Keep it open so a queued
        # sentinel can still be delivered by the producer.
        pass


def _signal_finished(chunks, stop):
    """Deliver the end-of-stream sentinel, waiting for queue space.

    ``put_nowait()`` drops the sentinel whenever the consumer has not drained
    the last chunks yet, which leaves ``iter_zip()`` blocked on ``chunks.get()``
    forever. Retry instead, and give up only when the consumer is gone, in
    which case ``stop`` is set and there is nobody left to notify.
    """
    while not stop.is_set():
        try:
            chunks.put(_SENTINEL, timeout=_POLL_INTERVAL)
            return
        except queue.Full:
            continue


def _is_within(base_path, candidate_path):
    """Return True when *candidate_path* resolves to *base_path* or below it."""
    try:
        base = os.path.realpath(base_path)
        candidate = os.path.realpath(candidate_path)
        return os.path.commonpath([base, candidate]) == base
    except ValueError:
        # Different drives on Windows cannot share a common path.
        return False


def _write_archive(root_path, destination):
    """Write every file under *root_path* into the archive at *destination*."""
    base_path = os.path.dirname(root_path)
    with zipfile.ZipFile(
        destination,
        mode='w',
        compression=zipfile.ZIP_DEFLATED,
        allowZip64=True,
    ) as archive:
        for current_path, dir_names, file_names in os.walk(root_path):
            # Never descend through symlinked directories: they can escape the
            # folder being downloaded or form a cycle.
            dir_names[:] = sorted(
                name for name in dir_names
                if not os.path.islink(os.path.join(current_path, name))
            )
            for file_name in sorted(file_names):
                full_path = os.path.join(current_path, file_name)

                # A symlinked file is only included when it still resolves
                # inside the folder being downloaded, mirroring safe_path().
                if os.path.islink(full_path) and not _is_within(root_path, full_path):
                    log_warning(
                        f'Skipping {full_path} in ZIP download: '
                        'symlink points outside the folder'
                    )
                    continue

                archive_name = os.path.relpath(full_path, base_path).replace('\\', '/')

                # Open before creating the entry: an unreadable file can then
                # be skipped without leaving a half-written entry behind.
                try:
                    source = open(full_path, 'rb')
                except OSError as exc:
                    log_warning(f'Skipping {full_path} in ZIP download: {exc}')
                    continue

                with source:
                    info = zipfile.ZipInfo.from_file(full_path, archive_name)
                    info.compress_type = zipfile.ZIP_DEFLATED
                    with archive.open(info, 'w', force_zip64=True) as member:
                        shutil.copyfileobj(source, member, READ_SIZE)


def iter_zip(folder_path, chunk_size=CHUNK_SIZE):
    """Yield the bytes of a ZIP archive containing *folder_path*.

    The first chunk is sent as soon as the first file has been read, so the
    browser starts downloading immediately. Errors that happen before any data
    is sent are raised to the caller; errors after that abort the stream, which
    leaves a truncated (clearly failed) archive instead of a silently
    incomplete one.
    """
    chunks = queue.Queue(maxsize=QUEUE_SIZE)
    stop = threading.Event()
    errors = []

    def produce():
        try:
            _write_archive(folder_path, _QueueWriter(chunks, stop))
        except ConnectionAbortedError:
            # Client went away; nothing left to do.
            pass
        except BaseException as exc:  # noqa: BLE001 - report any failure
            errors.append(exc)
            log_error(f'ZIP streaming failed for {folder_path}: {exc}')
        finally:
            _signal_finished(chunks, stop)

    worker = threading.Thread(
        target=produce,
        name='zip-stream',
        daemon=True,
    )
    worker.start()

    pending = []
    pending_size = 0
    try:
        while True:
            try:
                item = chunks.get(timeout=_POLL_INTERVAL)
            except queue.Empty:
                # A lost sentinel must never hang the response: if the producer
                # is gone, the archive is finished no matter what it queued.
                if not worker.is_alive():
                    break
                continue
            if item is _SENTINEL:
                break
            pending.append(item)
            pending_size += len(item)
            if pending_size >= chunk_size:
                yield b''.join(pending)
                pending.clear()
                pending_size = 0
        if pending:
            yield b''.join(pending)
    finally:
        stop.set()
        worker.join(timeout=5)

    if errors:
        raise errors[0]
