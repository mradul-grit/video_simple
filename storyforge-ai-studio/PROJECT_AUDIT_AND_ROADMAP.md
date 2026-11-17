# StoryForge AI Studio: Project Audit and Roadmap

Audit date: 2026-11-16 (branch `main` at `6b5521c`). No application code was changed during the audit.
**Updated 2026-11-17 with Stabilization Milestone 1 (M1) results. See §0.** Sections 1–11 are the
original audit; where M1 changed a finding, §0 and the dashboard supersede it.

Status key: `[x]` complete and verified · `[~]` partial · `[ ]` not implemented · `[!]` needs improvement · `[?]` not verified

---

## 1. Executive summary

StoryForge is a **working prototype**. One video can go through the whole flow:
create project → upload → server validation → analysis → cut review → render → play the export.
This has been verified on the backend, against the Docker stack, and on an Android 35 emulator.

The core promise is not delivered yet:
- **No real AI.** The transcript and key-point captions are labelled placeholder text with fixed timestamps.
  Only pause detection is real.
- **No story-aware visuals.** This is the signature feature, and it has no UI and no rendering.
- **The editor is a cut-review screen,** not an editor. There's no caption editing, overlays, motion, undo/redo or autosave.

Compared with commercial tools (CapCut, Descript, Captions.ai, Opus Clip), StoryForge has a clean
foundation but roughly 15–20% of the product.

**Highest risk right now:** all 12 commits of work exist only on this laptop.
`origin/main` still holds only the blueprint commit.

## 0. Stabilization Milestone 1: verified results (2026-11-17)

Branch `fix/stabilization-m1`, pushed through `5597fdf`. On top of that: 14 modified and 7 new files,
uncommitted and awaiting approval. The audit document is kept separate from the application changes.

**Status key for this section:** **Verified** = executed and observed in this milestone ·
**Implemented** = code written and unit-tested only · **Unverified** = could not be checked.

### Results (all executed; none inferred)

| Check | Result | Status |
|---|---|---|
| Backend full suite (pytest, JUnit report) | **113/113** (0 failures, 0 errors, 0 skipped), 65 s | Verified |
| Backend lint / format / types | `ruff check .` clean (incl. migrations), 54 files formatted, mypy clean (43 files) | Verified |
| Migration round trip on PostgreSQL | upgrade → downgrade → upgrade; columns 136/136, indexes 28/28 and enums identical to live DB; `alembic check`: no drift | Verified |
| Original 7 failure probes + 4 controls, live Docker | **11/11 PASS** (the 7 had all failed in the audit) | Verified |
| Live review flow, Docker (upload → analysis → accept and adjust cut → re-analysis → render → export) | **15/15 PASS** | Verified |
| Repository smoke test `scripts/smoke_e2e.py`, Docker | PASS | Verified |
| Export format | **1080×1920 H.264 yuv420p + AAC**, fast-start; edited 10.40 s vs 10.35 s expected; A/V in sync | Verified |
| Flutter format / analyze / tests | 26 files unchanged; analyzer **no issues**; **36/36** tests (28 existing + 8 new error-compatibility tests) | Verified |
| Android emulator (API 35) on-device e2e, `scripts/run-device-e2e.ps1` | **PASS** (2 min 20 s, 11 screenshots). Backend recorded the app's render: completed, 10.40 s, 1080×1920 H.264, from the cut accepted in the app (6.164–7.861 s) | Verified |
| Earlier UI fixes on device (logo badge size, "1 suggested cut") | Confirmed in screenshots | Verified |
| GitHub Actions | Workflow moved to the repo root and pushed (`5597fdf`). **Run results not readable:** private repo, no token, no `gh` | **Unverified** |

### Audit failures: status after M1

