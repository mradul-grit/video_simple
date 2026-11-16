---
inclusion: always
---
# Architecture steering

- Monorepo: Flutter mobile app + FastAPI Python backend + background workers.
- Backend business logic must not depend directly on AWS, Supabase, Openverse, Ollama or a specific model.
- Use interfaces/adapters for storage, auth, queues, STT, LLM, visual search, image generation and render engines.
- Keep long-running work asynchronous; all job operations must be idempotent and observable.
- Use Postgres for metadata, never binary media. Store large media in private object storage.
- Use Redis/Celery locally and an SQS adapter for cloud when implemented.
- FFmpeg worker is the MVP renderer; do not use retired upstream FFmpegKit.
- Use the JSON schema in repository root as the source of truth for edit manifests. Validate all manifests server-side.
- Use UTC timestamps, UUID IDs, explicit schema versions and optimistic concurrency.
- All API routes are versioned under /api/v1 and described in OpenAPI.
