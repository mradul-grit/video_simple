# API contract (initial proposal)

Base path: `/api/v1`. All long-running work is asynchronous. Use UUIDs, UTC ISO-8601 timestamps and JSON responses. Return a request ID in every response. Exact schemas should be generated from Pydantic and exposed via OpenAPI.

## Authentication
`Authorization: Bearer <JWT>` for protected routes. Development-only mock auth may be enabled only under `APP_ENV=development`; never in production. Verify issuer, audience, expiry and signature.

## Endpoints

### Health
- `GET /health/live` — process liveness.
- `GET /health/ready` — checks critical dependencies and reports degraded state safely.

### Projects
- `POST /projects` — create project: title, language preference, output preset.
- `GET /projects?cursor=&limit=` — list caller's projects.
- `GET /projects/{project_id}` — project metadata and current manifest version.
- `PATCH /projects/{project_id}` — update title/settings.
- `DELETE /projects/{project_id}` — initiate deletion of all project data and jobs.

### Media
- `POST /projects/{project_id}/media/upload-url` — request a short-lived signed upload grant with filename, content type, expected bytes and media role.
- `POST /projects/{project_id}/media/complete` — confirm upload and enqueue media validation.
- `GET /projects/{project_id}/media` — list media assets.
- `DELETE /media/{media_id}` — delete asset and dependent artifacts when safe.

### Analysis
- `POST /projects/{project_id}/analysis` — enqueue transcription/story analysis; idempotency key required.
- `GET /jobs/{job_id}` — state, stage, progress, safe error and retry availability.
- `POST /jobs/{job_id}/cancel` — cancel if possible.
- `POST /jobs/{job_id}/retry` — retry eligible failed job with quota checks.
- `GET /projects/{project_id}/analysis` — transcript, beats, cut proposals and editorial captions.

### Visual suggestions
- `POST /projects/{project_id}/visual-suggestions` — enqueue/search suggestions for selected story beat IDs.
- `GET /projects/{project_id}/visual-suggestions` — list candidates including provider, preview URL, creator, source URL, license, attribution, score and time recommendation.
- `POST /visual-suggestions/{suggestion_id}/select` — attach selected asset to edit manifest after rights checks.

### Edit manifest
- `GET /projects/{project_id}/edit-manifest` — return current version.
- `PUT /projects/{project_id}/edit-manifest` — save full validated manifest; optimistic concurrency via `If-Match` or `expected_version`.
- `POST /projects/{project_id}/edit-manifest/validate` — validate without saving.

### Rendering/export
- `POST /projects/{project_id}/renders` — enqueue render for a manifest version and preset.
- `GET /renders/{render_id}` — state/progress/metadata.
- `GET /projects/{project_id}/exports` — list completed exports.
- `POST /exports/{export_id}/download-url` — issue short-lived download URL.

## Error shape

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "The uploaded file is not a supported video.",
    "field_errors": [],
    "retryable": false
  },
  "request_id": "uuid"
}
```

Do not leak stack traces, filesystem paths, storage credentials, provider responses or signed URLs in public errors.

## Job status shape

```json
{
  "id": "uuid",
  "status": "transcribing",
  "stage": "speech_to_text",
  "progress": 32,
  "message": "Transcribing audio",
  "retryable": false,
  "updated_at": "2026-11-16T00:00:00Z"
}
```

## Idempotency and concurrency
- Use idempotency keys for analysis and render enqueue operations.
- Job retries reuse the same logical job lineage; completed jobs must not be duplicated by network retry.
- Each manifest update increments `version`; reject stale `expected_version` with `409 CONFLICT`.
- Check project ownership for nested objects; never trust an ID without an authorization query.
