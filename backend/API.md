# LongCareBot API reference

The public API is served by the FastAPI gateway at `http://localhost:8000`.

> Authentication is not implemented yet. The member IDs in these examples must be protected by an application session or JWT before production use.

## Common conventions

- Content type for JSON requests: `application/json`
- IDs are application-provided text values.
- Patient IDs must already exist in `patients`.
- A patient is created by creating a member with `is_patient: true`.
- Errors use FastAPI's standard format:

```json
{"detail":"description of the error"}
```

## `GET /health`

Checks that the gateway process is running.

### Response `200`

```json
{"status":"ok"}
```

### Usage

```bash
curl http://localhost:8000/health
```

## `POST /v1/members`

Registers a member. All patients and family members are stored in `members`.
When `is_patient` is `true`, the API also creates a corresponding row in `patients`.

### Request body

| Field | Type | Required | Description |
|---|---|---:|---|
| `id` | string | yes | Unique member and, for patients, patient ID. |
| `display_name` | string | yes | Name shown to other users. |
| `email` | string or null | no | Member email address. |
| `is_patient` | boolean | no | Whether this member is also a patient. Defaults to `false`. |

### Response `201`

```json
{"id":"patient-1","is_patient":true}
```

### Errors

- `409`: a member with this ID already exists.

### Usage

```bash
curl -X POST http://localhost:8000/v1/members \
  -H 'content-type: application/json' \
  -d '{
    "id": "patient-1",
    "display_name": "Alice",
    "email": "alice@example.com",
    "is_patient": true
  }'
```

Family member example:

```bash
curl -X POST http://localhost:8000/v1/members \
  -H 'content-type: application/json' \
  -d '{"id":"family-1","display_name":"Bob","is_patient":false}'
```

## `POST /v1/patients/{patient_id}/family-members`

Associates an existing non-patient member with a patient. This relationship controls
which family members are allowed to receive that patient's WebSocket notifications.

### Path parameters

| Parameter | Type | Description |
|---|---|---|
| `patient_id` | string | Existing patient ID from `patients.id`. |

### Request body

```json
{"member_id":"family-1"}
```

| Field | Type | Required | Description |
|---|---|---:|---|
| `member_id` | string | yes | Existing member ID. The member must have `is_patient: false`. |

### Response `201`

```json
{"ok":true}
```

### Errors

- `404`: the patient does not exist.
- `400`: the member does not exist or is itself a patient.

### Usage

```bash
curl -X POST \
  http://localhost:8000/v1/patients/patient-1/family-members \
  -H 'content-type: application/json' \
  -d '{"member_id":"family-1"}'
```

## `POST /v1/companion/ask`

Sends a patient question to the agent and streams the response as Server-Sent Events
(SSE). The frontend should send the transcript produced after wake-word detection and
ASR, not the audio itself.

### Request body

| Field | Type | Required | Description |
|---|---|---:|---|
| `patient_id` | string | yes | Existing patient ID. |
| `question` | string | yes | Patient transcript, 1–4000 characters. |

### Response

Content type: `text/event-stream`

Successful stream:

```text
event: text_delta
data: {"text":"They are on "}

event: text_delta
data: {"text":"the bedside table."}

event: completed
data: {}
```

If the agent or its model fails:

```text
event: error
data: {"message":"..."}
```

### Errors

- `404`: the patient does not exist.

### Usage

```bash
curl -N -X POST http://localhost:8000/v1/companion/ask \
  -H 'content-type: application/json' \
  -d '{"patient_id":"patient-1","question":"Where are my glasses?"}'
```

The frontend can concatenate `text_delta.text` values and send the completed text to
its TTS layer.

## `WS /v1/family/ws/{member_id}/{patient_id}`

Opens a WebSocket for a family member to receive immediate questions that the agent
cannot answer. The connection is accepted only if `member_id` is associated with
`patient_id` in `patient_family_members`.

### Path parameters

| Parameter | Type | Description |
|---|---|---|
| `member_id` | string | Connected family member's member ID. |
| `patient_id` | string | Patient whose notifications should be delivered. |

### Server message

```json
{
  "type": "family_question",
  "notification_id": 42,
  "patient_id": "patient-1",
  "question": "What time is my appointment?"
}
```

The database keeps the notification as a durable pending row. WebSocket delivery is
instant for connected members; offline members need a later notification query or a
future browser/mobile push provider.

### JavaScript usage

```js
const socket = new WebSocket(
  "ws://localhost:8000/v1/family/ws/family-1/patient-1"
);

socket.onmessage = (event) => {
  const notification = JSON.parse(event.data);
  console.log(notification.question);
};
```

The client should send periodic WebSocket ping/keepalive messages as appropriate for
its runtime. The server keeps the connection open until the client disconnects.

## `POST /v1/family/notifications/{notification_id}/answer`

Submits a family member's answer to a pending notification. The answer is marked as
answered and inserted into `question_answers`, so the agent can use it for future
questions from that patient.

### Path parameters

| Parameter | Type | Description |
|---|---|---|
| `notification_id` | integer | Notification ID received over WebSocket. |

### Request body

| Field | Type | Required | Description |
|---|---|---:|---|
| `patient_id` | string | yes | Patient associated with the notification. |
| `answer` | string | yes | Human answer, 1–4000 characters. |

### Response `200`

```json
{"ok":true}
```

If the notification is missing, already answered, or belongs to another patient:

```json
{"ok":false,"message":"Pending notification not found"}
```

### Usage

```bash
curl -X POST \
  http://localhost:8000/v1/family/notifications/42/answer \
  -H 'content-type: application/json' \
  -d '{
    "patient_id": "patient-1",
    "answer": "The appointment is tomorrow at 10 AM."
  }'
```

## Internal agent routes

These routes are available only on the internal Docker Compose network. They should not
be exposed directly to browsers.

### `GET /health`

The agent service exposes the same health response on its internal port (`8001`).

### `POST /internal/answer`

The gateway forwards the same `AskRequest` body to this route. It returns the same SSE
event stream as `/v1/companion/ask`. Normally, clients should call the gateway route,
not this internal route.