| Audit finding | Fix | Status |
|---|---|---|
| Unpushed work | 12 commits on `origin/dev/storyforge-prototype`; backup branch `backup/pre-stabilization-6b5521c`; `origin/main` untouched | Verified |
| CI misplaced and failing | Root workflow (FFmpeg, ruff, mypy, pytest on SQLite + PostgreSQL, migration round trip, Flutter checks); migrations lint-clean | Implemented; CI run **Unverified** |
| Transcript and captions past the video end | `domain/timeline.py` clamps every analysis item; mock timeline scaled to the real duration | Verified (live probes + tests) |
| Re-analysis wipes decisions | Merge-saves: reviewed cuts and edited/decided captions kept; stable segment IDs | Verified (live + tests) |
| Cancelled job later completes | `services/job_state.py` atomic updates that apply only while a job is active; results and completion in one transaction; Celery revoke | Verified for analysis (live); validation, visual search and render start covered by tests |
| Error format ≠ `API_CONTRACT.md` | `api/errors.py` envelope `{error{code,message,field_errors,retryable}, request_id}`; safe request IDs; legacy `detail` kept | Verified (live + 8 Flutter compatibility tests) |
| No `/jobs/{id}/retry` | Endpoint added; same job ID, bounded by `max_retries`; permanent failures refused | Verified (live 409 refusal + tests) |
| No rate limiting | Redis fixed-window limits per user (per IP for dev login); 429 + `Retry-After`; lets requests through if Redis is down | Verified (live 429 + tests for every limited route) |
| **New regression found in M1:** cancelled validation could never be restarted | `/media/complete` re-runs the same job after a cancel (not counted as a retry) | Verified (live + test) |

### Remaining issues found or confirmed in M1

1. **Project deleted during a render can leave an orphaned export file.** Measured with real renders in a
   throwaway test. Deleted during ffmpeg: nothing left. Deleted after the output check but before storing:
   `output.mp4` is written after the purge. Short window (ffprobe check plus a file move), but it breaks
   the deletion requirement in `SECURITY_PRIVACY.md`. The worker also crashes with `ObjectDeletedError`
   instead of exiting cleanly. **High.**
2. **Render completion is not cancel-safe.** The final write does not check that the render is still
   active. No API can cancel a render today, so there is no user impact yet; it must be fixed before
   render cancel is added. **Medium.**
3. **Visual-search failure handler** (original code) uses an unguarded update, so a crash after a cancel
   records `failed` instead of `cancelled`. **Low.**
4. **The app reads legacy `detail`, not `error.message`.** Works because the alias is kept. A 500 shows
   "Internal Server Error" rather than the friendlier envelope message. **Low.**
5. **Fixed-window rate limits** allow up to twice the limit across a window boundary. Acceptable for MVP. **Low.**
6. **CI unverified** (see above). **High until confirmed.**
7. **Host stability:** Docker Desktop's engine stopped twice and the emulator exited between sessions;
   only about 1.3 GB RAM was free during the device run. Environment risk, not an app defect.

## 2. Architecture overview

```text
Flutter app (Riverpod, GoRouter, Dio, video_player, file_picker, secure storage)
   │  HTTPS (HTTP only in debug)                    signed, single-use upload/download URLs
   ▼
FastAPI /api/v1 ── PostgreSQL 16 (SQLAlchemy 2, Alembic 0001)
   │  Celery tasks via Redis 7
   ▼
Worker (1 process): ffprobe validation · silencedetect pauses · mock transcript/LLM · FFmpeg render · ffprobe verify
   │
Local filesystem storage volume (HMAC-signed links; S3/R2 adapter not built)
```

**Strengths**
- Clean layering: routes → repositories → services → worker.
- Every nested route checks ownership.
- Edit manifest validated by schema and semantic rules, with optimistic concurrency.
- FFmpeg called with argument arrays only (never through a shell).
- Exports are verified with ffprobe before being marked complete.

**Weaknesses**
- Storage is coupled to the local adapter: `get_storage()` returns `LocalFilesystemStorage`, and the protocol is unused.
- AI providers are `if` branches inside `tasks.py`, not adapter classes.
- A single worker queue: a long render blocks validation and analysis.
- Several settings exist but do nothing (see §8).

