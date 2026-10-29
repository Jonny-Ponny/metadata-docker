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


# One dispatcher for every single-file tag mutation, so format support, logging
# and error handling cannot drift between the public wrappers below.
_ACTION_ERROR_LABELS = {
    'update_field': 'updating metadata',
    'update_fields': 'updating metadata',
    'update_picture': 'updating picture',
    'delete_field': 'deleting field',
    'delete_cover_art': 'deleting cover art',
}


def _modify(file_path, action, *args):
    """Apply *action* to one supported audio file; return True on success."""
    if not is_supported_audio(file_path):
        return False

    try:
        audio = _load_audio(file_path)
        if audio is None:
            return False

        backend = _backend_for_audio(file_path, audio)
        if backend is None:
            return False

        if action == 'update_field':
            field, value = args
            backend.write_field(audio, field, value)
            message = f"Updated {field}"
        elif action == 'update_fields':
            values, deletions = args
            for field, value in values.items():
                backend.write_field(audio, field, value)
            for field in deletions:
                backend.delete_field(audio, field)
            changed = [*values, *(f"-{field}" for field in deletions)]
            message = f"Updated {', '.join(changed)}"
        elif action == 'update_picture':
            image_data, mime_type = args
            backend.set_picture(audio, image_data, mime_type)
            message = "Updated cover art"
        elif action == 'delete_field':
            (field,) = args
            backend.delete_field(audio, field)
            message = f"Deleted {field}"
        elif action == 'delete_cover_art':
            backend.delete_picture(audio)
            message = "Deleted cover art"
        else:
            raise ValueError(f"Unknown metadata action: {action}")

        backend.save(audio)
        log_info(f"File: {file_path}. {message}")
        return True

    except Exception as e:
        label = _ACTION_ERROR_LABELS.get(action, action)
        log_error(f"File: {file_path}. Error {label}: {e}")
        return False


def update_file_metadata(file_path, field, value):
    """Update a single metadata field in a file."""
    return _modify(file_path, 'update_field', field, value)


def update_file_fields(file_path, values, deletions=()):
    """Set and delete several metadata fields in a file with one save."""
    return _modify(file_path, 'update_fields', dict(values), list(deletions))


def update_file_picture(file_path, image_data, mime_type=None):
    """Update cover art in a file."""
    return _modify(file_path, 'update_picture', image_data, mime_type)


def delete_metadata_field(file_path, field):
    """Delete a specific metadata field from a file."""
    return _modify(file_path, 'delete_field', field)


def delete_cover_art(file_path):
    """Delete cover art from a file."""
    return _modify(file_path, 'delete_cover_art')


def _iter_audio_files(folder_path, recursive=True):
    """Yield supported audio files in *folder_path*.

    Symlinks are skipped deliberately: a bulk tag/cover operation should never
    follow a link out of the folder the user selected. Access to individual
    symlinked files still goes through ``safe_path()``, which checks the
    resolved target.
    """
    if recursive:
        for root, dir_names, files in os.walk(folder_path):
            # os.walk() does not follow symlinked directories by default;
            # pruning them keeps that explicit and prevents surprises.
            dir_names[:] = [
                name for name in dir_names
                if not os.path.islink(os.path.join(root, name))
            ]
            for file in sorted(files):
                file_path = os.path.join(root, file)
                if os.path.islink(file_path):
                    continue
                if is_supported_audio(file_path):
                    yield file_path
        return

    for file in sorted(os.listdir(folder_path)):
        file_path = os.path.join(folder_path, file)
        if os.path.islink(file_path):
            continue
        if os.path.isfile(file_path) and is_supported_audio(file_path):
            yield file_path


def _apply_to_folder(folder_path, operation, recursive=True):
    """Apply *operation* to every supported audio file in a folder."""
    return _apply_to_files(
        _iter_audio_files(folder_path, recursive=recursive), operation
    )


def _apply_to_files(file_paths, operation):
    """Apply *operation* to each path and count successes and failures."""
    results = {
        'total': 0,
        'updated': 0,
        'failed': 0,
        'failed_files': [],
    }

    for file_path in file_paths:
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


def update_files_fields(file_paths, values, deletions=()):
    """Set and delete metadata fields on each of *file_paths*.

    Paths must already be resolved and checked by the caller. Missing,
    unsupported or symlinked files are counted as failures, like the folder
    helpers, which never follow links either.
    """
    def operation(file_path):
        if os.path.islink(file_path) or not os.path.isfile(file_path):
            return False
        return update_file_fields(file_path, values, deletions)

    return _apply_to_files(file_paths, operation)


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
