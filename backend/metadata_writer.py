import os
from mutagen import File
from mutagen.id3 import ID3, TIT2, TALB, TPE1, TPE2, TRCK, TPOS, TYER, TCON, COMM, TCOM, TPUB, USLT
from mutagen.flac import FLAC
from mutagen.mp3 import MP3

# Field mapping for different file types
FIELD_MAPPING = {
    'mp3': {
        'title': 'TIT2',
        'album': 'TALB',
        'artist': 'TPE1',
        'albumArtist': 'TPE2',
        'track': 'TRCK',
        'disk': 'TPOS',
        'year': 'TYER',
        'genre': 'TCON',
        'comment': 'COMM',
        'composer': 'TCOM',
        'publisher': 'TPUB',
    },
    'flac': {
        'title': 'TITLE',
        'album': 'ALBUM',
        'artist': 'ARTIST',
        'albumArtist': 'ALBUMARTIST',
        'track': 'TRACKNUMBER',
        'disk': 'DISCNUMBER',
        'year': 'ORIGINALYEAR',
        'genre': 'GENRE',
        'comment': 'DESCRIPTION',
        'composer': 'COMPOSER',
        'publisher': 'PUBLISHER',
    }
}

def update_file_metadata(file_path, field, value):
    """Update a single metadata field in a file."""
    try:
        audio = File(file_path, easy=False)
        if audio is None:
            return False
        
        file_ext = os.path.splitext(file_path)[1].lower().replace('.', '')
        
        if file_ext == 'mp3':
            return update_mp3_metadata(file_path, field, value)
        elif file_ext == 'flac':
            return update_flac_metadata(file_path, field, value)
        else:
            return False
            
    except Exception as e:
        print(f"Error updating metadata for {file_path}: {e}")
        return False

def update_mp3_metadata(file_path, field, value):
    """Update ID3 tag in MP3 file."""
    try:
        # Load or create ID3 tags
        try:
            tags = ID3(file_path)
        except:
            tags = ID3()
        
        # Handle special fields
        if field == 'comment':
            # Remove existing comment frames and add new one
            tags.delall('COMM')
            tags.add(COMM(encoding=3, lang='eng', desc='', text=value))
        elif field == 'unsyncedLyrics' or field == 'lyrics':
            tags.delall('USLT')
            tags.add(USLT(encoding=3, lang='eng', desc='', text=value))
        elif field in FIELD_MAPPING['mp3']:
            frame_id = FIELD_MAPPING['mp3'][field]
            tags.delall(frame_id)
            
            # Create appropriate frame based on field
            if frame_id == 'COMM':
                tags.add(COMM(encoding=3, lang='eng', desc='', text=value))
            else:
                frame_class = globals().get(frame_id)
                if frame_class:
                    tags.add(frame_class(encoding=3, text=value))
        
        # Save tags
        tags.save(file_path)
        return True
        
    except Exception as e:
        print(f"Error updating MP3 metadata: {e}")
        return False

def update_flac_metadata(file_path, field, value):
    """Update Vorbis comment in FLAC file."""
    try:
        audio = FLAC(file_path)
        
        if field in FIELD_MAPPING['flac']:
            tag_name = FIELD_MAPPING['flac'][field]
            # Remove existing tag and add new one
            audio.pop(tag_name)
            audio[tag_name] = value
        elif field == 'comment':
            audio.pop('DESCRIPTION')
            audio['DESCRIPTION'] = value
        elif field == 'lyrics':
            audio.pop('LYRICS')
            audio['LYRICS'] = value
        elif field == 'unsyncedLyrics':
            audio.pop('UNSYNCEDLYRICS')
            audio['UNSYNCEDLYRICS'] = value
        else:
            # For custom fields, use the field name as tag
            audio[field] = value
        
        audio.save()
        return True
        
    except Exception as e:
        print(f"Error updating FLAC metadata: {e}")
        return False

def update_folder_metadata(folder_path, field, value):
    """Update a metadata field for all audio files in a folder."""
    results = {
        'total': 0,
        'updated': 0,
        'failed': 0,
        'failed_files': []
    }
    
    for root, dirs, files in os.walk(folder_path):
        for file in files:
            if file.lower().endswith(('.mp3', '.flac')):
                results['total'] += 1
                file_path = os.path.join(root, file)
                
                if update_file_metadata(file_path, field, value):
                    results['updated'] += 1
                else:
                    results['failed'] += 1
                    results['failed_files'].append(file_path)
    
    return results