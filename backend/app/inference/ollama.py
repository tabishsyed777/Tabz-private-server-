from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx

from .base import InferenceError


class OllamaBackend:
    """Ollama adapter. Other engines can implement the same InferenceBackend contract."""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    async def list_models(self) -> list[dict]:
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                response.raise_for_status()
                data = response.json()
                return [{"name": item["name"], "size": item.get("size")} for item in data.get("models", [])]
        except httpx.ConnectError as exc:
            raise InferenceError(f"Cannot reach Ollama at {self.base_url}. Make sure Ollama is running.") from exc
        except httpx.TimeoutException as exc:
            raise InferenceError("Ollama did not respond in time while loading the model list.") from exc
        except httpx.HTTPStatusError as exc:
            raise InferenceError(self._response_error(exc.response)) from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise InferenceError("Could not read the local Ollama model list.") from exc

    async def stream_chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        *,
        num_ctx: int,
        num_predict: int,
        keep_alive: str,
    ) -> AsyncIterator[str]:
        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "keep_alive": keep_alive,
            "options": {"num_ctx": num_ctx, "num_predict": num_predict},
        }
        try:
            completed = False
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream("POST", f"{self.base_url}/api/chat", json=payload) as response:
                    if response.is_error:
                        body = await response.aread()
                        raise InferenceError(self._response_error(response, body))
                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                        except json.JSONDecodeError as exc:
                            raise InferenceError("Ollama sent an unreadable streaming response.") from exc
                        if data.get("error"):
                            raise InferenceError(str(data["error"]))
                        token = data.get("message", {}).get("content", "")
                        if token:
                            yield token
                        if data.get("done"):
                            completed = True
                            break
            if not completed:
                raise InferenceError("Ollama closed the stream before completing the reply.")
        except InferenceError:
            raise
        except httpx.ConnectError as exc:
            raise InferenceError("Ollama stopped responding. Check that its local service is running.") from exc
        except httpx.TimeoutException as exc:
            raise InferenceError("Ollama timed out before finishing the reply.") from exc
        except httpx.HTTPError as exc:
            raise InferenceError("The connection to Ollama failed while generating the reply.") from exc

    @staticmethod
    def _response_error(response: httpx.Response, body: bytes | None = None) -> str:
        try:
            data = json.loads(body if body is not None else response.content)
            detail = data.get("error") or data.get("detail")
            if detail:
                return f"Ollama error: {str(detail)[:400]}"
        except (json.JSONDecodeError, AttributeError, UnicodeDecodeError):
            pass
        return f"Ollama returned HTTP {response.status_code}: {response.reason_phrase}."
