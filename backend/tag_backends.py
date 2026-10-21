"""Tag read/write backends grouped by tag family.

The app supports several containers, but they only use three tag models:

* ID3 (MP3, later WAV/AIFF)
* native FLAC metadata blocks
* Vorbis comments

Keeping the per-family logic here means ``metadata_extractor`` and
``metadata_writer`` stay small, and a new format usually only needs a registry
entry plus, at most, a small backend override.
"""

import base64
import re

from mutagen.flac import FLAC, Picture
from mutagen.id3 import (
    APIC,
    COMM,
    SYLT,
    TALB,
    TCOM,
    TCON,
    TDRC,
    TIT2,
    TPE1,
    TPE2,
    TPOS,
    TPUB,
    TRCK,
    TXXX,
    USLT,
    Encoding,
    TextFrame,
)
from mutagen.mp3 import MP3
from mutagen.oggopus import OggOpus
from mutagen.oggvorbis import OggVorbis


# Canonical frontend field -> tag key per family. ``TXXX:NAME`` means the value
# is stored in a TXXX frame with that description.
FIELD_SCHEMA = {
    'title': {'id3': 'TIT2', 'vorbis': 'TITLE'},
    'album': {'id3': 'TALB', 'vorbis': 'ALBUM'},
    'artist': {'id3': 'TPE1', 'vorbis': 'ARTIST'},
    'albumArtist': {'id3': 'TPE2', 'vorbis': 'ALBUMARTIST'},
    'trackNumber': {'id3': 'TRCK', 'vorbis': 'TRACKNUMBER'},
    'diskNumber': {'id3': 'TPOS', 'vorbis': 'DISCNUMBER'},
    'date': {'id3': 'TDRC', 'vorbis': 'DATE'},
    'genre': {'id3': 'TCON', 'vorbis': 'GENRE'},
    'comment': {'id3': 'COMM', 'vorbis': 'COMMENT'},
    'description': {'id3': 'TXXX:DESCRIPTION', 'vorbis': 'DESCRIPTION'},
    'composer': {'id3': 'TCOM', 'vorbis': 'COMPOSER'},
    'publisher': {'id3': 'TPUB', 'vorbis': 'PUBLISHER'},
    'releaseType': {'id3': 'TXXX:RELEASETYPE', 'vorbis': 'RELEASETYPE'},
    'lyrics': {'id3': 'SYLT', 'vorbis': 'LYRICS'},
    'unsyncedLyrics': {'id3': 'USLT', 'vorbis': 'UNSYNCEDLYRICS'},
}

ID3_FRAME_CLASSES = {
    'TIT2': TIT2,
    'TALB': TALB,
    'TPE1': TPE1,
    'TPE2': TPE2,
    'TRCK': TRCK,
    'TPOS': TPOS,
    'TDRC': TDRC,
    'TCON': TCON,
    'TCOM': TCOM,
    'TPUB': TPUB,
}

ID3_KEY_TO_FIELD = {}
ID3_TXXX_TO_FIELD = {}
for _field, _keys in FIELD_SCHEMA.items():
    _id3_key = _keys.get('id3')
    if not _id3_key:
        continue
    if _id3_key.startswith('TXXX:'):
        ID3_TXXX_TO_FIELD[_id3_key.split(':', 1)[1].upper()] = _field
    else:
        ID3_KEY_TO_FIELD[_id3_key.upper()] = _field

VORBIS_KEY_TO_FIELD = {
    keys['vorbis'].upper(): field
    for field, keys in FIELD_SCHEMA.items()
    if 'vorbis' in keys
}

VORBIS_PICTURE_KEY = 'METADATA_BLOCK_PICTURE'


def empty_metadata():
    """Default metadata payload shared by every backend."""
    return {
        'title': '', 'album': '', 'artist': '', 'albumArtist': '',
        'trackNumber': '', 'diskNumber': '', 'date': '', 'genre': '',
        'comment': '', 'description': '', 'lyrics': '',
        'unsyncedLyrics': '', 'composer': '', 'publisher': '',
        'releaseType': '', 'customFields': [],
    }


