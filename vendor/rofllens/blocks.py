from __future__ import annotations

import math
import struct
from collections.abc import Collection, Iterator

from .errors import RoflParseError
from .models import ChunkRecord, NetworkBlock


def iter_framed_blocks(
    data: bytes | memoryview,
    *,
    chunk: ChunkRecord,
    include_payload: bool = False,
    packet_ids: Collection[int] | None = None,
) -> Iterator[NetworkBlock]:
    """Split a chunk using the marker framing documented by Mowokuma/ROFL-X."""
    view = memoryview(data)
    cursor = 0
    timestamp = 0.0
    packet_id = 0
    param = 0

    while cursor < len(view):
        block_offset = cursor
        marker = view[cursor]
        cursor += 1

        if marker & 0x80:
            _need(view, cursor, 1, block_offset, chunk)
            timestamp += view[cursor] * 0.001
            cursor += 1
        else:
            _need(view, cursor, 4, block_offset, chunk)
            timestamp = struct.unpack_from("<f", view, cursor)[0]
            cursor += 4
        if not math.isfinite(timestamp) or timestamp < 0:
            raise RoflParseError(
                "BLOCK_TIMESTAMP_INVALID",
                "block timestamp is negative or non-finite",
                offset=chunk.body_offset + block_offset,
                context=f"chunk {chunk.chunk_id} stream {chunk.stream_name}",
            )

        if marker & 0x10:
            _need(view, cursor, 1, block_offset, chunk)
            length = view[cursor]
            cursor += 1
        else:
            _need(view, cursor, 4, block_offset, chunk)
            length = struct.unpack_from("<I", view, cursor)[0]
            cursor += 4

        if not marker & 0x40:
            _need(view, cursor, 2, block_offset, chunk)
            packet_id = struct.unpack_from("<H", view, cursor)[0]
            cursor += 2

        if marker & 0x20:
            _need(view, cursor, 1, block_offset, chunk)
            param = (param + view[cursor]) & 0xFFFFFFFF
            cursor += 1
        else:
            _need(view, cursor, 4, block_offset, chunk)
            param = struct.unpack_from("<I", view, cursor)[0]
            cursor += 4

        _need(view, cursor, length, block_offset, chunk)
        payload_view = view[cursor : cursor + length]
        cursor += length
        if packet_ids is not None and packet_id not in packet_ids:
            continue
        yield NetworkBlock(
            stream=chunk.stream_name,
            stream_id=chunk.stream,
            chunk_id=chunk.chunk_id,
            block_offset=block_offset,
            timestamp=timestamp,
            packet_id=packet_id,
            param=param,
            payload_length=length,
            payload=bytes(payload_view) if include_payload else None,
        )


def _need(
    view: memoryview,
    cursor: int,
    size: int,
    block_offset: int,
    chunk: ChunkRecord,
) -> None:
    if cursor + size > len(view):
        raise RoflParseError(
            "BLOCK_TRUNCATED",
            f"block needs {size} bytes but only {len(view) - cursor} remain",
            offset=chunk.body_offset + block_offset,
            context=f"chunk {chunk.chunk_id} stream {chunk.stream_name}",
        )
