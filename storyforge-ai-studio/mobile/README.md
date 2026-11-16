# Flutter mobile application

This directory contains the mobile-app implementation requirements. Kiro should scaffold a native Flutter project here after verifying Flutter and platform tooling are available:

```bash
flutter create --project-name storyforge_mobile --platforms=android,ios .
```

Do not run this if the directory already contains a Flutter app. Before choosing package versions, verify the current stable Flutter/Dart SDK, package maintenance, Android Gradle Plugin, Kotlin and iOS deployment compatibility.

## Required architecture
- Flutter/Dart, feature-first structure.
- Riverpod, GoRouter, Dio, Drift/SQLite, flutter_secure_storage.
- Camera/import, video_player preview and resumable uploads.
- Typed API models generated from the backend OpenAPI/schema.
- Keep presentation, application state, domain models and data repositories separate.
- No AI provider keys in the mobile app.
- Use backend rendering for MVP; do not add FFmpegKit (upstream is retired).

See `APP_IMPLEMENTATION_SPEC.md` and `.kiro/specs/`.
