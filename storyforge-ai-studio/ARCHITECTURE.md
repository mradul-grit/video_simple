# Architecture and technical decisions

## High-level shape

Flutter mobile client → FastAPI control plane → Postgres metadata + private object storage → background job queue → media/AI workers → rendered MP4 → Flutter preview/export.

The client must not hold provider secrets and must not perform heavy rendering or AI inference in the request/response path. A future Android native rendering adapter may use Jetpack Media3 Transformer; iOS may use AVFoundation. MVP final rendering is performed by the backend FFmpeg worker to keep cross-platform output reproducible.

## Monorepo layout

```text
storyforge-ai-studio/
  .kiro/steering/                 persistent Kiro product/engineering rules
  .kiro/specs/                    phased requirements, design and tasks
  backend/                        FastAPI API, domain services and workers
  mobile/                         Flutter Android/iOS app (Kiro scaffolds it)
  infra/                          local and cloud deployment references
  docs/                           detailed product and operations docs
  scripts/                        repeatable developer/CI scripts
  docker-compose.yml              local Postgres + Redis + API + worker
  EDIT_MANIFEST.schema.json       canonical non-destructive edit format
```

## Mobile application
- Flutter/Dart; Android and iOS targets.
- Riverpod for state management; GoRouter for navigation.
- Dio for API client; generated typed models via Freezed/json_serializable or an equivalent maintained approach.
- Drift/SQLite for local drafts, recent projects and offline edit metadata; secrets via `flutter_secure_storage`.
- `camera` or `image_picker`/`file_picker` for capture/import; `video_player` for preview. Verify package maintenance and Flutter compatibility before pinning.
- Upload with resumable/chunked strategy where possible, retry and cancel support.
- Simple storyboard/timeline with tracks: source video, cuts, transcript, editorial captions, visuals, audio adjustments.
- Avoid FFmpegKit: upstream FFmpegKit was retired. Do not add an unverified fork. Use backend FFmpeg for MVP export; consider Media3 Transformer and AVFoundation native adapters later.

## Backend
- Python 3.12+ (verify the currently supported stable runtime before pinning).
- FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, PostgreSQL.
- Redis + Celery for local asynchronous jobs; cloud queue adapter for SQS.
- `boto3` for S3-compatible APIs and AWS services.
- FFmpeg/ffprobe command-line tools inside the worker container; never shell-interpolate user data.
- Provider interfaces for object storage, queue, transcription, LLM/story analysis, visual search, image generation and rendering.

## AI pipeline
1. Validate media using file signatures, size/duration limits and `ffprobe`.
2. Extract audio track and metadata.
3. Voice activity detection (VAD) to identify speech and long pauses; pause thresholds are user-adjustable.
4. Speech-to-text via Faster-Whisper (CPU int8 for local prototype; GPU profile for high quality/throughput). Keep source timestamps and language confidence.
5. Optional word-level alignment. Add only after validating timestamp quality and model dependencies.
6. Story analysis via a JSON-constrained LLM call. It can identify topic, key points, claims, named entities, visual beats and candidate short editorial captions. Every generated editorial caption must point to source transcript spans. Never add facts not supported by the transcript.
7. Cut proposals from VAD + transcript + configurable editing policy. Never auto-delete a pause when it may be rhetorical or intentional without confidence/review.
8. Visual query generation from story beats. Search open-licensed media providers; optionally call locally hosted ComfyUI or a configured paid generation provider.
9. Asset review, layout selection and user-approved edit manifest.
10. Deterministic rendering via FFmpeg with progress events and retryable jobs.
11. Validate export with ffprobe; return metadata and signed download URL.

## AI provider policy
- Local transcription: Faster-Whisper; model name/compute type configurable. CPU int8 is a cost-saving baseline, not a claim of best accuracy. Offer GPU model profile such as large-v3-turbo when hardware supports it and test Hindi/English/Hinglish separately.
- Local LLM: Ollama with a configurable instruct model. Default model name is a configuration value, not hard-coded into product logic. JSON-schema validation, retries and deterministic fallback for extraction must be implemented.
- Visual discovery: Openverse first with license filters and full attribution metadata. Pixabay is optional and must observe 24-hour caching, attribution display and downloading/storing assets rather than permanent hotlinking. Pexels should be an optional adapter only; do not block MVP on API key availability.
- Image generation: optional local ComfyUI adapter. Paid providers must be disabled until a user/server admin explicitly configures credentials and spending limits.
- No model weights, API secrets or unlicensed assets are committed to Git.

## Render engine
- FFmpeg + ffprobe in the backend worker container.
- Build a deterministic command/filter graph from validated EditManifest. Use argv arrays and explicit filtergraph escaping.
- Export baseline: MP4, H.264 video, AAC audio, yuv420p, 9:16 at 1080x1920, `-movflags +faststart`; expose quality/performance presets after testing. Preserve source frame rate where practical; normalize unsupported input to a documented target.
- Apply scale/crop, overlays, subtitle/caption burn-in or selectable sidecar track, alpha, image placement, time-based transforms, audio filters and loudness normalization.
- Preview renders may be lower resolution/bitrate; final export uses selected quality preset.
- Store render command metadata and app/renderer version for reproducibility, excluding secrets.

## Data model (minimum)
User, Project, MediaAsset, Transcript, TranscriptSegment, StoryBeat, EditManifest, VisualSuggestion, RenderJob, ExportAsset, UsageLedger, ProviderSetting. Use UUID IDs, UTC timestamps and ownership foreign keys. Add optimistic concurrency/versioning to EditManifest. Do not store binary media in Postgres.

## Job state machine
`created → uploading → uploaded → queued → validating → transcribing → analysing → awaiting_review → rendering → completed`
Terminal/side states: `failed`, `cancelled`, `expired`. Keep progress percentage, stage, safe user-facing message, retry count and provider metadata. Operations must be idempotent by job key; retries must not duplicate billing or produce duplicate exports.

## API boundary
See `API_CONTRACT.md`. Version all routes under `/api/v1`. Use OpenAPI, request IDs, pagination, structured error responses and auth dependency. No API request should block while a video is transcribed or rendered.

## Local development
- Docker Compose: Postgres, Redis, FastAPI API and worker.
- Local filesystem object storage adapter.
- Local AI services run on host or optional Docker profile; never download multi-GB model weights automatically without explicit setup/space confirmation.
- `mock` provider profile makes UI and API contract tests deterministic; visibly mark output as demo.

## Production growth path (not auto-provisioned)
- AWS S3 for source/proxy/export media; private buckets, SSE, lifecycle policies and short-lived presigned URLs.
- AWS SQS for job dispatch.
- ECS worker tasks for CPU/GPU/FFmpeg workloads; evaluate Fargate Spot or EC2 Spot only after retry/checkpoint behavior is reliable.
- Cognito for AWS-native authentication OR Supabase Auth for simpler early beta. Do not run two independent user identity systems in MVP.
- Supabase Postgres is a convenient early beta option. For mature AWS-native operation evaluate RDS/Aurora only after estimating steady-state cost and backup needs.
- CloudFront signed URLs optionally for media delivery.
- CloudWatch logs/metrics/alarms and budget alerts.
- Use AWS CDK or Terraform after deployment scope and costs are reviewed. No cloud stack deploy on agent initiative.

## Architecture decisions requiring verification
Before adding or upgrading dependencies, check official current docs, release activity, compatibility, security advisories, supported platform and licensing. Record dependency versions and why they were chosen.
