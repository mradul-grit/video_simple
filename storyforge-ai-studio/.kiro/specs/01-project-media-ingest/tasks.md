# Spec 01 — Tasks

Status as of 2026-11-16. A box is ticked only when a test or command verified it.

- [x] Define typed Project, MediaAsset and Job domain models (`app/db/models.py`, `app/domain/schemas.py`).
- [x] Add database migrations and repository tests (Alembic `0001`; upgrade → downgrade → upgrade
      verified on PostgreSQL; downgrade drops enum types).
- [x] Implement local object storage adapter with path traversal protection (tests cover `..`, absolute keys).
- [x] Implement project CRUD endpoints with ownership tests (cross-user access returns 404 on every route).
- [x] Implement upload intent/complete and local upload route with byte limits
      (HMAC grant bound to method, key, expiry and byte cap; single use; streamed to disk).
- [x] Implement ffprobe validation and media metadata extraction, in a Celery worker, never in the request.
      Tests: valid clip, non-video bytes, truncated MP4, over-long video, oversize upload.
- [ ] Implement resumable upload state/client retry UX. Current upload is cancellable and retryable
      from the start, not resumable.
- [x] Add cleanup/deletion behaviour and tests (project delete removes rows and stored objects).
- [x] Add API integration tests and mobile widget tests.
- [ ] Retention cleanup job (retention days are shown to users but not enforced yet).
- [x] Document supported formats, limits and local storage cleanup (README, `/system/info`).

## Deviations from the design, with reasons
- Validation runs in a worker after `/complete` (the API contract's async rule) instead of inside upload.
- `/system/info` was added so the app can show limits before upload and label demo-mode output.
- `/projects/{id}/media/{id}/preview-url` was added so the editor can play the owner's original.
