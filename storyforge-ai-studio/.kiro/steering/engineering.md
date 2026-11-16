---
inclusion: always
---
# Engineering steering

- Prefer readable, typed, modular code over clever abstractions.
- Follow feature-first clean separation on Flutter: presentation, application, domain, data.
- Backend layers: API/router, schemas, domain/services, repositories, provider adapters, workers.
- Use Ruff/pytest/mypy (or equivalent verified tools) for Python; Dart format/analyze/test for Flutter.
- Add a test for each bug and meaningful behavior. No test weakening to hide failures.
- Avoid unbounded retries, synchronous media processing, blocking UI work and whole-file memory loads.
- Keep functions focused; document non-obvious timestamp, time-base, codec and filtergraph logic.
- Pin compatible dependency versions after verifying official current docs, platform support and license.
- Update docs, `.env.example`, OpenAPI and migration notes whenever behavior/config/API changes.
- No placeholder button should appear functional. Clearly label mock/demo modes.
