# addon_base.py
from abc import ABC
from typing import Dict, Any, List, Optional

class MetadataFetcher(ABC):
    name: str = "Unnamed Fetcher"
    id: str = "unnamed_fetcher"
    description: str = ""
    
    required_env_vars: List[str] = []

    # ---- Album methods ----
    def search_albums(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        raise NotImplementedError(f"{self.id} does not support album search")
    search_albums._default_implementation = True

    def fetch_album_metadata(self, album_id: str) -> Dict[str, Any]:
        raise NotImplementedError(f"{self.id} does not support album metadata fetch")
    fetch_album_metadata._default_implementation = True

    # ---- Song / Track methods ----
    def search_songs(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        raise NotImplementedError(f"{self.id} does not support song search")
    search_songs._default_implementation = True

    def fetch_song_metadata(self, song_id: str) -> Dict[str, Any]:
        raise NotImplementedError(f"{self.id} does not support song metadata fetch")
    fetch_song_metadata._default_implementation = True