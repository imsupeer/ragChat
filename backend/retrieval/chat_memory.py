from collections import defaultdict
from typing import Dict, List


class InMemoryChatHistory:
    def __init__(self) -> None:
        self._store: Dict[str, List[dict]] = defaultdict(list)

    def append(self, session_id: str, role: str, content: str) -> None:
        self._store[session_id].append({"role": role, "content": content})

    def get(self, session_id: str) -> List[dict]:
        return self._store.get(session_id, [])

    def clear(self, session_id: str) -> None:
        self._store.pop(session_id, None)
