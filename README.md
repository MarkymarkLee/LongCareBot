# LongCareBot backend

An async Python backend for a long-care virtual companion. It accepts text produced by the frontend's wake-word/ASR pipeline, searches PostgreSQL for previously answered questions, asks an OpenRouter-hosted model for an answer, and streams the response over Server-Sent Events (SSE).

## Docker Compose quick start

Requirements: Python 3.11+, PostgreSQL, and [uv](https://docs.astral.sh/uv/).

```bash
cp .env.example .env
docker compose up --build -d 
```

The public gateway is available at `http://localhost:8000`. Compose runs three services:

- `postgres`: PostgreSQL plus the initial schema.
- `agent`: private OpenAI Agents SDK service on the Compose network, backed by local Ollama.
- `gateway`: public FastAPI API, SSE proxy, and family WebSocket hub.
- `ollama`: local model runtime. The agent automatically pulls `gemma4:e2b` into the persistent `ollama_data` volume on first startup.

To stop the services while retaining data:

```bash
docker compose down
```

To delete the database volume and initialize the schema again:

```bash
docker compose down -v
```

The `-v` also deletes the downloaded Ollama model, so the next startup will download it again. Gemma 4 E2B is approximately 7 GB for the standard tag; make sure Docker has enough disk space and memory.

Ask the companion:

```bash
curl -N -X POST http://localhost:8000/v1/companion/ask \
  -H 'content-type: application/json' \
  -d '{"patient_id":"patient-1","question":"Where are my glasses?"}'
```

The endpoint emits SSE events: `text_delta`, then `completed` (or `error`). A frontend can speak the accumulated text with TTS.

## Family notifications

Create a patient and associated family member in `patients` and `family_members`. A family frontend connects to:

```text
ws://localhost:8000/v1/family/ws/{family_member_id}/{patient_id}
```

When the agent cannot answer, it inserts a durable pending row in `family_notifications` and publishes a PostgreSQL notification. The gateway receives that event and immediately sends JSON to connected family WebSocket clients; no frontend polling is needed. The pending row remains the fallback for family members who were offline. Submit an answer with:

```bash
curl -X POST http://localhost:8000/v1/family/notifications/1/answer \
  -H 'content-type: application/json' \
  -d '{"patient_id":"patient-1","answer":"They are on the bedside table."}'
```

This WebSocket implementation assumes the member ID has already been authenticated by your frontend. Before production, derive the member and patient from a session/JWT instead of trusting URL parameters. For notifications when a family member is fully offline, add browser Web Push subscriptions and send them from the same notification path; PostgreSQL `NOTIFY` itself is an in-cluster delivery signal, not a mobile/browser push service.

The first version intentionally takes text rather than audio. Keep wake-word detection (`Hey [name]`) and ASR in the client or a separate service, then send only the transcript after the wake word to this endpoint.
