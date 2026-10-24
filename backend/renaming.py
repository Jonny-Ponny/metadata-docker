"""Smart renaming: turn metadata values into a new file or folder name.

Pure helpers only. ``generate_name_from_scheme`` takes the scheme string and
the metadata dict, resolves the known variables (``TITLE``, ``ALBUM``,
``ARTIST``, ...), extracts the year from a release date and produces a clean
bare file name or folder name. Everything that touches the library — walking
folders, reading metadata, renaming — stays in the route.
"""

import os
import re

from formats import is_supported_audio


VARIABLE_MAP = {
    'TITLE': 'title',
    'ALBUM': 'album',
    'ARTIST': 'artist',
    'ALBUMARTIST': 'albumArtist',
    'YYYY': 'date',  # Will extract just the year from date
    'TRACK': 'trackNumber',
    'DISK': 'diskNumber',
    'RELEASETYPE': 'releaseType',
}

_INFERRED_YEAR = re.compile(r'(?<!\d)(?:18|19|20)\d{2}(?!\d)')
_VARIABLE = re.compile(r'\[([^\[\]]+)\]')
_INVALID_CHARS = re.compile(r'[<>:"/\\|?*]')
_WHITESPACE = re.compile(r'\s+')


def extract_year(date_val):
    """Return the first four-digit year (1800-2099) found in *date_val*."""
    if not date_val:
        return None

    match = _INFERRED_YEAR.search(str(date_val))
    return match.group(0) if match else None


def generate_name_from_scheme(scheme_str, metadata, replace_spaces=False):
    """Generate a new name from a scheme and its metadata values."""
    result = scheme_str

    variables_in_scheme = _VARIABLE.findall(scheme_str)

    extracted_year = extract_year(metadata.get('date'))

    missing_fields = []
    for var in variables_in_scheme:
        if var not in VARIABLE_MAP:
            continue  # Skip unknown variables (they'll remain as-is)

        field = VARIABLE_MAP[var]

        if field == 'date':
            has_value = extracted_year is not None
        else:
            has_value = bool(metadata.get(field))

        if not has_value:
            missing_fields.append(var)

    if missing_fields:
        raise ValueError(
            f'Missing metadata fields for variables: {", ".join(missing_fields)}. '
            'Please fill these fields first.'
        )

    for var, field in VARIABLE_MAP.items():
        value = ''
        if field == 'date':
            value = extracted_year or ''
        elif field == 'trackNumber' and metadata.get('trackNumber'):
            track = str(metadata['trackNumber']).split('/')[0]
            value = track.zfill(2)
        elif field == 'diskNumber' and metadata.get('diskNumber'):
            disk = str(metadata['diskNumber']).split('/')[0]
            value = disk.zfill(2)
        elif field == 'releaseType' and metadata.get('releaseType'):
            value = str(metadata['releaseType'])
        elif metadata.get(field):
            value = str(metadata[field])

        # Replace the variable (case sensitive)
        result = result.replace(f'[{var}]', value)

    # Clean up multiple spaces and trim
    result = _WHITESPACE.sub(' ', result).strip()

    # Replace spaces with underscores if option is enabled
    if replace_spaces:
        result = result.replace(' ', '_')

    # Remove any characters that aren't allowed in filenames
    result = _INVALID_CHARS.sub('', result)

    return result


def find_first_audio(root_path):
    """Return the first supported audio file under *root_path*, skipping links.

    Symlinked directories are not descended, and symlinked files are skipped,
    so a bulk rename never reads a target outside the folder being renamed.
    """
    first_audio = None
    for current_path, dir_names, file_names in os.walk(root_path):
        dir_names[:] = [
            name for name in dir_names
            if not os.path.islink(os.path.join(current_path, name))
        ]
        for file_name in sorted(file_names):
            candidate = os.path.join(current_path, file_name)
            if os.path.islink(candidate):
                continue
            if is_supported_audio(candidate):
                first_audio = candidate
                break
        if first_audio:
            break
    return first_audio


def same_path(path1, path2):
    """Return True when both paths name the same file or folder."""
    if os.path.abspath(path1) == os.path.abspath(path2):
        return True
    try:
        return os.path.exists(path1) and os.path.exists(path2) and os.path.samefile(path1, path2)
    except OSError:
        return False


def unique_destination(path, is_folder):
    """Return *path* or the first free "name (n).ext" / "name (n)" variant."""
    candidate = path
    counter = 1
    while os.path.exists(candidate):
        if is_folder:
            candidate = f'{path} ({counter})'
        else:
            base, ext = os.path.splitext(path)
            candidate = f'{base} ({counter}){ext}'
        counter += 1
    return candidate
