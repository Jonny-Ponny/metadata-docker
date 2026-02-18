import mutagen
import os
import base64
from mutagen import File
from mutagen.id3 import ID3, TextFrame, USLT, APIC, SYLT
from mutagen.flac import FLAC

def get_tag_text(frame):
    """Extract readable text from an ID3 frame or a Vorbis comment value."""
    if hasattr(frame, 'text'):
        # Text frames (TIT2, TALB, etc.) and COMM
        return '; '.join(str(t) for t in frame.text)
    elif isinstance(frame, USLT):
        # Unsychronised lyrics
        return frame.text
    elif isinstance(frame, list):
        # For FLAC (list of strings)
        return '; '.join(str(v) for v in frame)
    else:
        # Fallback
        return str(frame)

def extract_picture(audio):
    """Extract first picture as base64 data URI, or None."""
    picture_data = None
    mime = None

    if isinstance(audio, mutagen.mp3.MP3):
        # Look for APIC frames in ID3 tags
        for tag in audio.tags.values():
            if isinstance(tag, APIC):
                picture_data = tag.data
                mime = tag.mime
                break
    elif hasattr(audio, 'pictures') and audio.pictures:
        # FLAC, Ogg, etc.
        pic = audio.pictures[0]
        picture_data = pic.data
        mime = pic.mime

    if picture_data and mime:
        base64_str = base64.b64encode(picture_data).decode('utf-8')
        return f"data:{mime};base64,{base64_str}"
    return None


def extract_metadata(filepath):
    audio = File(filepath, easy=False)
    if audio is None:
        return None

    result = {
        'title': '', 'album': '', 'artist': '', 'track': '', 'disk': '',
        'year': '', 'genre': '', 'comment': '', 'description': '',
        'lyrics': '', 'unsyncedLyrics': '', 'composer': '', 'publisher': '',
        'customFields': []          # list of {name, value} for truly unknown tags
    }

    # Mapping from frontend field to possible tag keys (original case)
    field_map = {
        'title': ['TIT2', 'TITLE'],
        'album': ['TALB', 'ALBUM'],
        'artist': ['TPE1', 'ARTIST'],
        'track': ['TRCK', 'TRACKNUMBER'],
        'disk': ['TPOS', 'DISCNUMBER'],
        'year': ['TDRC', 'TDRL', 'TYER', 'DATE', 'ORIGINALYEAR'],
        'genre': ['TCON', 'GENRE'],
        'comment': ['COMM', 'COMMENT'],
        'description': ['DESCRIPTION'],
        'lyrics': ['SYLT', 'LYRICS'],
        'unsyncedLyrics': ['USLT', 'LYRICS'],
        'composer': ['TCOM', 'COMPOSER'],
        'publisher': ['TPUB', 'PUBLISHER']
    }

    # Build case‑insensitive lookup: uppercase key -> frontend field
    key_to_field = {}
    for field, keys in field_map.items():
        for key in keys:
            key_to_field[key.upper()] = field

    tags = audio.tags
    if tags is None:
        return result

    if isinstance(audio, mutagen.mp3.MP3):
        # ID3 tags
        for key in tags.keys():
            frames = tags.getall(key)
            for frame in frames:
                value = get_tag_text(frame)
                if not value:
                    continue
                upper_key = key.upper()
                if upper_key in key_to_field:
                    field = key_to_field[upper_key]
                    if not result[field]:
                        result[field] = value
                else:
                    # Add only text‑like frames as custom fields
                    if isinstance(frame, TextFrame) or key in ('COMM', 'USLT') or key.startswith('T'):
                        result['customFields'].append({'name': key, 'value': value})
    else:
        # FLAC, Ogg, etc. – tags are dicts of lists
        for key, values in tags.items():
            value = '; '.join(str(v) for v in values)
            if not value:
                continue
            upper_key = key.upper()
            if upper_key in key_to_field:
                field = key_to_field[upper_key]
                if not result[field]:
                    result[field] = value
            else:
                result['customFields'].append({'name': key, 'value': value})

    # Extract picture after processing tags
    picture_uri = extract_picture(audio)
    if picture_uri:
        result['picture'] = picture_uri

    # Fallbacks
    if not result['description'] and result['comment']:
        result['description'] = result['comment']
    if not result['unsyncedLyrics'] and result['lyrics']:
        result['unsyncedLyrics'] = result['lyrics']

    return result