from __future__ import annotations


class RoflParseError(ValueError):
    """Stable parser error with a machine-readable code and file context."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        offset: int | None = None,
        context: str | None = None,
    ) -> None:
        self.code = code
        self.offset = offset
        self.context = context
        details = message
        if offset is not None:
            details += f" (offset {offset})"
        if context:
            details += f" [{context}]"
        super().__init__(details)


class SemanticDependencyError(RuntimeError):
    """The optional PE/emulator dependencies are not installed."""

    code = "SEMANTIC_DEPENDENCIES_MISSING"


class SemanticDecodeError(RuntimeError):
    code = "SEMANTIC_DECODE_FAILED"
