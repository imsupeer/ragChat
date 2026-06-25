import json
import os
import threading
from typing import Dict, List, Optional


class DocumentRegistry:
    def __init__(self, registry_path: str) -> None:
        self.registry_path = registry_path
        self._lock = threading.Lock()
        self._ensure_file()

    def _ensure_file(self) -> None:
        directory = os.path.dirname(self.registry_path)
        if directory:
            os.makedirs(directory, exist_ok=True)

        if not os.path.exists(self.registry_path):
            self._write_all_unlocked([])

    def _read_all_unlocked(self) -> List[Dict]:
        with open(self.registry_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _write_all_unlocked(self, data: List[Dict]) -> None:
        directory = os.path.dirname(self.registry_path) or "."
        os.makedirs(directory, exist_ok=True)

        temp_path = f"{self.registry_path}.tmp"
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())

        os.replace(temp_path, self.registry_path)

    def _read_all(self) -> List[Dict]:
        with self._lock:
            return self._read_all_unlocked()

    def _write_all(self, data: List[Dict]) -> None:
        with self._lock:
            self._write_all_unlocked(data)

    def add(self, entry: Dict) -> None:
        with self._lock:
            data = self._read_all_unlocked()
            data.append(entry)
            self._write_all_unlocked(data)

    def list_all(self) -> List[Dict]:
        return self._read_all()

    def get(self, document_id: str) -> Optional[Dict]:
        for item in self._read_all():
            if item["id"] == document_id:
                return item
        return None

    def remove(self, document_id: str) -> Optional[Dict]:
        with self._lock:
            data = self._read_all_unlocked()
            target = None
            remaining = []

            for item in data:
                if item["id"] == document_id:
                    target = item
                else:
                    remaining.append(item)

            self._write_all_unlocked(remaining)
            return target

    def update(self, document_id: str, updates: Dict) -> Optional[Dict]:
        with self._lock:
            data = self._read_all_unlocked()
            updated = None
            for item in data:
                if item["id"] == document_id:
                    item.update(updates)
                    updated = dict(item)
                    break
            if updated is not None:
                self._write_all_unlocked(data)
            return updated