## 3. Technical verification (this audit)

Checks were run sequentially, with no overlapping processes.

| Check | Command | Result |
|---|---|---|
| Git state | `git status -sb` | Clean; **ahead of origin by 12 commits (unpushed)** |
| Backend lint | `ruff check app tests` | Pass |
| Backend format | `ruff format --check app tests` | Pass (46 files) |
| Backend types | `mypy app` | Pass (39 files) |
| Backend tests | `pytest` (SQLite, real ffmpeg) | **82/82 passed**, 60 s |
| CI-equivalent lint | `ruff check backend` (as in ci.yml) | **Fail**: 19 errors in `migrations/` |
| CI-equivalent format | `ruff format --check backend` | **Fail**: 1 file |
| Compose config | `docker compose config --quiet` | exit 0 |
| Containers | `docker compose ps` | api, worker up; postgres, redis healthy |
| Health | `/health/live`, `/health/ready` | 200 / 200 (`database ok`, `queue ok`) |
| DB / queue | alembic `0001`; `redis-cli ping`; `celery inspect ping` | 0001 / PONG / 1 node online |
| Smoke e2e | `scripts/smoke_e2e.py` | **Pass** (29 s): export H.264 1080×1920 yuv420p + AAC, 8.00 s; link 404 after delete |
| Failure probes | scratch script against live stack | **4 pass, 7 fail** (below) |
| Flutter checks | format, analyze, test | **Not re-run in this audit** (run interrupted). Last verified this session: analyze clean, **28/28 tests pass** |
| Android e2e | `scripts/run-device-e2e.ps1` | **Not re-run in this audit.** Last run passed on an Android 35 emulator (all 11 steps). The 4 UI fixes made after that run are covered by widget tests only |
| PostgreSQL test mode | `TEST_DATABASE_URL=...` | Passed earlier in the session (67 tests at the time); not re-run |

Failure and recovery probes against the running stack:

| Probe | Result |
|---|---|
| Junk file is rejected with a clear message and deleted | PASS |
| Tampered upload grant is refused (403) | PASS |
| Measured pause is proposed (1.66–2.66 s in a 4 s clip) | PASS |
| Job queued while the worker is down completes after restart | PASS |
| Error body matches the API contract `{error, request_id}` | **FAIL**: `{"detail": "..."}` |
| Demo transcript stays inside the video | **FAIL**: 4 of 5 segments start after a 4 s clip ends (fixed 0–25 s) |
| Captions stay inside the video | **FAIL**: 3 of 3 end after the video |
| Re-analysis keeps accepted cuts | **FAIL**: the decision is wiped and IDs change |
| Cancelled job stays cancelled | **FAIL**: the worker ran it and marked it `completed` |
| `POST /jobs/{id}/retry` (in the contract) | **FAIL**: 404, not built |
| Rate limiting (30 rapid creates) | **FAIL**: all 201 |

## 4. Feature checklist

### Product / UI
- [~] Authentication: development-only email sign-in, refused outside `APP_ENV=development`. No real accounts.
- [ ] Onboarding / permissions explainer
- [x] Home / project list with empty, loading and error states (widget tests + device)
- [x] Create project (title, language, preset) (device)
- [x] Navigation: Home, Exports, Settings tabs; project and editor routes (device)
- [~] Settings: read-only server, provider and privacy facts, plus sign-out. No language, retention or account controls.
- [!] Responsive design: tested at 360 dp. Editor review lists are cramped on small phones. Large text scale is not tested.
- [ ] Localization: all strings hard-coded English. No Hindi UI.
- [!] Session expiry: a 401 shows an error but does not sign the user out.
- [ ] Branding: default app icon.

### Uploads
- [x] File selection (file_picker) and type/size checks before upload
- [x] Explicit consent dialog (host, size, retention, demo-mode notice) (device)
- [x] Streamed upload with progress and cancel (device)
- [x] Server validation in worker: signature, ffprobe, size, duration (tests + live probe)
- [x] Probe timeout keeps the original and is retryable (tests)
- [ ] Resumable upload (restart from zero only)
- [!] A cancelled upload leaves an orphan `pending` media row
- [ ] In-app camera recording
- [ ] Recovery after the app is killed mid-upload

