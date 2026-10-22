"""Tag read/write backends grouped by tag family.

The app supports several containers, but they only use three tag models:

* ID3 (MP3, WAV, AIFF)
* native FLAC metadata blocks
* Vorbis comments

Keeping the per-family logic here means ``metadata_extractor`` and
``metadata_writer`` stay small, and a new format usually only needs a registry
entry plus, at most, a small backend override.
"""

import base64
import re

from mutagen.aiff import AIFF
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
from mutagen.mp4 import MP4, MP4Cover, MP4FreeForm
from mutagen.oggopus import OggOpus
from mutagen.oggvorbis import OggVorbis
from mutagen.wave import WAVE


MP4_FREEFORM_PREFIX = '----:com.apple.iTunes:'

# Canonical frontend field -> tag key per family. ``TXXX:NAME`` means the value
# is stored in a TXXX frame with that description. MP4 freeform atoms use the
# ``----:com.apple.iTunes:NAME`` form.
FIELD_SCHEMA = {
    'title': {'id3': 'TIT2', 'vorbis': 'TITLE', 'mp4': '©nam'},
    'album': {'id3': 'TALB', 'vorbis': 'ALBUM', 'mp4': '©alb'},
    'artist': {'id3': 'TPE1', 'vorbis': 'ARTIST', 'mp4': '©ART'},
    'albumArtist': {'id3': 'TPE2', 'vorbis': 'ALBUMARTIST', 'mp4': 'aART'},
    'trackNumber': {'id3': 'TRCK', 'vorbis': 'TRACKNUMBER', 'mp4': 'trkn'},
    'diskNumber': {'id3': 'TPOS', 'vorbis': 'DISCNUMBER', 'mp4': 'disk'},
    'date': {'id3': 'TDRC', 'vorbis': 'DATE', 'mp4': '©day'},
    'genre': {'id3': 'TCON', 'vorbis': 'GENRE', 'mp4': '©gen'},
    'comment': {'id3': 'COMM', 'vorbis': 'COMMENT', 'mp4': '©cmt'},
    'description': {'id3': 'TXXX:DESCRIPTION', 'vorbis': 'DESCRIPTION', 'mp4': 'desc'},
    'composer': {'id3': 'TCOM', 'vorbis': 'COMPOSER', 'mp4': '©wrt'},
    'publisher': {
        'id3': 'TPUB',
        'vorbis': 'PUBLISHER',
        'mp4': MP4_FREEFORM_PREFIX + 'PUBLISHER',
    },
    'releaseType': {
        'id3': 'TXXX:RELEASETYPE',
        'vorbis': 'RELEASETYPE',
        'mp4': MP4_FREEFORM_PREFIX + 'RELEASETYPE',
    },
    'lyrics': {'id3': 'SYLT', 'vorbis': 'LYRICS', 'mp4': '©lyr'},
    'unsyncedLyrics': {
        'id3': 'USLT',
        'vorbis': 'UNSYNCEDLYRICS',
        'mp4': MP4_FREEFORM_PREFIX + 'UNSYNCEDLYRICS',
    },
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

MP4_KEY_TO_FIELD = {}
MP4_FREEFORM_TO_FIELD = {}
for _field, _keys in FIELD_SCHEMA.items():
    _mp4_key = _keys.get('mp4')
    if not _mp4_key:
        continue
    if _mp4_key.startswith(MP4_FREEFORM_PREFIX):
        MP4_FREEFORM_TO_FIELD[_mp4_key[len(MP4_FREEFORM_PREFIX):].upper()] = _field
    else:
        MP4_KEY_TO_FIELD[_mp4_key] = _field

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


def parse_number_pair(value):
    """Parse ``"3/12"`` into an MP4 ``(3, 12)`` tuple, or None when empty."""
    text = str(value).strip()
    if not text:
        return None

    number, _, total = text.partition('/')

    def to_int(part):
        try:
            return max(0, min(int(part.strip()), 65535))
        except (TypeError, ValueError):
            return 0

    return (to_int(number), to_int(total))


def format_number_pair(values):
    """Format an MP4 ``trkn``/``disk`` value as ``"3/12"`` or ``"3"``."""
    if not values:
        return ''
    try:
        number, total = values[0]
    except (TypeError, ValueError):
        return ''
    if not number and not total:
        return ''
    return f"{number}/{total}" if total else str(number)


def mp4_freeform_name(key):
    """Return the user-facing name from a ``----:...:NAME`` atom key."""
    if not key.startswith('----:'):
        return key
    parts = key.split(':', 2)
    return parts[2] if len(parts) == 3 else ''


def decode_freeform_values(values):
    """Decode freeform atom values, which mutagen exposes as bytes."""
    decoded = []
    for value in values:
        try:
            decoded.append(bytes(value).decode('utf-8'))
        except (TypeError, UnicodeDecodeError):
            decoded.append(str(value))
    return '; '.join(decoded)


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

    def extract(self, audio, include_picture=True):
        result = empty_metadata()
        if audio.tags is not None:
            self.read_tags(audio, result)

        picture = self.get_picture(audio)
        if picture:
            if include_picture:
                image_data, mime = picture
                result['picture'] = _picture_uri(image_data, mime)
            else:
                result['hasPicture'] = True
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
    """ID3v2 tags used by MP3, WAV and AIFF files."""

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


class Mp4Backend(TagBackend):
    """MP4 atoms used by M4A/M4B (AAC and ALAC)."""

    family = 'mp4'
    supports_synced_lyrics = False
    picture_storage = 'mp4-atom'

    def _tags(self, audio):
        if audio.tags is None:
            audio.add_tags()
        return audio.tags

    def read_tags(self, audio, result):
        tags = audio.tags
        if tags is None:
            return

        for key, values in tags.items():
            if key == 'covr':
                continue
            if not isinstance(values, list):
                values = [values]

            if key in ('trkn', 'disk'):
                value = format_number_pair(values)
                field = MP4_KEY_TO_FIELD.get(key)
                if field and value and not result[field]:
                    result[field] = value
                continue

            if key.startswith('----:'):
                value = decode_freeform_values(values)
                if not value:
                    continue
                name = mp4_freeform_name(key)
                field = MP4_FREEFORM_TO_FIELD.get(name.upper())
                if field:
                    if not result[field]:
                        result[field] = value
                elif name:
                    result['customFields'].append({'name': name, 'value': value})
                continue

            value = '; '.join(str(v) for v in values)
            if not value:
                continue

            field = MP4_KEY_TO_FIELD.get(key)
            if field:
                if not result[field]:
                    result[field] = value
            else:
                result['customFields'].append({'name': key, 'value': value})

    def write_field(self, audio, field, value):
        tags = self._tags(audio)
        atom = FIELD_SCHEMA.get(field, {}).get('mp4')

        if atom is None:
            atom = MP4_FREEFORM_PREFIX + field

        if atom in ('trkn', 'disk'):
            tags.pop(atom, None)
            pair = parse_number_pair(value)
            if pair and (pair[0] or pair[1]):
                tags[atom] = [pair]
            return

        if atom.startswith('----:'):
            self._remove_freeform(tags, atom)
            tags[atom] = [MP4FreeForm(str(value).encode('utf-8'))]
            return

        tags[atom] = [str(value)]

    def delete_field(self, audio, field):
        tags = audio.tags
        if tags is None:
            return

        atom = FIELD_SCHEMA.get(field, {}).get('mp4')
        if atom is None:
            self._remove_freeform(tags, MP4_FREEFORM_PREFIX + field)
        elif atom.startswith('----:'):
            self._remove_freeform(tags, atom)
        else:
            tags.pop(atom, None)

    @staticmethod
    def _remove_freeform(tags, full_key):
        target = mp4_freeform_name(full_key).upper()
        for key in list(tags.keys()):
            if key.startswith('----:') and mp4_freeform_name(key).upper() == target:
                del tags[key]

    def get_picture(self, audio):
        if audio.tags is None:
            return None
        covers = audio.tags.get('covr')
        if not covers:
            return None

        cover = covers[0]
        image_data = bytes(cover)
        if cover.imageformat == MP4Cover.FORMAT_PNG:
            mime = 'image/png'
        elif cover.imageformat == MP4Cover.FORMAT_JPEG:
            mime = 'image/jpeg'
        else:
            mime = detect_image_mime(image_data)
        return image_data, mime

    def set_picture(self, audio, image_data, mime_type):
        tags = self._tags(audio)
        mime = resolve_image_mime(image_data, mime_type)
        imageformat = (
            MP4Cover.FORMAT_PNG
            if mime == 'image/png'
            else MP4Cover.FORMAT_JPEG
        )
        tags['covr'] = [MP4Cover(image_data, imageformat=imageformat)]

    def delete_picture(self, audio):
        if audio.tags is not None:
            audio.tags.pop('covr', None)

    def save(self, audio):
        if audio.tags is not None and not audio.tags:
            audio.delete()
        else:
            audio.save()


ID3_BACKEND = Id3Backend()
FLAC_BACKEND = FlacBackend()
VORBIS_BACKEND = VorbisBackend()
MP4_BACKEND = Mp4Backend()


def backend_for(audio):
    """Return the backend matching a loaded mutagen object, or None."""
    if isinstance(audio, (MP3, WAVE, AIFF)):
        return ID3_BACKEND
    if isinstance(audio, FLAC):
        return FLAC_BACKEND
    if isinstance(audio, (OggVorbis, OggOpus)):
        return VORBIS_BACKEND
    if isinstance(audio, MP4):
        return MP4_BACKEND
    return None
