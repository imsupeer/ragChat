from unittest.mock import patch

import asyncio
import pytest

from ingestion.processor import stream_upload_to_disk


class SingleChunkUploadFile:
    def __init__(self, content: bytes) -> None:
        self.content = content
        self.read_calls = 0

    async def read(self, size: int = -1) -> bytes:
        self.read_calls += 1
        if self.read_calls > 1:
            return b""
        return self.content


def test_stream_upload_cleans_up_when_disk_write_fails(tmp_path):
    upload = SingleChunkUploadFile(b"partial write")

    with patch("ingestion.processor.open", side_effect=OSError("disk full")):
        with pytest.raises(OSError, match="disk full"):
            asyncio.run(
                stream_upload_to_disk(
                    upload,
                    filename="sample.txt",
                    target_dir=str(tmp_path),
                    max_bytes=1024,
                    chunk_bytes=64,
                )
            )

    assert list(tmp_path.glob("*")) == []