### AI
- [x] Pause detection from real audio (`silencedetect`, padded, confidence-scored, never auto-applied)
- [ ] Whisper transcription: adapter code exists, not installed or tested
- [ ] Hindi / Indian English / Hinglish: language setting stored only; no evaluation set
- [ ] Story analysis: Ollama adapter exists, not tested; mock only
- [!] Mock transcript ignores the real duration (bug, see §7)
- [ ] Filler-word detection (needs word timestamps)
- [~] Grounded captions: grounding enforced server-side, but the content is mock
- [ ] Visual suggestions: Openverse worker code and API exist; no UI; never verified live

### Editor
- [x] Source preview playback via signed URL (device)
- [x] Timeline strip: cut regions and caption markers, tap to seek
- [x] Transcript tap-to-seek
- [x] Accept / keep cut, result duration (device)
- [~] Cut handle adjustment: API supports it, no UI
- [ ] Caption text editing, styling, safe-zone placement
- [ ] Overlays, PIP or cutaway, transitions, zoom motion
- [ ] Undo / redo; autosave; local drafts (Drift planned, absent)
- [!] Re-analysis wipes the user's decisions
- [!] Preview link expires after 300 s. Long sessions or late seeks get 403 (by design of the TTL; not observed live).

### Rendering
- [x] FFmpeg cuts + concat, 1080×1920 scale/pad, yuv420p, faststart (tests + device)
- [x] A/V sync and duration verified by ffprobe; silence synthesised for silent sources
- [x] Audio chain (high-pass, denoise, loudnorm, limiter) and basic colour (render tests)
- [!] Loudness: single-pass loudnorm; no listening tests
- [ ] Caption burn-in, overlays, motion
- [ ] Other aspect ratios / resolutions (schema pins 1080×1920)
- [!] Progress is coarse (stage jumps 25 → 85%); no ffmpeg `-progress` parsing
- [ ] Render cancel
- [x] Export history and in-app playback (device)
- [ ] Save to gallery / share sheet

### Backend
- [x] Project CRUD, pagination, ownership checks (tests)
- [x] Manifest versioning + 409 conflicts (tests)
- [x] Alembic migration round trip on PostgreSQL
- [!] Error envelope differs from `API_CONTRACT.md`
- [!] Job cancel not honoured by the worker; no retry endpoint
- [~] Idempotency: validation and analysis keys yes; render enqueue has no idempotency key
- [ ] Structured logging, request IDs in logs, metrics
- [ ] Separate queues; worker concurrency is 1
- [!] Project delete is synchronous and does not stop running jobs

### Security
- [x] Ownership checks on every project, media, job and export route (IDOR tests)
- [x] HMAC upload/download links bound to method, key, expiry and size; single-use upload; expiry tested
- [x] Path traversal blocked; server-chosen storage keys
- [x] Dev secrets refused outside development; `.env` ignored; no keys in the app
- [!] JWT: no issuer/audience checks (the contract requires them); dev token valid 24 h
- [ ] Rate limits, quotas, per-user concurrency (`max_concurrent_jobs_per_user` unused)
- [ ] Retention enforcement (7 days is shown to users but not enforced)
- [!] Containers run as root; image ships dev dependencies (1.2 GB)
- [!] CORS `*` with credentials in development
- [ ] Dependency / container vulnerability scanning

### Testing
- [x] Backend unit + API tests with real FFmpeg (82)
- [x] Flutter unit + widget tests (28, last verified this session)
- [x] Docker smoke e2e
- [x] Android emulator e2e (passed once; screenshots in `mobile/build/e2e_screenshots`)
- [ ] Physical low-end Android device
- [ ] Load / concurrency tests; long-video tests (only clips of 12 s or less tested)
- [ ] Real phone footage (rotation, VFR, HDR, HEVC) not tested

