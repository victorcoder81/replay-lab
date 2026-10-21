from __future__ import annotations

import hashlib
import json
import mmap
import struct
from collections import Counter
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import TYPE_CHECKING, Any

import zstandard

from .blocks import iter_framed_blocks
from .errors import RoflParseError
from .metadata import parse_metadata
from .models import (
    ChunkRecord,
    NetworkBlock,
    ReplayHeader,
    ReplaySummary,
    STREAM_NAMES,
)

if TYPE_CHECKING:
    from .decoders.base import DecoderContext
    from .decoders.registry import DecoderRegistry
    from .models import TypedEvent, UnknownEvent


CHUNK_HEADER = struct.Struct("<IBIII")


class ReplayReader:
    """Lazy, read-only reader for a ROFL v2 file."""

    def __init__(
        self,
        path: Path,
        handle: Any,
        mapped: mmap.mmap,
        *,
        header: ReplayHeader,
        metadata: Any,
        metadata_offset: int,
        metadata_length: int,
        signature_offset: int,
    ) -> None:
        self.path = path
        self._handle = handle
        self._mapped = mapped
        self.header = header
        self.metadata = metadata
        self.metadata_offset = metadata_offset
        self.metadata_length = metadata_length
        self.signature_offset = signature_offset
        self._chunks: tuple[ChunkRecord, ...] | None = None
        self._sha256: str | None = None

    @classmethod
    def open(cls, path: str | Path) -> "ReplayReader":
        file_path = Path(path).expanduser().resolve()
        if not file_path.is_file():
            raise RoflParseError("FILE_NOT_FOUND", "replay file does not exist")
        handle = file_path.open("rb")
        try:
            if handle.seek(0, 2) < 32:
                raise RoflParseError("FILE_TOO_SMALL", "replay file is too small")
            file_size = handle.tell()
            mapped = mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ)
            try:
                header = _parse_header(mapped)
                metadata_length = struct.unpack_from("<I", mapped, file_size - 4)[0]
                metadata_offset = file_size - 4 - metadata_length
                signature_offset = metadata_offset - 256
                if signature_offset < header.header_size:
                    raise RoflParseError(
                        "BOUNDARY_INVALID",
                        "metadata length leaves no valid signature and chunk region",
                    )
                metadata = parse_metadata(
                    bytes(mapped[metadata_offset : file_size - 4]),
                    offset=metadata_offset,
                )
                return cls(
                    file_path,
                    handle,
                    mapped,
                    header=header,
                    metadata=metadata,
                    metadata_offset=metadata_offset,
                    metadata_length=metadata_length,
                    signature_offset=signature_offset,
                )
            except Exception:
                mapped.close()
                raise
        except Exception:
            handle.close()
            raise

    def close(self) -> None:
        if self._mapped is not None:
            self._mapped.close()
            self._mapped = None  # type: ignore[assignment]
        if self._handle is not None:
            self._handle.close()
            self._handle = None

    def __enter__(self) -> "ReplayReader":
        return self

    def __exit__(self, _type: object, _value: object, _traceback: object) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except (BufferError, OSError):
            pass

    @property
    def sha256(self) -> str:
        if self._sha256 is None:
            self._sha256 = hashlib.sha256(self._mapped).hexdigest()
        return self._sha256

    def chunks(self, *, verify: bool = False) -> Iterator[ChunkRecord]:
        if self._chunks is None:
            self._chunks = tuple(self._walk_chunks())
        if verify:
            for chunk in self._chunks:
                self.read_chunk_body(chunk, verify=True)
        yield from self._chunks

    def _walk_chunks(self) -> Iterator[ChunkRecord]:
        cursor = self.header.header_size
        while cursor < self.signature_offset:
            if cursor + CHUNK_HEADER.size > self.signature_offset:
                raise RoflParseError("CHUNK_HEADER_TRUNCATED", "chunk header is truncated", offset=cursor)
            chunk_id, slot, stream_raw, raw_size, compressed_size = (
                CHUNK_HEADER.unpack_from(self._mapped, cursor)
            )
            stream = (stream_raw >> 24) & 0xFF
            body_offset = cursor + CHUNK_HEADER.size
            stored_size = compressed_size or raw_size
            body_end = body_offset + stored_size
            if body_end > self.signature_offset:
                raise RoflParseError(
                    "CHUNK_OUT_OF_BOUNDS",
                    f"chunk {chunk_id} body extends beyond chunk region",
                    offset=cursor,
                    context=STREAM_NAMES.get(stream, f"stream {stream}"),
                )
            record = ChunkRecord(
                offset=cursor,
                body_offset=body_offset,
                chunk_id=chunk_id,
                slot=slot,
                stream=stream,
                raw_size=raw_size,
                compressed_size=compressed_size,
            )
            yield record
            cursor = body_end
        if cursor != self.signature_offset:
            raise RoflParseError("CHUNK_BOUNDARY_MISMATCH", "chunk walk did not reach signature")

    def read_chunk_body(self, chunk: ChunkRecord, *, verify: bool = False) -> bytes:
        stored = self._mapped[chunk.body_offset : chunk.body_offset + chunk.stored_size]
        if chunk.compressed_size:
            try:
                decoded = zstandard.ZstdDecompressor().decompress(
                    stored,
                    max_output_size=chunk.raw_size,
                )
            except zstandard.ZstdError as exc:
                raise RoflParseError(
                    "ZSTD_INVALID",
                    str(exc),
                    offset=chunk.body_offset,
                    context=f"chunk {chunk.chunk_id}",
                ) from exc
        else:
            decoded = stored
        if verify or len(decoded) != chunk.raw_size:
            if len(decoded) != chunk.raw_size:
                raise RoflParseError(
                    "CHUNK_SIZE_MISMATCH",
                    f"decoded {len(decoded)} bytes, expected {chunk.raw_size}",
                    offset=chunk.body_offset,
                    context=f"chunk {chunk.chunk_id}",
                )
        return decoded

    def iter_blocks(
        self,
        *,
        streams: Iterable[str | int] | None = None,
        opcodes: Iterable[int] | None = None,
        include_payload: bool = False,
        verify: bool = True,
    ) -> Iterator[NetworkBlock]:
        selected = _normalize_streams(streams)
        selected_opcodes = _normalize_opcodes(opcodes)
        for chunk in self.chunks(verify=False):
            if selected is not None and chunk.stream not in selected:
                continue
            body = self.read_chunk_body(chunk, verify=verify)
            yield from iter_framed_blocks(
                body,
                chunk=chunk,
                include_payload=include_payload,
                packet_ids=selected_opcodes,
            )

    def histogram(self, *, verify: bool = True, top: int = 50) -> dict[str, Any]:
        stream_blocks: Counter[int] = Counter()
        opcode_counts: Counter[int] = Counter()
        payload_bytes: Counter[int] = Counter()
        first_timestamp: float | None = None
        last_timestamp: float | None = None
        for block in self.iter_blocks(include_payload=False, verify=verify):
            stream_blocks[block.stream_id] += 1
            opcode_counts[block.packet_id] += 1
            payload_bytes[block.packet_id] += block.payload_length
            first_timestamp = (
                block.timestamp
                if first_timestamp is None
                else min(first_timestamp, block.timestamp)
            )
            last_timestamp = (
                block.timestamp
                if last_timestamp is None
                else max(last_timestamp, block.timestamp)
            )
        top_opcodes = tuple(
            {
                "id": packet_id,
                "hex": f"0x{packet_id:04x}",
                "count": count,
                "payloadBytes": payload_bytes[packet_id],
                "averagePayloadBytes": round(payload_bytes[packet_id] / count, 3),
            }
            for packet_id, count in opcode_counts.most_common(top)
        )
        return {
            "blockCount": sum(stream_blocks.values()),
            "streamBlocks": {
                STREAM_NAMES.get(stream, str(stream)): count
                for stream, count in sorted(stream_blocks.items())
            },
            "firstTimestamp": first_timestamp,
            "lastTimestamp": last_timestamp,
            "distinctOpcodes": len(opcode_counts),
            "topOpcodes": list(top_opcodes),
        }

    def iter_events(
        self,
        registry: "DecoderRegistry",
        context: "DecoderContext",
        *,
        streams: Iterable[str | int] | None = None,
        opcodes: Iterable[int] | None = None,
    ) -> Iterator["TypedEvent | UnknownEvent"]:
        for block in self.iter_blocks(
            streams=streams,
            opcodes=opcodes,
            include_payload=True,
        ):
            yield registry.decode(block, context)

    def summary(self, *, verify: bool = False, analyze_blocks: bool = False) -> ReplaySummary:
        chunk_list = tuple(self.chunks(verify=verify and not analyze_blocks))
        stream_chunks = Counter(chunk.stream for chunk in chunk_list)
        transport = self.histogram(verify=verify) if analyze_blocks else {}
        return ReplaySummary(
            path=str(self.path),
            file_size=self._mapped.size(),
            sha256=self.sha256,
            header=self.header,
            metadata=self.metadata,
            chunk_count=len(chunk_list),
            stream_chunks={
                STREAM_NAMES.get(stream, str(stream)): count
                for stream, count in sorted(stream_chunks.items())
            },
            compressed_bytes=sum(chunk.compressed_size for chunk in chunk_list),
            uncompressed_bytes=sum(chunk.raw_size for chunk in chunk_list),
            signature_offset=self.signature_offset,
            signature_size=256,
            metadata_offset=self.metadata_offset,
            metadata_length=self.metadata_length,
            block_count=transport.get("blockCount"),
            stream_blocks=transport.get("streamBlocks", {}),
            first_timestamp=transport.get("firstTimestamp"),
            last_timestamp=transport.get("lastTimestamp"),
            distinct_opcodes=transport.get("distinctOpcodes"),
            top_opcodes=tuple(transport.get("topOpcodes", [])),
        )


