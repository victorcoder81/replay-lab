from __future__ import annotations

import json
from typing import Any

from .errors import RoflParseError
from .models import ReplayMetadata


def parse_metadata(raw: bytes, *, offset: int) -> ReplayMetadata:
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RoflParseError(
            "METADATA_INVALID", "metadata is not valid UTF-8 JSON", offset=offset
        ) from exc
    if not isinstance(payload, dict):
        raise RoflParseError("METADATA_INVALID", "metadata root must be an object", offset=offset)

    stats_raw = payload.get("statsJson", "[]")
    participants: list[dict[str, Any]] = []
    if isinstance(stats_raw, str):
        try:
            parsed_stats = json.loads(stats_raw)
        except json.JSONDecodeError as exc:
            raise RoflParseError(
                "STATS_INVALID", "statsJson is not valid JSON", offset=offset
            ) from exc
        if not isinstance(parsed_stats, list) or any(
            not isinstance(item, dict) for item in parsed_stats
        ):
            raise RoflParseError("STATS_INVALID", "statsJson must contain participant objects", offset=offset)
        participants = parsed_stats
    elif stats_raw is not None:
        raise RoflParseError("STATS_INVALID", "statsJson must be a JSON string", offset=offset)

    extra = {key: value for key, value in payload.items() if key != "statsJson"}
    return ReplayMetadata(
        game_length=_optional_int(payload.get("gameLength")),
        last_game_chunk_id=_optional_int(payload.get("lastGameChunkId")),
        last_key_frame_id=_optional_int(payload.get("lastKeyFrameId")),
        participants=tuple(participants),
        extra=extra,
        stats_json_length=len(stats_raw) if isinstance(stats_raw, str) else 0,
    )


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise RoflParseError("METADATA_INVALID", "numeric metadata field is not an integer")
    return value
