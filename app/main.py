import asyncio
import json
from contextlib import asynccontextmanager

import asyncpg
import httpx
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .config import get_settings
from .db import Database

settings = get_settings()
db = Database(settings)


class FamilyHub:
    def __init__(self):
        self.clients: dict[str, set[WebSocket]] = {}
        self.lock = asyncio.Lock()

    async def connect(self, member_id: str, socket: WebSocket):
        await socket.accept()
        async with self.lock:
            self.clients.setdefault(member_id, set()).add(socket)

    async def disconnect(self, member_id: str, socket: WebSocket):
        async with self.lock:
            group = self.clients.get(member_id)
            if not group:
                return
            group.discard(socket)
            if not group:
                self.clients.pop(member_id, None)
                _member_patients.pop(member_id, None)

    async def broadcast(self, payload: dict):
        patient_id = payload["patient_id"]
        async with self.lock:
            sockets = [socket for member_id, group in self.clients.items()
                       if awaitable_member_access(member_id, patient_id) for socket in group]
        # The actual membership check is done before connection; this lookup is intentionally
        # kept in the gateway so a member only receives notifications for their patient.
        for socket in sockets:
            try:
                await socket.send_json(payload)
            except Exception:
                pass


def awaitable_member_access(member_id: str, patient_id: str) -> bool:
    # Membership is encoded in the connection map by the gateway connection route.
    # A member id is globally unique, so the notification fanout can use this map.
    return member_id in _member_patients and _member_patients[member_id] == patient_id


_member_patients: dict[str, str] = {}
hub = FamilyHub()
listener: asyncpg.Connection | None = None


async def on_family_question(_: asyncpg.Connection, __: int, ___: str, payload: str):
    notification_id, patient_id, question = payload.split(":", 2)
    await hub.broadcast({"type": "family_question", "notification_id": int(notification_id),
                         "patient_id": patient_id, "question": question})


@asynccontextmanager
async def lifespan(_: FastAPI):
    global listener
    await db.connect()
    listener = await asyncpg.connect(settings.database_url)
    await listener.add_listener("family_question", on_family_question)
    yield
    await listener.close()
    await db.close()


app = FastAPI(title="LongCareBot gateway", lifespan=lifespan)


class AskRequest(BaseModel):
    patient_id: str = Field(min_length=1)
    question: str = Field(min_length=1, max_length=4000)


class MemberRequest(BaseModel):
    id: str = Field(min_length=1, max_length=200)
    display_name: str = Field(min_length=1, max_length=200)
    email: str | None = None
    is_patient: bool = False


class FamilyLinkRequest(BaseModel):
    member_id: str = Field(min_length=1, max_length=200)


class FamilyAnswer(BaseModel):
    patient_id: str = Field(min_length=1)
    answer: str = Field(min_length=1, max_length=4000)


async def proxy_events(request: Request, body: AskRequest):
    try:
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream("POST", f"{settings.agent_url}/internal/answer",
                                     json=body.model_dump()) as response:
                response.raise_for_status()
                async for chunk in response.aiter_bytes():
                    if await request.is_disconnected():
                        return
                    yield chunk
    except Exception as exc:
        yield f"event: error\ndata: {json.dumps({'message': str(exc)})}\n\n"


@app.post("/v1/companion/ask")
async def ask(request: Request, body: AskRequest):
    if not await db.patient_exists(body.patient_id):
        raise HTTPException(status_code=404, detail=f"Patient '{body.patient_id}' does not exist")
    return StreamingResponse(proxy_events(request, body), media_type="text/event-stream")


@app.post("/v1/members", status_code=201)
async def create_member(body: MemberRequest):
    try:
        await db.create_member(body.id, body.display_name, body.email, body.is_patient)
    except asyncpg.UniqueViolationError:
        raise HTTPException(status_code=409, detail="Member already exists") from None
    return {"id": body.id, "is_patient": body.is_patient}


@app.post("/v1/patients/{patient_id}/family-members", status_code=201)
async def link_family_member(patient_id: str, body: FamilyLinkRequest):
    if not await db.patient_exists(patient_id):
        raise HTTPException(status_code=404, detail="Patient does not exist")
    await db.add_family_member(patient_id, body.member_id)
    if not await db.member_can_access_patient(body.member_id, patient_id):
        raise HTTPException(status_code=400, detail="Member does not exist or is a patient")
    return {"ok": True}


@app.websocket("/v1/family/ws/{member_id}/{patient_id}")
async def family_socket(socket: WebSocket, member_id: str, patient_id: str):
    if not await db.member_can_access_patient(member_id, patient_id):
        await socket.close(code=1008)
        return
    _member_patients[member_id] = patient_id
    await hub.connect(member_id, socket)
    try:
        while True:
            await socket.receive_text()
    except WebSocketDisconnect:
        await hub.disconnect(member_id, socket)


@app.post("/v1/family/notifications/{notification_id}/answer")
async def answer_family(notification_id: int, body: FamilyAnswer):
    if not await db.patient_exists(body.patient_id):
        raise HTTPException(status_code=404, detail=f"Patient '{body.patient_id}' does not exist")
    if not await db.answer_family_notification(notification_id, body.patient_id, body.answer):
        return {"ok": False, "message": "Pending notification not found"}
    return {"ok": True}


@app.get("/health")
async def health():
    return {"status": "ok"}
