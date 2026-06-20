import sys
import importlib.util
from pathlib import Path
from logger_config import log_info, log_error, log_warning
from addon_base import MetadataFetcher

class PluginManager:
    def __init__(self, addons_dir="addons"):
        self.addons_dir = Path(addons_dir)
        self.fetchers = {}

    def discover_plugins(self, reload=False):
        if reload:
            log_info("Reloading all plugins...")
            self.fetchers.clear()   # clear registered classes
        self.addons_dir.mkdir(exist_ok=True)
        log_info(f"Scanning directory: {self.addons_dir.absolute()}")
        # List all files and subdirectories
        all_items = list(self.addons_dir.glob("*"))
        log_info(f"Total items found: {len(all_items)}")

        for file_path in self.addons_dir.rglob("*.py"):
            if file_path.name.startswith("_"):
                continue
            
            module_name = file_path.stem
            log_info(f"Found module: {module_name}")

            # ---- CLEANUP: remove old module from cache ----
            if module_name in sys.modules:
                log_info(f"Removing cached module: {module_name}")
                del sys.modules[module_name]

            # Now load fresh
            try:
                spec = importlib.util.spec_from_file_location(module_name, file_path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)   # this executes the file
                log_info(f"Successfully executed module: {module_name}")
            except Exception as e:
                log_error(f"Failed to load {file_path.name}: {e}")
                continue   # Skip to the next file

            # Register classes
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (isinstance(attr, type) and 
                    issubclass(attr, MetadataFetcher) and 
                    attr is not MetadataFetcher):
                    self.fetchers[attr.id] = attr
                    log_info(f"Registered fetcher: '{attr.name}' (id: {attr.id})")

    def get_fetcher(self, fetcher_id: str):
        """Retrieve a fetcher class by its ID."""
        fetcher = self.fetchers.get(fetcher_id)
        if fetcher:
            log_info(f"Retrieved fetcher: {fetcher_id}")
        else:
            log_warning(f"Fetcher ID not found: {fetcher_id}")
        return fetcher

    def reload_plugins(self):
        self.discover_plugins(reload=True)