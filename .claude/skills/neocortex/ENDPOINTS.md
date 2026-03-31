# Endpoint Reference

Complete API reference for the NeoCortex ingestion and admin endpoints.

## Contents

- [Health Check](#health-check)
- [Text Ingestion](#text-ingestion)
- [Document Ingestion](#document-ingestion)
- [Events Ingestion](#events-ingestion)
- [Audio Ingestion](#audio-ingestion)
- [Video Ingestion](#video-ingestion)
- [Admin: Graphs](#admin-graphs)
- [Admin: Permissions](#admin-permissions)
- [Admin: Agents](#admin-agents)
- [Response Models](#response-models)
- [Error Codes](#error-codes)

---

## Health Check

```
GET /health
```

Response: `{"status": "ok", "version": "0.1.0"}`

---

## Text Ingestion

```
POST /ingest/text
Content-Type: application/json
Authorization: Bearer <token>
```

**Request body:**
```json
{
  "text": "Content to ingest (required, min 1 char)",
  "metadata": {"source": "optional-context"},
  "target_graph": "ncx_shared__purpose"
}
```

**Response:** `IngestionResult`

```bash
curl -X POST localhost:8001/ingest/text \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer claude-code-work" \
  -d '{"text": "Meeting notes from March standup"}'
```

---

## Document Ingestion

```
POST /ingest/document
Authorization: Bearer <token>
```

Multipart form upload. Accepted types: `text/plain`, `application/json`, `text/markdown`, `text/csv`. Max 10 MB.

**Form fields:**
- `file` (required) — the file upload
- `metadata` (optional) — JSON string with context
- `target_graph` (optional) — shared schema name

```bash
curl -X POST localhost:8001/ingest/document \
  -H "Authorization: Bearer claude-code-work" \
  -F "file=@notes.md;type=text/markdown" \
  -F 'metadata={"source": "weekly-notes"}'
```

---

## Events Ingestion

```
POST /ingest/events
Content-Type: application/json
Authorization: Bearer <token>
```

**Request body:**
```json
{
  "events": [
    {"type": "meeting", "topic": "standup", "attendees": 5},
    {"type": "decision", "topic": "use postgres", "rationale": "reliability"}
  ],
  "metadata": {},
  "target_graph": null
}
```

Each event is stored as a separate episode. Supports partial failure — if some events fail, returns `status: "partial"` with count of successful ones.

```bash
curl -X POST localhost:8001/ingest/events \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer claude-code-work" \
  -d '{"events": [{"type": "log", "msg": "deploy succeeded"}]}'
```

---

## Audio Ingestion

```
POST /ingest/audio
Authorization: Bearer <token>
```

Multipart form upload. Accepted types: `audio/mpeg`, `audio/wav`, `audio/ogg`, `audio/flac`, `audio/aac`, `audio/mp4`, `audio/webm`. Max 100 MB. Requires ffmpeg.

Audio is compressed to 64kbps mono opus in .ogg container. A Gemini multimodal model generates a text description stored as the episode content.

```bash
curl -X POST localhost:8001/ingest/audio \
  -H "Authorization: Bearer claude-code-work" \
  -F "file=@recording.wav;type=audio/wav" \
  -F 'metadata={"speaker": "alice", "language": "en"}'
```

**Response:** `MediaIngestionResult` (includes `media_ref` with path, size, duration).

---

## Video Ingestion

```
POST /ingest/video
Authorization: Bearer <token>
```

Multipart form upload. Accepted types: `video/mp4`, `video/mpeg`, `video/webm`, `video/quicktime`, `video/x-msvideo`, `video/x-matroska`, `video/3gpp`. Max 100 MB. Requires ffmpeg.

Video is compressed to 480p, CRF 30, h264 with 64kbps mono audio in .mp4 container.

```bash
curl -X POST localhost:8001/ingest/video \
  -H "Authorization: Bearer claude-code-work" \
  -F "file=@demo.mp4;type=video/mp4"
```

**Response:** `MediaIngestionResult` (includes `media_ref` with path, size, duration).

---

## Admin: Graphs

All admin endpoints require an admin token.

### Create shared graph

```
POST /admin/graphs
Authorization: Bearer admin-token
Content-Type: application/json
```

```json
{"purpose": "team_knowledge"}
```

Creates schema `ncx_shared__team_knowledge` with shared isolation.

### List graphs

```
GET /admin/graphs
Authorization: Bearer admin-token
```

### Drop graph

```
DELETE /admin/graphs/{schema_name}
Authorization: Bearer admin-token
```

---

## Admin: Permissions

### Grant permission

```
POST /admin/permissions
Authorization: Bearer admin-token
Content-Type: application/json
```

```json
{
  "agent_id": "alice",
  "schema_name": "ncx_shared__team_knowledge",
  "can_read": true,
  "can_write": true
}
```

Upserts — call again to update read/write flags.

### List permissions

```
GET /admin/permissions
GET /admin/permissions?agent_id=alice
GET /admin/permissions?schema_name=ncx_shared__team_knowledge
GET /admin/permissions/{agent_id}
```

### Revoke permission

```
DELETE /admin/permissions/{agent_id}/{schema_name}
```

---

## Admin: Agents

### List agents

```
GET /admin/agents
Authorization: Bearer admin-token
```

### Promote to admin

```
PUT /admin/agents/{agent_id}/admin
Content-Type: application/json
```

```json
{"is_admin": true}
```

### Demote from admin

```
DELETE /admin/agents/{agent_id}/admin
```

Bootstrap admin (`admin` by default) cannot be demoted.

---

## Response Models

### IngestionResult

```json
{
  "status": "stored",
  "episodes_created": 1,
  "message": "Stored 1 episode(s)"
}
```

`status` is one of: `"stored"`, `"failed"`, `"partial"`.

### MediaIngestionResult

Extends `IngestionResult` with:

```json
{
  "status": "stored",
  "episodes_created": 1,
  "message": "...",
  "media_ref": {
    "relative_path": "alice/f47ac10b-58cc.ogg",
    "original_filename": "recording.wav",
    "content_type": "audio/wav",
    "compressed_size": 45120,
    "duration_seconds": 3.5
  }
}
```

### PermissionInfo

```json
{
  "id": 1,
  "agent_id": "alice",
  "schema_name": "ncx_shared__team_knowledge",
  "can_read": true,
  "can_write": true,
  "granted_by": "admin",
  "created_at": "2026-03-28T10:00:00",
  "updated_at": "2026-03-28T10:00:00"
}
```

---

## Error Codes

| Code | Meaning | Common Cause |
|------|---------|--------------|
| 401 | Unauthorized | Missing or invalid bearer token |
| 403 | Forbidden | Agent lacks write permission for `target_graph`, or not admin for `/admin/*` |
| 413 | Payload Too Large | File exceeds size limit (10 MB for docs, 100 MB for media) |
| 415 | Unsupported Media Type | Content type not in accepted list for endpoint |
| 422 | Validation Error | Empty text, empty events array, malformed metadata JSON |
