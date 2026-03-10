import os
import re
from mutagen import File
from mutagen.id3 import ID3, TIT2, TALB, TPE1, TPE2, TRCK, TPOS, TYER, TCON, COMM, TCOM, TPUB, USLT, APIC, SYLT, Encoding
from mutagen.flac import FLAC, Picture
from mutagen.mp3 import MP3
from logger_config import log_error, log_info

# Field mapping for different file types
FIELD_MAPPING = {
    'mp3': {
        'title': 'TIT2',
        'album': 'TALB',
        'artist': 'TPE1',
        'albumArtist': 'TPE2',
        'track': 'TRCK',
        'disk': 'TPOS',
        'year': 'TDRC',
        'genre': 'TCON',
        'comment': 'COMM',
        'composer': 'TCOM',
        'publisher': 'TPUB',
        'unsyncedLyrics': 'USLT',
        'lyrics': 'SYLT'
    },
    'flac': {
        'title': 'TITLE',
        'album': 'ALBUM',
        'artist': 'ARTIST',
        'albumArtist': 'ALBUMARTIST',
        'track': 'TRACKNUMBER',
        'disk': 'DISCNUMBER',
        'year': 'DATE',
        'genre': 'GENRE',
        'comment': 'COMMENT',
        'description': 'DESCRIPTION',
        'composer': 'COMPOSER',
        'publisher': 'PUBLISHER',
        'unsyncedLyrics': 'UNSYNCEDLYRICS',
        'lyrics': 'LYRICS',
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
        log_error(f"Error updating metadata for {file_path}: {e}")
        return False

def update_mp3_metadata(file_path, field, value):
    """Update ID3 tag in MP3 file."""
    try:
        log_info(f"File: {file_path}")
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
            log_info(f"Edited COMM frame")

        elif field == 'unsyncedLyrics':
            tags.delall('USLT')
            tags.add(USLT(encoding=3, lang='eng', desc='', text=value))    
            log_info(f"Edited USLT frame")  

        # SYLT frame logic - CORRECT FOR NAVIDROME
        elif field == 'lyrics':
            tags.delall('SYLT')
            
            # Get sample rate from MP3
            mp3 = MP3(file_path)
            sample_rate = mp3.info.sample_rate if mp3.info.sample_rate else 44100
            
            # Convert SYLT lines to events with samples (not milliseconds)
            lines = value.split('\n')
            events = []

            for line in lines:
                # line format: "[MM:SS.ss] text"
                m = re.match(r'^\[(\d{2}):(\d{2}\.\d{2})\](.*)', line)
                if m:
                    minutes = int(m.group(1))
                    seconds = float(m.group(2))
                    text = m.group(3).strip()
                    
                    # Convert to absolute seconds
                    abs_seconds = minutes * 60 + seconds
                    
                    samples = int(round(abs_seconds * sample_rate))
                    
                    if text:
                        events.append((text, samples))
            
            if events:
                sylt = SYLT(
                    encoding=Encoding.UTF8, 
                    lang='eng', 
                    format=1,
                    type=1,
                    desc='', 
                    text=events
                )
                tags.add(sylt)
                log_info(f"Added SYLT frame with {len(events)} events")

        elif field in FIELD_MAPPING['mp3']:
            frame_id = FIELD_MAPPING['mp3'][field]
            tags.delall(frame_id)

            # Create appropriate frame based on field
            if frame_id == 'COMM':
                tags.add(COMM(encoding=3, lang='eng', desc='', text=value))
                log_info(f"Edited {frame_id} frame, new value:{value}")
            
            else:
                # Get the frame class from globals() and create the frame
                frame_class = globals().get(frame_id)
                if frame_class:
                    tags.add(frame_class(encoding=3, text=value))
                    log_info(f"Edited {frame_id} frame, new value:{value}")
                else:
                    # If frame class not found in globals, use TXXX for custom fields
                    # This handles cases where the field name isn't a standard ID3 frame
                    from mutagen.id3 import TXXX
                    tags.add(TXXX(encoding=3, desc=frame_id, text=value))
                    log_info(f"Edited {frame_id} as TXXX frame, new value:{value}")

        else:
            # For fields not in mapping, use the field name directly as TXXX descriptor
            tags.delall(field)
            from mutagen.id3 import TXXX
            tags.add(TXXX(encoding=3, desc=field, text=value))
            log_info(f"Edited {field} as TXXX frame, new value:{value}")
        
        # Save tags
        tags.save(file_path)
        log_info("Changes saved")
        return True
        
    except Exception as e:
        log_error(f"Error updating MP3 metadata: {e}")
        return False

def update_flac_metadata(file_path, field, value):
    """Update Vorbis comment in FLAC file."""
    try:
        log_info(f"File: {file_path}")
        audio = FLAC(file_path)

        if field in FIELD_MAPPING['flac']:
            # Remove existing tag and add new one
            tag_name = FIELD_MAPPING['flac'][field]
            audio.pop(tag_name, None)  # None is the default if key doesn't exist
            audio[tag_name] = value
            log_info(f"Edited {tag_name} comment, new value:{value}")
        elif field == 'comment':
            audio.pop('COMMENT', None)  # None is the default if key doesn't exist
            audio['COMMENT'] = value
            log_info(f"Edited COMMENT comment")
        elif field == 'description':
            audio.pop('DESCRIPTION', None)  # None is the default if key doesn't exist
            audio['DESCRIPTION'] = value
            log_info(f"Edited DESCRIPTION comment")
        elif field == 'lyrics':
            audio.pop('LYRICS', None)  # None is the default if key doesn't exist
            audio['LYRICS'] = value
            log_info(f"Edited LYRICS comment")
        elif field == 'unsyncedlyrics':
            audio.pop('UNSYNCEDLYRICS', None)  # None is the default if key doesn't exist
            audio['UNSYNCEDLYRICS'] = value
            log_info(f"Edited UNSYNCEDLYRICS comment, new value:{value}")
        else:
            # For custom fields, use the field name as tag
            audio[field] = value
            log_info(f"Edited {field} comment, new value:{value}")

        audio.save()
        log_info("Changes saved")
        return True
        
    except Exception as e:
        log_error(f"Error updating FLAC metadata: {e}")
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

def update_file_picture(file_path, image_data, mime_type=None):
    """Update cover art in a file."""
    try:
        file_ext = os.path.splitext(file_path)[1].lower().replace('.', '')
        
        if file_ext == 'mp3':
            return update_mp3_picture(file_path, image_data, mime_type)
        elif file_ext == 'flac':
            return update_flac_picture(file_path, image_data)
        else:
            return False
            
    except Exception as e:
        log_error(f"Error updating picture for {file_path}: {e}")
        return False

def update_mp3_picture(file_path, image_data, mime_type=None):
    """Update APIC frame in MP3 file."""
    try:
        log_info(f"File: {file_path}")
        # Load or create ID3 tags
        try:
            tags = ID3(file_path)
        except:
            tags = ID3()
        
        # Remove existing APIC frames
        tags.delall('APIC')
        
        # Determine mime type if not provided
        if not mime_type:
            # Try to detect from image data
            if image_data.startswith(b'\xff\xd8'):
                mime_type = 'image/jpeg'
            elif image_data.startswith(b'\x89PNG\r\n\x1a\n'):
                mime_type = 'image/png'
            else:
                mime_type = 'image/jpeg'  # default
        
        # Add new picture
        tags.add(APIC(
            encoding=3,  # UTF-8
            mime=mime_type,
            type=3,  # Cover (front)
            desc='Cover',
            data=image_data
        ))
        
        tags.save(file_path)
        log_info("Updated APIC frame")
        return True
        
    except Exception as e:
        log_error(f"Error updating MP3 picture: {e}")
        return False

def update_flac_picture(file_path, image_data):
    """Update picture block in FLAC file."""
    try:
        log_info(f"File: {file_path}")
        audio = FLAC(file_path)
        
        # Create picture
        picture = Picture()
        
        # Detect image type
        if image_data.startswith(b'\xff\xd8'):
            picture.mime = 'image/jpeg'
            picture.type = 3  # Cover (front)
        elif image_data.startswith(b'\x89PNG\r\n\x1a\n'):
            picture.mime = 'image/png'
            picture.type = 3
        else:
            picture.mime = 'image/jpeg'
            picture.type = 3
        
        picture.data = image_data
        
        # Add picture to FLAC file
        audio.clear_pictures()
        audio.add_picture(picture)
        audio.save()
        log_info("Updated coveart")
        
        return True
        
    except Exception as e:
        log_error(f"Error updating FLAC picture: {e}")
        return False

def update_folder_pictures(folder_path, image_data, mime_type=None):
    """Update cover art for all audio files in a folder."""
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
                
                if update_file_picture(file_path, image_data, mime_type):
                    results['updated'] += 1
                else:
                    results['failed'] += 1
                    results['failed_files'].append(file_path)
    
    return results

def update_folder_metadata_only_current(folder_path, field, value):
    """Update a metadata field for all audio files in a folder (current folder only, no subfolders)."""
    results = {
        'total': 0,
        'updated': 0,
        'failed': 0,
        'failed_files': []
    }
    
    # Only process files directly in the folder, not subfolders
    for file in os.listdir(folder_path):
        file_path = os.path.join(folder_path, file)
        if os.path.isfile(file_path) and file.lower().endswith(('.mp3', '.flac')):
            results['total'] += 1
            
            if update_file_metadata(file_path, field, value):
                results['updated'] += 1
            else:
                results['failed'] += 1
                results['failed_files'].append(file_path)
    
    return results

def update_folder_pictures_only_current(folder_path, image_data, mime_type=None):
    """Update cover art for all audio files in a folder (current folder only, no subfolders)."""
    results = {
        'total': 0,
        'updated': 0,
        'failed': 0,
        'failed_files': []
    }
    
    # Only process files directly in the folder, not subfolders
    for file in os.listdir(folder_path):
        file_path = os.path.join(folder_path, file)
        if os.path.isfile(file_path) and file.lower().endswith(('.mp3', '.flac')):
            results['total'] += 1
            
            if update_file_picture(file_path, image_data, mime_type):
                results['updated'] += 1
            else:
                results['failed'] += 1
                results['failed_files'].append(file_path)
    
    return results

def delete_metadata_field(file_path, field):
    """Delete a specific metadata field from a file."""
    try:
        file_ext = os.path.splitext(file_path)[1].lower().replace('.', '')
        
        if file_ext == 'mp3':
            return delete_mp3_field(file_path, field)
        elif file_ext == 'flac':
            return delete_flac_field(file_path, field)
        else:
            return False
            
    except Exception as e:
        log_error(f"Error deleting field from {file_path}: {e}")
        return False

def delete_mp3_field(file_path, field):
    """Delete a specific ID3 tag from MP3 file."""
    try:
        tags = ID3(file_path)
        
        # Map field to frame ID
        if field == 'comment':
            tags.delall('COMM')
        elif field == 'unsyncedLyrics' or field == 'lyrics':
            tags.delall('USLT')
        elif field in FIELD_MAPPING['mp3']:
            frame_id = FIELD_MAPPING['mp3'][field]
            tags.delall(frame_id)
        else:
            # For custom fields, try to delete as is
            tags.delall(field)
        
        # If no frames left, remove the entire tag structure
        if not tags:
            tags.delete()
        
        tags.save(file_path)
        return True
        
    except Exception as e:
        log_error(f"Error deleting MP3 field: {e}")
        return False

def delete_flac_field(file_path, field):
    """Delete a specific Vorbis comment from FLAC file."""
    try:
        audio = FLAC(file_path)
        
        # Map field to tag name
        if field == 'comment':
            audio.pop('COMMENT', None)
        elif field == 'description':
            audio.pop('DESCRIPTION', None)
        elif field == 'lyrics':
            audio.pop('LYRICS', None)
        elif field == 'unsyncedLyrics':
            audio.pop('UNSYNCEDLYRICS', None)
        elif field in FIELD_MAPPING['flac']:
            tag_name = FIELD_MAPPING['flac'][field]
            audio.pop(tag_name, None)
        else:
            # For custom fields, use the field name as tag
            audio.pop(field, None)
        
        audio.save()
        return True
        
    except Exception as e:
        log_error(f"Error deleting FLAC field: {e}")
        return False

def delete_cover_art(file_path):
    """Delete cover art from a file."""
    try:
        file_ext = os.path.splitext(file_path)[1].lower().replace('.', '')
        
        if file_ext == 'mp3':
            return delete_mp3_cover_art(file_path)
        elif file_ext == 'flac':
            return delete_flac_cover_art(file_path)
        else:
            return False
            
    except Exception as e:
        log_error(f"Error deleting cover art from {file_path}: {e}")
        return False

def delete_mp3_cover_art(file_path):
    """Delete APIC frames from MP3 file."""
    try:
        tags = ID3(file_path)
        tags.delall('APIC')
        
        if not tags:
            tags.delete()
        else:
            tags.save(file_path)
        
        return True
        
    except Exception as e:
        log_error(f"Error deleting MP3 cover art: {e}")
        return False

def delete_flac_cover_art(file_path):
    """Delete pictures from FLAC file."""
    try:
        audio = FLAC(file_path)
        audio.clear_pictures()
        audio.save()
        return True
        
    except Exception as e:
        log_error(f"Error deleting FLAC cover art: {e}")
        return False
    
def delete_field_from_folder(folder_path, field, recursive=False):
    """Delete a metadata field from all audio files in a folder.
    
    Args:
        folder_path: Path to the folder
        field: Field name to delete
        recursive: Whether to include subfolders
    
    Returns:
        dict: Statistics about the operation
    """
    updated = 0
    failed = 0
    total = 0
    
    # Walk through folder
    for root, dirs, files in os.walk(folder_path):
        for file in files:
            if file.lower().endswith(('.mp3', '.flac')):
                total += 1
                file_path = os.path.join(root, file)
                try:
                    if delete_metadata_field(file_path, field):
                        updated += 1
                    else:
                        failed += 1
                except Exception as e:
                    print(f"Error deleting field from {file_path}: {e}")
                    failed += 1
        
        # If not recursive, break after first iteration
        if not recursive:
            break
    
    return {
        'updated': updated,
        'failed': failed,
        'total': total
    }