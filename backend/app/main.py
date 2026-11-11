"""LocalMind API: server-owned history and streaming access to local inference."""
from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import threading
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from .database import SessionLocal, get_db, initialize_database
from .inference.base import InferenceBackend, InferenceError
from .inference.ollama import OllamaBackend
from .models import ChatMessage, Conversation

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("localmind")

INFERENCE_BACKEND = os.getenv("INFERENCE_BACKEND", "ollama").lower()
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_NUM_CTX = max(1024, int(os.getenv("OLLAMA_NUM_CTX", "4096")))
OLLAMA_NUM_PREDICT = max(128, min(int(os.getenv("OLLAMA_NUM_PREDICT", "1024")), OLLAMA_NUM_CTX - 256))
OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "15m")


def make_backend() -> InferenceBackend:
    if INFERENCE_BACKEND == "ollama":
        return OllamaBackend(OLLAMA_BASE_URL)
    raise RuntimeError(f"Unsupported INFERENCE_BACKEND={INFERENCE_BACKEND!r}; install and register a backend adapter first.")


inference_backend = make_backend()
active_conversations: set[str] = set()
active_guard = threading.Lock()


class ClientDisconnected(Exception):
    """The browser ended a streaming request and the local model should be released."""


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    yield


app = FastAPI(title="Tabzzat Tabish Server API", version="0.3.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(","),
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type"],
    expose_headers=["X-Conversation-Id", "X-Context-Estimated-Tokens", "X-Context-Truncated"],
)


class ConversationCreate(BaseModel):
    model: str = Field(min_length=1, max_length=200)
    title: str = Field(default="New conversation", min_length=1, max_length=160)


class ChatRequest(BaseModel):
    model: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=20_000)
    conversation_id: str | None = None


def as_conversation(item: Conversation, detail: bool = False) -> dict:
    result = {
        "id": item.id,
        "title": item.title,
        "model": item.model,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }
    if detail:
        result["messages"] = [
            {
                "id": message.id,
                "role": message.role,
                "content": message.content,
                "status": message.status,
                "error_message": message.error_message,
            }
            for message in item.messages
        ]
    return result


def estimate_message_tokens(message: dict[str, str]) -> int:
    # Conservative rough estimate for English and code. Ollama's own tokenizer is
    # model-specific, so this budget intentionally errs on the safe side.
    return math.ceil(len(message["content"]) / 3) + 4


def fit_context(messages: list[dict[str, str]]) -> tuple[list[dict[str, str]], int, int]:
    input_budget = max(256, OLLAMA_NUM_CTX - OLLAMA_NUM_PREDICT)
    selected: list[dict[str, str]] = []
    used = 0
    for message in reversed(messages):
        cost = estimate_message_tokens(message)
        if used + cost > input_budget:
            break
        selected.append(message)
        used += cost
    if not selected and messages:
        raise HTTPException(
            status_code=413,
            detail=f"This message is too long for the configured context. Shorten it or raise OLLAMA_NUM_CTX (currently {OLLAMA_NUM_CTX}).",
        )
    selected.reverse()
    return selected, used, len(messages) - len(selected)


def save_reply(message_id: str, content: str, status: str, error_message: str | None = None) -> None:
    with SessionLocal() as db:
        message = db.get(ChatMessage, message_id)
        if message is not None:
            message.content = content
            message.status = status
            message.error_message = error_message[:500] if error_message else None
            db.commit()


@app.get("/api/health")
async def health() -> dict:
    try:
        models = await inference_backend.list_models()
    except InferenceError as exc:
        raise HTTPException(503, str(exc)) from exc
    return {"status": "ok", "inference_backend": INFERENCE_BACKEND, "models": len(models), "storage": "ready"}


@app.get("/api/models")
async def models() -> dict:
    try:
        return {"models": await inference_backend.list_models()}
    except InferenceError as exc:
        raise HTTPException(503, str(exc)) from exc


@app.get("/api/capabilities")
async def capabilities() -> dict:
    return {
        "chat": True,
        "history": True,
        "local_models": True,
        "context_window": OLLAMA_NUM_CTX,
        "reserved_response_tokens": OLLAMA_NUM_PREDICT,
        "keep_alive": OLLAMA_KEEP_ALIVE,
        "inference_backend": INFERENCE_BACKEND,
        "agents": "planned",
        "notebooks": "planned",
        "third_party_inference": False,
    }


@app.get("/api/conversations")
def list_conversations(db: Session = Depends(get_db)) -> dict:
    items = db.scalars(select(Conversation).order_by(Conversation.updated_at.desc())).all()
    return {"conversations": [as_conversation(item) for item in items]}


@app.post("/api/conversations", status_code=201)
def create_conversation(payload: ConversationCreate, db: Session = Depends(get_db)) -> dict:
    item = Conversation(model=payload.model, title=payload.title)
    db.add(item)
    db.commit()
    db.refresh(item)
    return as_conversation(item)


@app.get("/api/conversations/{conversation_id}")
def get_conversation(conversation_id: str, db: Session = Depends(get_db)) -> dict:
    item = db.scalar(
        select(Conversation)
        .options(selectinload(Conversation.messages))
        .where(Conversation.id == conversation_id)
    )
    if not item:
        raise HTTPException(404, "Conversation not found")
    item.messages.sort(key=lambda message: message.sequence)
    return as_conversation(item, True)


@app.delete("/api/conversations/{conversation_id}", status_code=204)
def delete_conversation(conversation_id: str, db: Session = Depends(get_db)) -> Response:
    item = db.get(Conversation, conversation_id)
    if not item:
        raise HTTPException(404, "Conversation not found")
    db.delete(item)
    db.commit()
    return Response(status_code=204)


