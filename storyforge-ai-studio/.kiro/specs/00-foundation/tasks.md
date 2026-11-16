# Spec 00 — Tasks

Status as of 2026-11-16. A box is ticked only when the check was actually run.

- [x] Inspect environment and verify Flutter/Dart/Python/Docker/Git availability.
      Windows 11 x64, 14 GB RAM; Docker 29.9.3 (WSL 2), Python 3.13.17, Flutter 3.29.2 / Dart 3.7.2,
      FFmpeg 9.0.2, Android SDK 35, JDK 21 for Gradle. No macOS/Xcode, so iOS is unverified.
- [x] Validate `docker compose config` and backend image build (`docker compose build`, exit 0).
- [x] Add safe liveness/readiness checks and backend test coverage.
      `/health/ready` returned `{"database":"ok","queue":"ok"}` against the Compose stack.
- [x] Scaffold Flutter app (`mobile/`, `flutter create --platforms=android,ios`).
- [x] Add design tokens and navigation shell with polished empty states
      (Home, New Project, Editor, Exports, Settings; no inert controls).
- [x] Add setup documentation (root README) and `.env.example` placeholders; `.env` is git-ignored.
- [x] Run Python formatting, lint and tests (`scripts/check-backend.ps1`: ruff, ruff format, pytest).
      Suite also passes on PostgreSQL via `TEST_DATABASE_URL`.
- [x] Run mypy (clean on `app/`; part of `scripts/check-backend.ps1`).
- [x] Run Flutter format/analyze/test (`dart format`, `flutter analyze`: no issues, `flutter test`).
- [ ] Build and run on an Android emulator or device (debug APK build in progress; not yet run on a device).
- [ ] CI pipeline (deferred until commands are stable; must not need secrets).
- [x] Record outputs and limitations (README "Known limitations"; this file).

## Assumptions recorded
- Python 3.13 locally, 3.12 in the Docker image; both satisfy `requires-python >=3.12`.
- Flutter is kept at 3.29.2 (installed). `flutter pub add` resolved riverpod 3.3, go_router 17,
  dio 5.11, file_picker 11, video_player 2.10, flutter_secure_storage 10 for Dart 3.7.
  APIs used were checked against the package sources in the local pub cache.
- Gradle 8.10 (from the Flutter 3.29 template) cannot run on Java 25, so Flutter is pinned to JDK 21.
