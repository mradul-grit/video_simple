# StoryForge AI Studio

> Working title. Rename after product and trademark checks.

StoryForge turns a creator's talking-head recording into a reviewed, vertical (9:16) video. It
analyses the speech, proposes cuts and key-point captions, and renders an MP4 you publish yourself.
Every AI suggestion starts unreviewed. Nothing is cut unless you accept it, and the original video
is never modified.

Product requirements live in `PRODUCT_BRIEF.md`, `ARCHITECTURE.md`, `API_CONTRACT.md`,
`SECURITY_PRIVACY.md`, `QUALITY_BAR.md`, `COST_AND_SERVICE_MATRIX.md` and `.kiro/specs/`.

## What works today

| Area | Status |
|---|---|
| Local stack (Postgres, Redis, FastAPI API, Celery worker) in Docker Compose | Working |
| Health: `/api/v1/health/live`, `/api/v1/health/ready` (DB + queue) | Working |
| Projects: create, list (paginated), rename, delete (removes rows **and** stored files) | Working |
| Upload: signed, size-capped, single-use grant, streamed to private storage | Working |
| Validation in the worker: file signature, ffprobe streams, size and duration limits | Working |
| Analysis job: transcript, story beats, pause cuts, grounded key-point captions | **Demo data only** (see below) |
| Cut review (accept / keep / adjust) | Working |
| Edit manifest: JSON-Schema + semantic validation, versioned saves, `409` on conflicts | Working |
| Render: cuts, 1080x1920 scale/pad, colour and audio filters, ffprobe-verified H.264/AAC MP4 | Working |
| Export download through short-lived signed links | Working |
| Flutter app: sign-in (dev), projects, upload with consent, analysis, editor, exports, settings | Working (Android build; see Mobile) |

### Not built yet (planned in later specs)

- Real transcription and story analysis. Faster-Whisper and Ollama adapters exist in
  `app/workers/tasks.py` but are not installed or tested. Default providers are `mock`, and the
  app shows a **Demo mode** banner wherever their placeholder output appears.
- Visual suggestions UI, overlays/cutaways, caption burn-in and motion in the renderer (Spec 03-05).
- Editing caption text, undo/redo, autosave (Spec 04).
- In-app recording, resumable uploads, saving exports to the gallery/share sheet.
- Real accounts (Spec 06). Today's sign-in is a **development-only** endpoint that the server
  refuses unless `APP_ENV=development`.
- iOS has not been built or tested. That needs macOS and Xcode.
- Hindi / Indian English / Hinglish accuracy has **not** been evaluated.

## Prerequisites

Versions this repository was verified with on 2026-11-16 (Windows 11, x64):

