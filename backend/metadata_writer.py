"""Write metadata and cover art to supported audio files."""

import os

from mutagen import File

from formats import is_supported_audio
from logger_config import log_error, log_info
from tag_backends import backend_for


def _load_audio(file_path):
    audio = File(file_path, easy=False)
    if audio is None:
        log_error(f"File: {file_path}. Could not open audio file")
    return audio


def _backend_for_audio(file_path, audio):
    backend = backend_for(audio)
    if backend is None:
        log_error(f"File: {file_path}. Unsupported audio format")
    return backend


def update_file_metadata(file_path, field, value):
    """Update a single metadata field in a file."""
    if not is_supported_audio(file_path):
        return False

    try:
        audio = _load_audio(file_path)
        if audio is None:
            return False

        backend = _backend_for_audio(file_path, audio)
        if backend is None:
            return False

        backend.write_field(audio, field, value)
        backend.save(audio)
        log_info(f"File: {file_path}. Updated {field}")
        return True

    except Exception as e:
        log_error(f"File: {file_path}. Error updating metadata: {e}")
        return False


def update_file_picture(file_path, image_data, mime_type=None):
    """Update cover art in a file."""
    if not is_supported_audio(file_path):
        return False

    try:
        audio = _load_audio(file_path)
        if audio is None:
            return False

        backend = _backend_for_audio(file_path, audio)
        if backend is None:
            return False

        backend.set_picture(audio, image_data, mime_type)
        backend.save(audio)
        log_info(f"File: {file_path}. Updated cover art")
        return True

    except Exception as e:
        log_error(f"File: {file_path}. Error updating picture: {e}")
        return False


def delete_metadata_field(file_path, field):
    """Delete a specific metadata field from a file."""
    if not is_supported_audio(file_path):
        return False

    try:
        audio = _load_audio(file_path)
        if audio is None:
            return False

        backend = _backend_for_audio(file_path, audio)
        if backend is None:
            return False

        backend.delete_field(audio, field)
        backend.save(audio)
        log_info(f"File: {file_path}. Deleted {field}")
        return True

    except Exception as e:
        log_error(f"File: {file_path}. Error deleting field: {e}")
        return False


def delete_cover_art(file_path):
    """Delete cover art from a file."""
    if not is_supported_audio(file_path):
        return False

    try:
        audio = _load_audio(file_path)
        if audio is None:
            return False

        backend = _backend_for_audio(file_path, audio)
        if backend is None:
            return False

        backend.delete_picture(audio)
        backend.save(audio)
        log_info(f"File: {file_path}. Deleted cover art")
        return True

    except Exception as e:
        log_error(f"File: {file_path}. Error deleting cover art: {e}")
        return False


def _iter_audio_files(folder_path, recursive=True):
    """Yield supported audio files in *folder_path*."""
    if recursive:
        for root, _, files in os.walk(folder_path):
            for file in files:
                file_path = os.path.join(root, file)
                if is_supported_audio(file_path):
                    yield file_path
        return

    for file in os.listdir(folder_path):
        file_path = os.path.join(folder_path, file)
        if os.path.isfile(file_path) and is_supported_audio(file_path):
            yield file_path


def _apply_to_folder(folder_path, operation, recursive=True):
    """Apply *operation* to every supported audio file in a folder."""
    results = {
        'total': 0,
        'updated': 0,
        'failed': 0,
        'failed_files': [],
    }

    for file_path in _iter_audio_files(folder_path, recursive=recursive):
        results['total'] += 1
        try:
            if operation(file_path):
                results['updated'] += 1
            else:
                results['failed'] += 1
                results['failed_files'].append(file_path)
        except Exception as e:
            log_error(f"Error processing {file_path}: {e}")
            results['failed'] += 1
            results['failed_files'].append(file_path)

    return results


def update_folder_metadata(folder_path, field, value):
    """Update a metadata field for all audio files in a folder."""
    return _apply_to_folder(
        folder_path,
        lambda file_path: update_file_metadata(file_path, field, value),
    )


def update_folder_pictures(folder_path, image_data, mime_type=None):
    """Update cover art for all audio files in a folder."""
    return _apply_to_folder(
        folder_path,
        lambda file_path: update_file_picture(file_path, image_data, mime_type),
    )


def update_folder_metadata_only_current(folder_path, field, value):
    """Update a metadata field in the current folder only (no subfolders)."""
    return _apply_to_folder(
        folder_path,
        lambda file_path: update_file_metadata(file_path, field, value),
        recursive=False,
    )


def update_folder_pictures_only_current(folder_path, image_data, mime_type=None):
    """Update cover art in the current folder only (no subfolders)."""
    return _apply_to_folder(
        folder_path,
        lambda file_path: update_file_picture(file_path, image_data, mime_type),
        recursive=False,
    )


def delete_field_from_folder(folder_path, field, recursive=False):
    """Delete a metadata field from all audio files in a folder."""
    return _apply_to_folder(
        folder_path,
        lambda file_path: delete_metadata_field(file_path, field),
        recursive=recursive,
    )
