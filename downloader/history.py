import json
import os
import threading
from datetime import datetime

APP_DATA_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "NhamAIO")
HISTORY_PATH = os.path.join(APP_DATA_DIR, "history.json")
CONFIG_PATH = os.path.join(APP_DATA_DIR, "config.json")
MAX_ENTRIES = 2000


class DownloadHistory:
    def __init__(self, path: str = None):
        self.path = path or HISTORY_PATH
        self._lock = threading.Lock()
        self._entries = self._load()

    def _load(self):
        try:
            if os.path.exists(self.path):
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    return data
        except Exception:
            pass
        return []

    def _save(self):
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self._entries[-MAX_ENTRIES:], f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def add(self, title: str = "", file_path: str = "", url: str = "",
            source: str = "", status: str = "Success", kind: str = "Video") -> dict:
        entry = {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "title": (title or "Unknown")[:200],
            "file": file_path or "",
            "url": url or "",
            "source": source or "",
            "status": status,
            "kind": kind,
        }
        with self._lock:
            self._entries.append(entry)
            self._save()
        return entry

    def entries(self) -> list:
        with self._lock:
            return list(self._entries)

    def remove_at(self, index: int):
        with self._lock:
            if 0 <= index < len(self._entries):
                self._entries.pop(index)
                self._save()

    def clear(self):
        with self._lock:
            self._entries = []
            self._save()


def load_config() -> dict:
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def save_config(cfg: dict):
    try:
        os.makedirs(APP_DATA_DIR, exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
