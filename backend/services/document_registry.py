import json
import os
from typing import Dict, List, Optional


class DocumentRegistry:
    def __init__(self, registry_path: str) -> None:
        self.registry_path = registry_path
        self._ensure_file()

    def _ensure_file(self) -> None:
        directory = os.path.dirname(self.registry_path)
        if directory:
            os.makedirs(directory, exist_ok=True)

        if not os.path.exists(self.registry_path):
            with open(self.registry_path, "w", encoding="utf-8") as f:
                json.dump([], f, ensure_ascii=False, indent=2)

    def _read_all(self) -> List[Dict]:
        with open(self.registry_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _write_all(self, data: List[Dict]) -> None:
        with open(self.registry_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def add(self, entry: Dict) -> None:
        data = self._read_all()
        data.append(entry)
        self._write_all(data)

    def list_all(self) -> List[Dict]:
        return self._read_all()

    def get(self, document_id: str) -> Optional[Dict]:
        for item in self._read_all():
            if item["id"] == document_id:
                return item
        return None

    def remove(self, document_id: str) -> Optional[Dict]:
        data = self._read_all()
        target = None
        remaining = []

        for item in data:
            if item["id"] == document_id:
                target = item
            else:
                remaining.append(item)

        self._write_all(remaining)
        return target