@app.post("/api/chat")
async def chat(
    request: ChatRequest,
    http_request: Request,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    try:
        available_models = await inference_backend.list_models()
    except InferenceError as exc:
        raise HTTPException(503, str(exc)) from exc
    if request.model not in {model["name"] for model in available_models}:
        raise HTTPException(422, f"Model {request.model!r} is not installed in the selected local inference backend.")
    # Reject an oversized new message before creating a conversation or locking it.
    fit_context([{"role": "user", "content": request.content}])
    if request.conversation_id:
        conversation = db.get(Conversation, request.conversation_id)
        if not conversation:
            raise HTTPException(404, "Conversation not found")
        conversation_id = conversation.id
        with active_guard:
            if conversation_id in active_conversations:
                raise HTTPException(409, "This conversation already has a reply running. Stop or wait for it before sending another message.")
            active_conversations.add(conversation_id)
        try:
            prior = db.scalars(
                select(ChatMessage)
                .where(ChatMessage.conversation_id == conversation_id)
                .order_by(ChatMessage.sequence.asc())
            ).all()
            history = [
                {"role": item.role, "content": item.content}
                for item in prior
                if item.content and item.role in {"user", "assistant"}
            ]
        except Exception:
            with active_guard:
                active_conversations.discard(conversation_id)
            raise
    else:
        conversation = Conversation(model=request.model, title=request.content.strip()[:60] or "New conversation")
        db.add(conversation)
        db.commit()
        db.refresh(conversation)
        conversation_id = conversation.id
        history = []
        with active_guard:
            active_conversations.add(conversation_id)

    history.append({"role": "user", "content": request.content})
    try:
        selected_messages, estimated_tokens, omitted = fit_context(history)
    except HTTPException:
        with active_guard:
            active_conversations.discard(conversation_id)
        raise
    try:
        last_sequence = db.scalar(
            select(func.max(ChatMessage.sequence)).where(ChatMessage.conversation_id == conversation_id)
        ) or 0
        user_message = ChatMessage(
            conversation_id=conversation_id,
            sequence=last_sequence + 1,
            role="user",
            content=request.content,
            status="complete",
        )
        assistant_message = ChatMessage(
            conversation_id=conversation_id,
            sequence=last_sequence + 2,
            role="assistant",
            content="",
            status="streaming",
        )
        conversation.model = request.model
        conversation.updated_at = datetime.now(timezone.utc)
        db.add_all([user_message, assistant_message])
        db.commit()
        db.refresh(assistant_message)
        assistant_id = assistant_message.id
    except Exception:
        with active_guard:
            active_conversations.discard(conversation_id)
        raise

    async def stream() -> AsyncIterator[str]:
        answer = ""
        final_status = "interrupted"
        error_message: str | None = "Generation stopped before completion. The saved text is the available partial answer."
        tokens_since_checkpoint = 0
        last_checkpoint = time.monotonic()
        events: asyncio.Queue[tuple[str, str | None]] = asyncio.Queue()

        async def produce() -> None:
            try:
                async for token in inference_backend.stream_chat(
                    request.model,
                    selected_messages,
                    num_ctx=OLLAMA_NUM_CTX,
                    num_predict=OLLAMA_NUM_PREDICT,
                    keep_alive=OLLAMA_KEEP_ALIVE,
                ):
                    await events.put(("token", token))
                await events.put(("done", None))
            except InferenceError as exc:
                await events.put(("error", str(exc)))
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Unexpected error while streaming local inference")
                await events.put(("unexpected", None))

        producer = asyncio.create_task(produce())
        try:
            while True:
                if await http_request.is_disconnected():
                    raise ClientDisconnected
                try:
                    kind, value = await asyncio.wait_for(events.get(), timeout=0.25)
                except TimeoutError:
                    continue
                if kind == "token":
                    token = value or ""
                    answer += token
                    tokens_since_checkpoint += 1
                    yield f"data: {json.dumps({'token': token, 'conversation_id': conversation_id})}\n\n"
                    now = time.monotonic()
                    if tokens_since_checkpoint >= 24 or now - last_checkpoint >= 1.0:
                        await asyncio.to_thread(save_reply, assistant_id, answer, "streaming")
                        tokens_since_checkpoint = 0
                        last_checkpoint = now
                elif kind == "done":
                    final_status = "complete"
                    error_message = None
                    yield "data: [DONE]\n\n"
                    break
                elif kind == "error":
                    final_status = "error"
                    error_message = value or "The local inference backend failed while generating the reply."
                    yield f"data: {json.dumps({'error': error_message, 'status': final_status})}\n\n"
                    break
                else:
                    final_status = "error"
                    error_message = "An unexpected local inference error occurred. Check the backend log for details."
                    yield f"data: {json.dumps({'error': error_message, 'status': final_status})}\n\n"
                    break
        except ClientDisconnected:
            final_status = "interrupted"
            error_message = "Stopped in the browser. The saved text is the available partial answer."
        except asyncio.CancelledError:
            final_status = "interrupted"
            raise
        finally:
            try:
                if not producer.done():
                    producer.cancel()
                await asyncio.gather(producer, return_exceptions=True)
                await asyncio.shield(asyncio.to_thread(save_reply, assistant_id, answer, final_status, error_message))
            finally:
                with active_guard:
                    active_conversations.discard(conversation_id)

    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        "X-Conversation-Id": conversation_id,
        "X-Context-Estimated-Tokens": str(estimated_tokens),
        "X-Context-Truncated": "true" if omitted else "false",
    }
    return StreamingResponse(stream(), media_type="text/event-stream", headers=headers)