def detect_image_mime(image_data):
    """Detect the common cover-art MIME types from their magic bytes."""
    if image_data.startswith(b'\xff\xd8'):
        return 'image/jpeg'
    if image_data.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'image/png'
    return 'image/jpeg'


def resolve_image_mime(image_data, mime_type=None):
    """Trust a supplied image MIME type, otherwise detect it from the bytes."""
    if mime_type and mime_type.startswith('image/'):
        return mime_type
    return detect_image_mime(image_data)


def get_tag_text(frame):
    """Extract readable text from an ID3 frame."""
    if hasattr(frame, 'text'):
        return '; '.join(str(t) for t in frame.text)
    if isinstance(frame, list):
        return '; '.join(str(v) for v in frame)
    return str(frame)


def format_sylt_timestamp(timestamp, sample_rate=None):
    """Convert a SYLT timestamp to LRC ``[MM:SS.ss]`` format."""
    seconds = timestamp / sample_rate if sample_rate else timestamp / 1000
    minutes = int(seconds // 60)
    return f"[{minutes:02d}:{seconds % 60:05.2f}]"


def extract_sylt_text(sylt_frame, sample_rate):
    """Extract synchronized lyrics from a SYLT frame in LRC format."""
    if not sylt_frame or not hasattr(sylt_frame, 'text'):
        return ''

    lines = []
    for text, timestamp in sylt_frame.text:
        if getattr(sylt_frame, 'format', 1) == 2:
            timestamp_str = format_sylt_timestamp(timestamp)
        else:
            timestamp_str = format_sylt_timestamp(timestamp, sample_rate)
        lines.append(f"{timestamp_str} {text}")
    return '\n'.join(lines)


def lrc_to_sylt_events(value):
    """Convert LRC text using ``[MM:SS.ss]`` timestamps to SYLT events."""
    events = []
    for line in value.split('\n'):
        match = re.match(r'^\[(\d{2}):(\d{2}\.\d{2})\](.*)', line)
        if not match:
            continue
        minutes = int(match.group(1))
        seconds = float(match.group(2))
        text = match.group(3).strip()
        if text:
            events.append((text, int(round((minutes * 60 + seconds) * 1000))))
    return events


def _normalise_field_name(name):
    """Normalise custom field names so ``Release Type`` and ``releasetype`` match."""
    return re.sub(r'[\s_-]+', '', str(name)).upper()


def _picture_uri(image_data, mime):
    encoded = base64.b64encode(image_data).decode('utf-8')
    return f"data:{mime};base64,{encoded}"


class TagBackend:
    """Common interface implemented by every tag family backend."""

    family = ''
    supports_synced_lyrics = False
    picture_storage = ''

    def extract(self, audio):
        result = empty_metadata()
        if audio.tags is not None:
            self.read_tags(audio, result)

        picture = self.get_picture(audio)
        if picture:
            image_data, mime = picture
            result['picture'] = _picture_uri(image_data, mime)
        return result

    def read_tags(self, audio, result):
        raise NotImplementedError

    def write_field(self, audio, field, value):
        raise NotImplementedError

    def delete_field(self, audio, field):
        raise NotImplementedError

    def get_picture(self, audio):
        return None

    def set_picture(self, audio, image_data, mime_type):
        raise NotImplementedError

    def delete_picture(self, audio):
        raise NotImplementedError

    def save(self, audio):
        audio.save()


class Id3Backend(TagBackend):
    """ID3v2 tags (MP3 today, WAV/AIFF if registered later)."""

    family = 'id3'
    supports_synced_lyrics = True
    picture_storage = 'apic'

    def _tags(self, audio):
        if audio.tags is None:
            audio.add_tags()
        return audio.tags

    def read_tags(self, audio, result):
        tags = audio.tags
        if tags is None:
            return

        sample_rate = getattr(getattr(audio, 'info', None), 'sample_rate', 44100)

        for key in tags.keys():
            for frame in tags.getall(key):
                if isinstance(frame, TXXX):
                    if not frame.desc or not frame.text:
                        continue
                    value = '; '.join(str(t) for t in frame.text)
                    field = ID3_TXXX_TO_FIELD.get(frame.desc.upper())
                    if field:
                        if not result[field]:
                            result[field] = value
                    else:
                        result['customFields'].append(
                            {'name': frame.desc, 'value': value}
                        )
                    continue

                if isinstance(frame, SYLT):
                    lyrics = extract_sylt_text(frame, sample_rate)
                    if lyrics:
                        result['lyrics'] = lyrics
                    continue

                if isinstance(frame, USLT):
                    if frame.text:
                        result['unsyncedLyrics'] = frame.text
                    continue

                value = get_tag_text(frame)
                if not value:
                    continue

                # Frame keys can include a description/lang suffix
                # (for example ``COMM:eng:``); match on the frame ID.
                frame_id = key.split(':', 1)[0].upper()
                field = ID3_KEY_TO_FIELD.get(frame_id)
                if field:
                    if not result[field]:
                        result[field] = value
                elif isinstance(frame, TextFrame) or frame_id.startswith('T'):
                    result['customFields'].append({'name': key, 'value': value})

    def write_field(self, audio, field, value):
        tags = self._tags(audio)

        if field == 'comment':
            tags.delall('COMM')
            tags.add(COMM(encoding=Encoding.UTF8, lang='eng', desc='', text=value))
            return

        if field == 'unsyncedLyrics':
            tags.delall('USLT')
            tags.add(USLT(encoding=Encoding.UTF8, lang='eng', desc='', text=value))
            return

        if field == 'lyrics':
            tags.delall('SYLT')
            events = lrc_to_sylt_events(value)
            if events:
                tags.add(SYLT(
                    encoding=Encoding.UTF8,
                    lang='eng',
                    format=2,       # absolute milliseconds
                    type=1,
                    desc='',
                    text=events,
                ))
            return

        id3_key = FIELD_SCHEMA.get(field, {}).get('id3')
        if id3_key and id3_key.startswith('TXXX:'):
            desc = id3_key.split(':', 1)[1]
            self._remove_txxx(tags, desc)
            tags.add(TXXX(encoding=Encoding.UTF8, desc=desc, text=value))
            return

        frame_id = id3_key
        if frame_id:
            tags.delall(frame_id)
            frame_class = ID3_FRAME_CLASSES.get(frame_id)
            if frame_class:
                tags.add(frame_class(encoding=Encoding.UTF8, text=value))
            else:
                tags.add(TXXX(encoding=Encoding.UTF8, desc=frame_id, text=value))
            return

        # Unknown/custom field: store it as a TXXX frame.
        self._remove_txxx(tags, field)
        tags.add(TXXX(encoding=Encoding.UTF8, desc=field, text=value))

    def delete_field(self, audio, field):
        tags = audio.tags
        if tags is None:
            return

        id3_key = FIELD_SCHEMA.get(field, {}).get('id3')
        if id3_key and id3_key.startswith('TXXX:'):
            self._remove_txxx(tags, id3_key.split(':', 1)[1])
        elif id3_key:
            tags.delall(id3_key)
        else:
            self._remove_txxx(tags, field)

    @staticmethod
    def _remove_txxx(tags, name):
        normalised = _normalise_field_name(name)
        for key in list(tags.keys()):
            frame = tags[key]
            if isinstance(frame, TXXX) and _normalise_field_name(frame.desc) == normalised:
                del tags[key]

    def get_picture(self, audio):
        if audio.tags is None:
            return None
        for frame in audio.tags.values():
            if isinstance(frame, APIC):
                return frame.data, frame.mime
        return None

    def set_picture(self, audio, image_data, mime_type):
        tags = self._tags(audio)
        tags.delall('APIC')
        tags.add(APIC(
            encoding=Encoding.UTF8,
            mime=resolve_image_mime(image_data, mime_type),
            type=3,                 # front cover
            desc='Cover',
            data=image_data,
        ))

    def delete_picture(self, audio):
        if audio.tags is not None:
            audio.tags.delall('APIC')

    def save(self, audio):
        # Match the previous behaviour: remove the tag entirely when the last
        # frame was deleted instead of leaving an empty ID3 tag behind.
        if audio.tags is not None and not audio.tags:
            audio.delete()
        else:
            audio.save()


class VorbisBackend(TagBackend):
    """Vorbis comments used by OGG Vorbis and Opus."""

    family = 'vorbis'
    supports_synced_lyrics = False
    picture_storage = 'vorbis-comment'

    def read_tags(self, audio, result):
        tags = audio.tags
        if tags is None:
            return

        for key, values in tags.items():
            if key.upper() == VORBIS_PICTURE_KEY:
                continue

            if not isinstance(values, list):
                values = [values]
            value = '; '.join(str(v) for v in values)
            if not value:
                continue

            field = VORBIS_KEY_TO_FIELD.get(key.upper())
            if field:
                if not result[field]:
                    result[field] = value
            else:
                result['customFields'].append({'name': key, 'value': value})

    def write_field(self, audio, field, value):
        tag_name = FIELD_SCHEMA.get(field, {}).get('vorbis')
        if not tag_name:
            # Custom field: use the name supplied by the user.
            tag_name = field
        audio.pop(tag_name, None)
        audio[tag_name] = value

    def delete_field(self, audio, field):
        tag_name = FIELD_SCHEMA.get(field, {}).get('vorbis', field)
        audio.pop(tag_name, None)

    def get_picture(self, audio):
        if audio.tags is None:
            return None
        values = audio.tags.get(VORBIS_PICTURE_KEY)
        if not values:
            return None
        if not isinstance(values, list):
            values = [values]
        for value in values:
            try:
                picture = Picture(base64.b64decode(value))
            except Exception:
                continue
            if picture.data:
                return picture.data, picture.mime
        return None

    def set_picture(self, audio, image_data, mime_type):
        picture = Picture()
        picture.type = 3             # front cover
        picture.mime = resolve_image_mime(image_data, mime_type)
        picture.data = image_data
        encoded = base64.b64encode(picture.write()).decode('ascii')
        audio.pop(VORBIS_PICTURE_KEY, None)
        audio[VORBIS_PICTURE_KEY] = encoded

    def delete_picture(self, audio):
        if audio.tags is not None:
            audio.pop(VORBIS_PICTURE_KEY, None)


class FlacBackend(VorbisBackend):
    """Native FLAC files: same comments as OGG, native picture blocks."""

    family = 'flac'
    picture_storage = 'flac-block'

    def get_picture(self, audio):
        pictures = getattr(audio, 'pictures', None) or []
        # Prefer the front cover when several pictures are present.
        for picture in pictures:
            if picture.type == 3 and picture.data:
                return picture.data, picture.mime
        for picture in pictures:
            if picture.data:
                return picture.data, picture.mime
        return None

    def set_picture(self, audio, image_data, mime_type):
        picture = Picture()
        picture.type = 3
        picture.mime = resolve_image_mime(image_data, mime_type)
        picture.data = image_data
        audio.clear_pictures()
        audio.add_picture(picture)

    def delete_picture(self, audio):
        audio.clear_pictures()


ID3_BACKEND = Id3Backend()
FLAC_BACKEND = FlacBackend()
VORBIS_BACKEND = VorbisBackend()


def backend_for(audio):
    """Return the backend matching a loaded mutagen object, or None."""
    if isinstance(audio, MP3):
        return ID3_BACKEND
    if isinstance(audio, FLAC):
        return FLAC_BACKEND
    if isinstance(audio, (OggVorbis, OggOpus)):
        return VORBIS_BACKEND
    return None
