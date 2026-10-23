"""The library root itself must not be deleted, recreated or copied.

``safe_path()`` maps ``""``, ``"."`` and ``"/"`` to the music root, so routes
that derive a new name from the resolved path (mkdir, copy) or remove it
(delete) would otherwise act one level above the library.
"""

from pathlib import Path

import pytest


def _relative(path, music_root):
    return Path(path).relative_to(music_root).as_posix()


def test_delete_cannot_remove_the_library_root(client, auth_headers, music_root):
    for path in ('.', '/', './'):
        response = client.post(
            '/api/delete',
            headers=auth_headers,
            json={'path': path},
        )
        assert response.status_code == 400, path
        assert response.get_json()['error'] == 'Cannot delete the library root'

    assert music_root.is_dir()


def test_delete_still_removes_a_file(client, auth_headers, music_root, test_dir):
    song = test_dir / 'song.mp3'
    song.write_bytes(b'audio')

    response = client.post(
        '/api/delete',
        headers=auth_headers,
        json={'path': _relative(song, music_root)},
    )

    assert response.status_code == 200
    assert not song.exists()


@pytest.mark.parametrize('path', ['.', '/', './'])
@pytest.mark.parametrize('conflict', [None, 'merge'])
def test_mkdir_cannot_create_the_library_root(
    client, auth_headers, music_root, path, conflict
):
    payload = {'path': path}
    if conflict:
        payload['conflict'] = conflict

    response = client.post('/api/mkdir', headers=auth_headers, json=payload)

    assert response.status_code == 400, (path, conflict)
    assert response.get_json()['error'] == 'Cannot create the library root'
    assert music_root.is_dir()
    assert not music_root.with_name(f'{music_root.name} (1)').exists()


def test_mkdir_still_creates_a_folder(client, auth_headers, music_root, test_dir):
    album = test_dir / 'Album'

    response = client.post(
        '/api/mkdir',
        headers=auth_headers,
        json={'path': _relative(album, music_root)},
    )

    assert response.status_code == 200
    assert response.get_json()['created'] is True
    assert album.is_dir()
