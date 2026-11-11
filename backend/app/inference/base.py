from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol


class InferenceError(Exception):
    """A safe, user-facing inference error."""


class InferenceBackend(Protocol):
    async def list_models(self) -> list[dict]: ...

    def stream_chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        *,
        num_ctx: int,
        num_predict: int,
        keep_alive: str,
    ) -> AsyncIterator[str]: ...