### Deployment
- [~] Android: debug APK builds (minSdk 23, target 35). Release signing uses debug keys.
- [ ] iOS: never built; Info.plist lacks photo-library/camera usage strings
- [!] CI: `ci.yml` is in the wrong folder (never runs) and would fail lint/format and FFmpeg tests
- [ ] Monitoring, alerting, backups, production infrastructure, S3/R2 storage
- [!] Source control: 12 commits unpushed

## 5. UI/UX findings (from device screenshots)

**Good**
- Coherent dark design system and one clear primary action per screen.
- Honest demo banner wherever placeholder output appears.
- Clear consent copy; good empty and error states.
- The editor puts the preview first.

**Weak**
- The editor is cramped on a 360 dp phone: the preview plus timeline leave room for about one cut card.
- No caption preview on the video.
- No waveform or thumbnails on the timeline.
- Exports can't leave the app.
- Default launcher icon.
- No onboarding.
- No haptics or motion polish.
- Next to CapCut or Descript, it feels like an internal tool rather than a creator product.

## 6. Quality scorecard (out of 10)

| Area | Score | Good | Weak / must change |
|---|---|---|---|
| Architecture | 6 | Clean layers, async jobs, manifest as source of truth | Storage and AI not behind real adapters; one queue |
| Backend | 6 | Tested, typed, idempotent ingest, verified renders | Cancel/retry, error envelope, logging, quotas |
| Flutter app | 6 | Tested flows, secure token storage, robust polling | No drafts, no l10n, 401 handling, no codegen models |
| UI/UX | 5 | Consistent, honest states | Cramped editor, thin feature set, no brand |
| AI capabilities | 2 | Real pause detection; grounding rules | No transcription, analysis or visuals |
| Video editing experience | 2 | Cut review with preview and seek | No captions, overlays, undo, autosave |
| Rendering quality | 6 | Correct, verified 1080×1920 H.264/AAC | No captions or overlays; coarse progress; one format |
| Performance | 4 | Streams uploads; small clips are fast | Single worker; untested on long videos; machine-bound |
| Security | 5 | Ownership, signed links, secret guard | No real auth, rate limits, retention, root containers |
| Reliability | 5 | Retries, timeouts, recovery after worker restart | Cancel ignored; decisions wiped; no monitoring |
| Scalability | 3 | Stateless API, queue-based | Local storage, concurrency 1, no S3 |
| Production readiness | 2 | Docker stack, migrations | No auth, CI, backups, release signing, iOS |

**Overall: 4.3 / 10.** The engineering foundation is sound (about 6) but the product is about 2.

## 7. Critical bugs and technical debt

_M1 status: items 1–4, 6 and 7 are fixed (see §0). Items 5 and 8–12 remain open._

1. **Unpushed work**: 12 commits only on this laptop. *Critical.*
2. **Mock transcript ignores real duration**: segments and captions beyond the video end show in the editor. *High.*
3. **Re-analysis wipes accepted or rejected cuts** and changes IDs; any saved manifest captions then reference dead segment IDs. *High.*
4. **Job cancel not honoured**: the worker overwrites `cancelled` with `completed`. *High.*
5. **Preview/download links expire after 5 min** mid-session. *Medium.*
6. **CI broken and misplaced**: wrong folder; lint fails on migrations; no FFmpeg. *High.*
7. **Error format diverges from API_CONTRACT.md**; no `/jobs/{id}/retry`. *Medium.*
8. **Dead config**: `dev_auth_enabled`, `max_concurrent_jobs_per_user`, Pixabay, ComfyUI and S3 settings do nothing. *Low* (misleading).
9. **401 does not sign the user out.** *Medium.*
10. **Orphan pending media rows** after a cancelled upload. *Low.*
11. **Root containers and a 1.2 GB image** with dev tools. *Medium* (before any hosting).
12. **Hand-written client models** drift from OpenAPI. *Low.*

## 8. Production readiness

