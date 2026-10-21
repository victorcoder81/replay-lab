from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


STREAM_NAMES = {
    1: "gameChunk",
    2: "keyframe",
    3: "startKeyframe",
    4: "startSentinel",
}


@dataclass(frozen=True)
class ReplayHeader:
    format_version: int
    client_version: str
    header_field_0x06: int
    header_bytes_0x08: bytes
    header_size: int

    @property
    def patch(self) -> str:
        parts = self.client_version.split(".")
        return ".".join(parts[:2]) if len(parts) >= 2 else self.client_version

    @property
    def protocol_digest(self) -> str:
        return self.header_field_0x06.to_bytes(2, "little").hex() + self.header_bytes_0x08.hex()

    def as_dict(self) -> dict[str, Any]:
        return {
            "formatVersion": self.format_version,
            "clientVersion": self.client_version,
            "patch": self.patch,
            "protocolDigest": self.protocol_digest,
            "headerField0x06": self.header_field_0x06,
            "headerBytes0x08": self.header_bytes_0x08.hex(),
            "headerSize": self.header_size,
        }


@dataclass(frozen=True)
class ReplayMetadata:
    game_length: int | None
    last_game_chunk_id: int | None
    last_key_frame_id: int | None
    participants: tuple[dict[str, Any], ...] = ()
    extra: dict[str, Any] = field(default_factory=dict)
    stats_json_length: int = 0

    @property
    def participant_count(self) -> int:
        return len(self.participants)

    def as_dict(self) -> dict[str, Any]:
        payload = dict(self.extra)
        payload.update(
            {
                "gameLength": self.game_length,
                "lastGameChunkId": self.last_game_chunk_id,
                "lastKeyFrameId": self.last_key_frame_id,
                "statsJson": {
                    "encodedLength": self.stats_json_length,
                    "participantCount": self.participant_count,
                    "fieldsPerParticipant": (
                        len(self.participants[0]) if self.participants else 0
                    ),
                },
            }
        )
        return payload


@dataclass(frozen=True)
class ChunkRecord:
    offset: int
    body_offset: int
    chunk_id: int
    slot: int
    stream: int
    raw_size: int
    compressed_size: int

    @property
    def stream_name(self) -> str:
        return STREAM_NAMES.get(self.stream, "unknown")

    @property
    def stored_size(self) -> int:
        return self.compressed_size or self.raw_size

    def as_dict(self, *, decoded_size: int | None = None, valid: bool | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "offset": self.offset,
            "bodyOffset": self.body_offset,
            "chunkId": self.chunk_id,
            "slot": self.slot,
            "stream": self.stream,
            "streamName": self.stream_name,
            "rawSize": self.raw_size,
            "compressedSize": self.compressed_size,
        }
        if decoded_size is not None:
            payload["decodedSize"] = decoded_size
        if valid is not None:
            payload["valid"] = valid
        return payload


@dataclass(frozen=True)
class NetworkBlock:
    stream: str
    stream_id: int
    chunk_id: int
    block_offset: int
    timestamp: float
    packet_id: int
    param: int
    payload_length: int
    payload: bytes | None = None

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "stream": self.stream,
            "streamId": self.stream_id,
            "chunkId": self.chunk_id,
            "blockOffset": self.block_offset,
            "timestamp": self.timestamp,
            "packetId": self.packet_id,
            "param": self.param,
            "payloadLength": self.payload_length,
        }
        if self.payload is not None:
            payload["payload"] = self.payload
        return payload


@dataclass(frozen=True)
class ReplaySummary:
    path: str
    file_size: int
    sha256: str
    header: ReplayHeader
    metadata: ReplayMetadata
    chunk_count: int
    stream_chunks: dict[str, int]
    compressed_bytes: int
    uncompressed_bytes: int
    signature_offset: int
    signature_size: int
    metadata_offset: int
    metadata_length: int
    block_count: int | None = None
    stream_blocks: dict[str, int] = field(default_factory=dict)
    first_timestamp: float | None = None
    last_timestamp: float | None = None
    distinct_opcodes: int | None = None
    top_opcodes: tuple[dict[str, Any], ...] = ()

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "path": self.path,
            "fileSize": self.file_size,
            "sha256": self.sha256,
            "header": self.header.as_dict(),
            "metadata": self.metadata.as_dict(),
            "chunkCount": self.chunk_count,
            "streamChunks": self.stream_chunks,
            "compressedBytes": self.compressed_bytes,
            "uncompressedBytes": self.uncompressed_bytes,
            "signatureOffset": self.signature_offset,
            "signatureSize": self.signature_size,
            "metadataOffset": self.metadata_offset,
            "metadataLength": self.metadata_length,
        }
        if self.block_count is not None:
            payload["transport"] = {
                "blockCount": self.block_count,
                "streamBlocks": self.stream_blocks,
                "firstTimestamp": self.first_timestamp,
                "lastTimestamp": self.last_timestamp,
                "distinctOpcodes": self.distinct_opcodes,
                "topOpcodes": list(self.top_opcodes),
            }
        return payload


@dataclass(frozen=True)
class TypedEvent:
    kind: str
    timestamp: float
    opcode: int
    fields: dict[str, Any]
    decode_status: str = "decoded"

    def as_dict(self) -> dict[str, Any]:
        return {
            "decodeStatus": self.decode_status,
            "kind": self.kind,
            "timestamp": self.timestamp,
            "opcode": self.opcode,
            "fields": self.fields,
        }


@dataclass(frozen=True)
class UnknownEvent:
    block: NetworkBlock
    reason: str = "no decoder registered"

    def as_dict(self) -> dict[str, Any]:
        payload = self.block.as_dict()
        raw_available = payload.pop("payload", None) is not None
        payload.update(
            {
                "decodeStatus": "unknown",
                "reason": self.reason,
                "rawPayloadAvailable": raw_available,
            }
        )
        return payload
