import json
import asyncio
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .agent import CompanionAgent
from .config import get_settings
from .db import Database
from .notifications import FamilyNotifier

settings = get_settings()
db = Database(settings)
companion: CompanionAgent | None = None


async def ensure_ollama_model() -> None:
    """Wait for Ollama and pull the configured model if it is not persistent yet."""
    async with httpx.AsyncClient(timeout=None) as client:
        for _ in range(60):
            try:
                response = await client.get(f"{settings.ollama_base_url}/api/tags")
                response.raise_for_status()
                models = {item["name"] for item in response.json().get("models", [])}
                if settings.ollama_model in models:
                    return
                async with client.stream(
                    "POST",
                    f"{settings.ollama_base_url}/api/pull",
                    json={"name": settings.ollama_model, "stream": False},
                ) as pull:
                    pull.raise_for_status()
                return
            except (httpx.HTTPError, KeyError, ValueError):
                await asyncio.sleep(2)
    raise RuntimeError("Ollama did not become ready within 120 seconds")


@asynccontextmanager
async def lifespan(_: FastAPI):
    global companion
    await ensure_ollama_model()
    await db.connect()
    companion = CompanionAgent(settings, db, FamilyNotifier(db))
    yield
    await db.close()


app = FastAPI(title="LongCareBot agent", lifespan=lifespan)


class AskRequest(BaseModel):
    patient_id: str = Field(min_length=1)
    question: str = Field(min_length=1, max_length=4000)


async def events(request: Request, body: AskRequest):
    if companion is None:
        yield f"event: error\ndata: {json.dumps({'message': 'Agent not ready'})}\n\n"
        return
    try:
        async for delta in companion.answer(body.patient_id, body.question):
            if await request.is_disconnected():
                return
            yield f"event: text_delta\ndata: {json.dumps({'text': delta})}\n\n"
        yield "event: completed\ndata: {}\n\n"
    except Exception as exc:
        yield f"event: error\ndata: {json.dumps({'message': str(exc)})}\n\n"


@app.post("/internal/answer")
async def answer(request: Request, body: AskRequest):
    return StreamingResponse(events(request, body), media_type="text/event-stream")


@app.get("/health")
async def health():
    return {"status": "ok"}