**Prototype.** Not suitable for external users:
- no real accounts;
- no real AI;
- no rate limits or retention;
- no backups or monitoring;
- no CI;
- no iOS;
- debug-signed Android.

## 9. Remaining work (prioritised)

### Essential for a private beta

| # | Task | Status | Problem | Solution | Priority | Depends on | Effort | Acceptance criteria |
|---|---|---|---|---|---|---|---|---|
| 1 | Push work to remote | [!] | 12 commits local only | Push `main` (needs your OK) | Critical | — | S | `origin/main` = `6b5521c` |
| 2 | Fix CI | [!] | Wrong path, fails | Move to repo-root `.github/`, install ffmpeg, lint scope, add mypy + flutter jobs | Critical | 1 | S | Green run on push |
| 3 | Stabilisation fixes | [!] | Bugs 2–5, 7, 9, 10 | Clamp/remove mock timestamps; preserve decisions on re-analysis; honour cancel (check status + revoke); refreshable preview URLs; contract error envelope + retry; 401 → sign-out | High | 2 | M | Each §3 probe that failed now passes; regression tests added |
| 4 | Real transcription | [ ] | Mock only | Faster-Whisper adapter (CPU int8 `small`, opt-in model download), word timestamps, language confidence | Critical | 3, model-download approval | L | Real transcript on recorded speech; segments inside duration; low confidence flagged |
| 5 | Hindi/Hinglish evaluation set | [ ] | No evidence | 20–30 consented clips, WER/CER report per language | High | 4 | M | Published per-language numbers in docs |
| 6 | Story analysis + grounded captions | [ ] | Mock only | Ollama adapter with JSON-schema validation, retries, deterministic fallback | High | 4 | L | Every caption cites real segments; schema-invalid output rejected |
| 7 | Caption editing + burn-in | [ ] | Read-only | Edit API + UI; ASS/drawtext burn-in in safe zones; style presets | Critical | 4 | L | Edited caption appears in export at the right time, inside the safe zone |
| 8 | Undo/redo + autosave + drafts | [ ] | None | Manifest mutation stack; debounced save with 409 handling; local draft cache | High | 7 | M | Survives app restart; conflict UI |
| 9 | Real accounts | [ ] | Dev login | Supabase Auth *or* Cognito (choose one); JWT iss/aud/exp checks | Critical | 3 | L | No dev login outside dev; auth tests |
| 10 | Quotas, rate limits, retention job | [ ] | None | Per-user limits, concurrency cap, Celery beat purge | High | 9 | M | 429 on abuse; expired media deleted, with test |
| 11 | Export to gallery / share | [ ] | In-app only | Download + gallery save + share sheet | High | — | S | MP4 lands in the gallery on device |
| 12 | Worker queues + render progress/cancel | [!] | One queue, coarse | Separate render queue, `-progress` parsing, cancel | Medium | 3 | M | Validation not blocked by renders; accurate %; cancel works |
| 13 | Real-footage + long-video tests | [ ] | Synthetic ≤12 s only | Phone clips (rotation, VFR, HEVC), 10–15 min clip | High | — | M | Correct orientation and sync; renders under the time budget |
| 14 | Physical low-end Android QA | [ ] | Emulator only | Test on 1 low-end + 1 mid device | High | 11 | S | E2E passes on both |
| 15 | Release build | [~] | Debug signing, default icon | Release keystore (kept out of Git), icon, version | High | 9 | S | Signed release APK/AAB installs |

### Signature feature (needed for the product promise)

| # | Task | Status | Priority | Depends on | Effort | Acceptance criteria |
|---|---|---|---|---|---|---|
| 16 | Visual suggestions UI | [ ] | High | 6 | L | Candidates with licence/creator shown per story beat; reject or select |
| 17 | Overlay render: PIP / cutaway + motion | [ ] | High | 16, 7 | XL | Selected asset appears at the chosen time and place with fade/zoom; speaker not covered by default |
| 18 | Licence/attribution through export | [ ] | High | 16 | M | Credits file/screen generated for CC BY assets |