def _parse_header(data: mmap.mmap) -> ReplayHeader:
    if data[:4] != b"RIOT":
        raise RoflParseError("MAGIC_INVALID", "file does not start with RIOT")
    format_version = struct.unpack_from("<H", data, 4)[0]
    if format_version != 2:
        raise RoflParseError("FORMAT_UNSUPPORTED", f"unsupported ROFL format {format_version}")
    version_length = data[14]
    header_size = 15 + version_length
    if version_length == 0 or header_size > len(data):
        raise RoflParseError("HEADER_INVALID", "client version length is invalid", offset=14)
    raw_version = bytes(data[15:header_size])
    try:
        client_version = raw_version.decode("ascii")
    except UnicodeDecodeError as exc:
        raise RoflParseError("HEADER_INVALID", "client version is not ASCII", offset=15) from exc
    return ReplayHeader(
        format_version=format_version,
        client_version=client_version,
        header_field_0x06=struct.unpack_from("<H", data, 6)[0],
        header_bytes_0x08=bytes(data[8:14]),
        header_size=header_size,
    )


def _normalize_streams(streams: Iterable[str | int] | None) -> set[int] | None:
    if streams is None:
        return None
    result: set[int] = set()
    reverse = {name: stream for stream, name in STREAM_NAMES.items()}
    for stream in streams:
        if isinstance(stream, int):
            result.add(stream)
        elif stream in reverse:
            result.add(reverse[stream])
        else:
            raise RoflParseError("STREAM_INVALID", f"unknown ROFL stream: {stream}")
    return result


def _normalize_opcodes(opcodes: Iterable[int] | None) -> set[int] | None:
    if opcodes is None:
        return None
    result: set[int] = set()
    for opcode in opcodes:
        if isinstance(opcode, bool) or not isinstance(opcode, int) or not 0 <= opcode <= 0xFFFF:
            raise RoflParseError(
                "OPCODE_INVALID",
                "opcodes must fit in an unsigned 16-bit value",
            )
        result.add(opcode)
    return result