| Tool | Version | Used for |
|---|---|---|
| Docker Desktop (WSL 2 backend) | 29.9.3 / Compose v5.7.0 | Postgres, Redis, API, worker |
| Python | 3.13.17 | Backend tests outside Docker (image uses 3.12) |
| FFmpeg / ffprobe | 9.0.2 | Backend tests and the smoke test (image installs Debian's ffmpeg) |
| Flutter / Dart | 3.29.2 / 3.7.2 (stable) | Mobile app |
| JDK for Android builds | 21 (`flutter config --jdk-dir=...`) | Gradle 8.10 does not run on Java 25 |
| Android SDK | platform 35, build-tools 35.0.0, emulator | Android build and emulator |

## Quick start (backend)

```powershell
docker compose up -d            # postgres, redis, api (runs migrations), worker
curl http://localhost:8000/api/v1/health/ready
# {"status":"ready", ..., "checks":{"database":"ok","queue":"ok"}}
```

API docs: http://localhost:8000/docs. The API reloads on code changes. Stop with `docker compose down`.
Add `-v` to also delete the database, queue and stored media volumes.

End-to-end check against the running stack (generates a test clip; needs ffmpeg on PATH). It
uploads, validates, analyses, renders, verifies the export with ffprobe and deletes the project:

```powershell
backend\.venv\Scripts\python.exe scripts\smoke_e2e.py
```

## Backend development and tests

```powershell
py -3.13 -m venv backend\.venv
backend\.venv\Scripts\pip install -e "backend[dev]"
powershell -File scripts\check-backend.ps1     # ruff, ruff format --check, pytest
```

Tests use in-memory SQLite, a temp storage folder and Celery in eager mode, so no services are
needed. They run real ffmpeg/ffprobe on generated clips and inspect rendered output. To run the
same suite on PostgreSQL, point `TEST_DATABASE_URL` at a **throwaway** database (tables are dropped):

```powershell
docker compose exec postgres psql -U storyforge -d postgres -c "CREATE DATABASE storyforge_test"
$env:TEST_DATABASE_URL = "postgresql+psycopg://storyforge:storyforge_dev_only@localhost:5433/storyforge_test"
backend\.venv\Scripts\python.exe -m pytest backend\tests -q
```

Migrations (Alembic, in `backend/migrations`): `cd backend; .venv\Scripts\alembic upgrade head`.
The API container applies them on start.

## Mobile app

```powershell
cd mobile
flutter pub get
flutter test                    # unit + widget tests (run at 360 dp width)
flutter analyze
flutter run                     # Android emulator; API at http://10.0.2.2:8000 by default
```

On a physical phone, use your computer's LAN address:
`flutter run --dart-define=SF_API_BASE_URL=http://192.168.x.y:8000`. Plain HTTP is allowed in
**debug builds only** (`android/app/src/debug/AndroidManifest.xml`). Release builds require HTTPS.

The app contains no API keys. Provider credentials are server-side configuration only.

## Configuration

The backend reads environment variables (or `backend/.env`). Copy `.env.example` and keep real
values out of Git (`.env` is ignored). Key settings:

| Variable | Default | Notes |
|---|---|---|
| `APP_ENV` | `development` | Anything else disables dev sign-in and requires strong secrets |
| `SECRET_KEY` | dev placeholder | Signs session tokens. Must be 32+ random chars outside development |
| `STORAGE_SIGNING_SECRET` | dev placeholder | Signs upload/download links. Same rule |
| `DATABASE_URL`, `REDIS_URL` | local Compose services | |
| `LOCAL_STORAGE_ROOT` | `./media_data` | Private media folder (local adapter) |
| `MANIFEST_SCHEMA_PATH` | search repo | Compose mounts `EDIT_MANIFEST.schema.json` at `/schema/` |
| `MAX_UPLOAD_BYTES` | 1 GiB | Enforced on the grant and while streaming |
| `MAX_VIDEO_DURATION_SECONDS` | 900 | Checked with ffprobe |
| `SIGNED_URL_TTL_SECONDS` | 300 | Lifetime of upload/download links |
| `DEFAULT_MEDIA_RETENTION_DAYS` | 7 | Shown to users. **Automatic cleanup is not implemented yet** |
| `TRANSCRIPTION_PROVIDER`, `LLM_PROVIDER` | `mock` | Demo output, labelled `[DEMO]` |
| `VISUAL_SEARCH_PROVIDER` | `openverse` | Adapter exists; no UI yet |
| `IMAGE_GENERATION_PROVIDER` | `disabled` | |

No cloud resources, paid APIs or credentials are used anywhere in the current code.

## Repository layout

```text
backend/            FastAPI app, Celery workers, Alembic migrations, tests
  app/api/v1/       routes (projects, media, analysis, manifest, renders, jobs, storage, system)
  app/services/     ingest validation, FFmpeg renderer
  app/domain/       schemas, manifest rules
  app/storage/      storage adapter interface + local filesystem adapter
mobile/             Flutter app (Android; iOS untested)
  lib/core/         API client, models, providers
  lib/features/     auth, projects, editor, exports, settings
scripts/            check-backend.ps1, smoke_e2e.py
docker-compose.yml  local stack
EDIT_MANIFEST.schema.json   canonical edit format
```

## Known limitations

- Deleting a project removes database rows and files on the local storage volume. Docker volume
  snapshots or backups you make yourself are not touched.
- Retention is displayed but not enforced by a cleanup job.
- The local storage adapter is for development. An S3/R2 adapter with presigned URLs is planned.
- No rate limiting or per-user quotas yet beyond upload size and duration limits.