### Optional / later
- iOS build and verification on macOS (M).
- S3/R2 storage adapter with presigned URLs (M).
- Monitoring and backups (M).
- Other aspect ratios (S).
- Image generation (ComfyUI) (L).
- In-app recording (M).
- Resumable uploads (M).
- OpenAPI-generated client models (S).
- Hindi UI localization (M).
- Non-root, slim production image (S).

**Remove or postpone**
- Pixabay and Pexels settings until there's an adapter.
- Image-generation settings.
- The unused `dev_auth_enabled` flag (replace it with the real auth switch).

## 10. Phased roadmap

1. **Stabilise (about 1 week):** items 1–3, 12 (queues/cancel). Every failed probe passes; CI is green.
2. **Real AI core (2–3 weeks):** items 4–6. Real transcript and grounded captions, measured on Hindi/Hinglish.
3. **Editor completion (2–3 weeks):** items 7, 8, 11, plus cut-handle UI and editor layout for small phones.
4. **Signature feature (3–4 weeks):** items 16–18.
5. **Security and production (2–3 weeks):** items 9, 10, 15, non-root image, scanning, backups.
6. **Scale and deploy (ongoing):** S3/R2, GPU worker profile, monitoring, iOS, items 13 and 14 on every release.

Order rationale:
- Captions, editing and visuals all depend on real word-timed transcripts, so AI comes before the editor.
- Auth can wait until just before outside testers.
- CI and bug fixes come first so the following phases build on a reliable base.

## 11. Recommended immediate next task

**Push the 12 local commits and fix CI** (items 1–2, effort S), then do the stabilisation fixes (item 3).
After that, real Whisper transcription, which unlocks every other AI and editor feature.

---

## Dashboard (updated after M1, 2026-11-17)

**DONE (verified):**
- Docker stack, health checks, migrations (round trip verified).
- Project CRUD with ownership isolation.
- Consented, signed, single-use streamed uploads with worker validation; timeout-safe retry; cancel and restart.
- Real pause detection.
- Analysis items always inside the video; re-analysis that keeps user decisions.
- Final cancellation; job retry endpoint; contract error format; rate limiting.
- Cut review (accept / keep / adjust) with preview, timeline and transcript seek.
- Manifest validation and versioning.
- 1080×1920 H.264/AAC rendering with audio/colour presets; export history and playback.
- Backend 113/113, Flutter 36/36, live probes 11/11, live review 15/15, Android emulator e2e.

**IN PROGRESS (implemented, not fully verified):**
- CI pipeline (pushed; results unread).
- Visual-suggestion backend (no UI; Openverse never called live).
- Cut-handle adjustment (API only).
- Dev-only authentication; read-only settings; debug-signed Android build.

**LEFT:**
- Real transcription, story analysis, filler detection, Hindi/Hinglish evaluation.
- Caption editing and burn-in; overlays, PIP/cutaway, motion; undo/redo, autosave, drafts.
- Gallery export and share.
- Real accounts, quotas, retention job.
- Resumable uploads, in-app recording.
- iOS; monitoring, backups, S3/R2; localization.

**NEEDS FIXING:**
- Orphaned export when a project is deleted mid-render (High).
- Render completion not cancel-safe (Medium, before render cancel ships).
- Visual-search failure overwriting cancel (Low).
- App still reading legacy `detail` (Low).
- Root containers and a 1.2 GB image; editor cramped on small phones; dead config.

**WORLD-CLASS SCORE:** **4.8 / 10** (was 4.3). Reliability rises from 5 to 7 and backend from 6 to 7:
cancel, retry, error and rate-limit behaviour is now correct and tested. Product scores are unchanged:
AI is still 2 and the editing experience still 2.

**RELEASE STATUS:** **Prototype** (stabilised).

**NEXT MOVE:**
1. Fix the deletion-during-render leak (small, privacy).
2. Confirm CI with a read-only token.
3. Start the functional Android video editor milestone (§0 of the next spec).
