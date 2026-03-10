import mutagen
import os
import base64
import re
from mutagen import File
from mutagen.id3 import ID3, TextFrame, USLT, APIC, SYLT, TXXX
from mutagen.flac import FLAC

def get_tag_text(frame):
    """Extract readable text from an ID3 frame or a Vorbis comment value."""
    if hasattr(frame, 'text'):
        # Text frames (TIT2, TALB, etc.) and COMM
        return '; '.join(str(t) for t in frame.text)
    elif isinstance(frame, USLT):
        # Unsychronised lyrics
        return frame.text
    elif isinstance(frame, SYLT):
        # Handle this separately in extract_metadata
        return None
    elif isinstance(frame, TXXX):
        # For TXXX frames, we handle them separately in extract_metadata
        # to return the description as the field name
        return None
    elif isinstance(frame, list):
        # For FLAC (list of strings)
        return '; '.join(str(v) for v in frame)
    else:
        # Fallback
        return str(frame)

def format_sylt_timestamp(samples, sample_rate):
    """Convert samples to LRC timestamp format [MM:SS.ss]"""
    if sample_rate <= 0:
        return "[--:--.--]"
    
    seconds = samples / sample_rate
    minutes = int(seconds // 60)
    secs = seconds % 60
    return f"[{minutes:02d}:{secs:06.3f}]"

def extract_sylt_text(sylt_frame, sample_rate):
    """Extract synchronized lyrics from SYLT frame in LRC format"""
    if not sylt_frame or not hasattr(sylt_frame, 'text'):
        return ""
    
    lines = []
    for text, timestamp in sylt_frame.text:
        # Convert samples to timestamp
        timestamp_str = format_sylt_timestamp(timestamp, sample_rate)
        lines.append(f"{timestamp_str} {text}")
    
    return "\n".join(lines)

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

def get_sample_rate(audio):
    """Extract sample rate from audio file"""
    if hasattr(audio.info, 'sample_rate'):
        return audio.info.sample_rate
    return 44100  # Default fallback

def extract_metadata(filepath):
    audio = File(filepath, easy=False)
    if audio is None:
        return None

    # Get sample rate for SYLT conversion
    sample_rate = get_sample_rate(audio)

    result = {
        'title': '', 'album': '', 'artist': '', 'albumArtist': '', 'track': '', 'disk': '',
        'year': '', 'genre': '', 'comment': '', 'description': '',
        'lyrics': '', 'unsyncedLyrics': '', 'composer': '', 'publisher': '', 'releaseType': '',
        'customFields': []          # list of {name, value} for truly unknown tags
    }

    # Mapping from frontend field to possible tag keys (original case)
    field_map = {
        'title': ['TIT2', 'TITLE'],
        'album': ['TALB', 'ALBUM'],
        'artist': ['TPE1', 'ARTIST'],
        'albumArtist': ['TPE2', 'ALBUMARTIST'],
        'track': ['TRCK', 'TRACKNUMBER'],
        'disk': ['TPOS', 'DISCNUMBER'],
        'year': ['TDRC', 'DATE'],
        'genre': ['TCON', 'GENRE'],
        'comment': ['COMM', 'COMMENT'],
        'description': ['DESCRIPTION'],
        'lyrics': ['SYLT', 'LYRICS'],
        'unsyncedLyrics': ['USLT', 'UNSYNCEDLYRICS'],
        'composer': ['TCOM', 'COMPOSER'],
        'publisher': ['TPUB', 'PUBLISHER'],
        'releaseType': ['TXXX:RELEASETYPE', 'RELEASETYPE']
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
                # Special handling for TXXX frames (custom user text frames)
                if isinstance(frame, TXXX):
                    if frame.desc and frame.text:
                        # Use the description as the field name, not "TXXX"
                        field_name = frame.desc
                        value = '; '.join(str(t) for t in frame.text)
                        # Check if this matches any known field
                        if field_name.upper() in key_to_field:
                            mapped_field = key_to_field[field_name.upper()]
                            if not result[mapped_field]:
                                result[mapped_field] = value
                        else:
                            result['customFields'].append({'name': field_name, 'value': value})
                    continue
                
                # Special handling for SYLT frames
                if isinstance(frame, SYLT):
                    # Extract synchronized lyrics in LRC format
                    lrc_text = extract_sylt_text(frame, sample_rate)
                    if lrc_text:
                        result['lyrics'] = lrc_text
                    continue
                
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
                        # For standard T* frames, use the frame ID as the name
                        result['customFields'].append({'name': key, 'value': value})
    else:
        # FLAC, Ogg, etc. – tags are dicts of lists
        for key, values in tags.items():
            # Check if this is a lyrics field
            upper_key = key.upper()
            value = '; '.join(str(v) for v in values)
            
            if not value:
                continue
                
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

    return result