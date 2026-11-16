# Spec 02 — Design

- Define `TranscriptionProvider`, `VoiceActivityProvider` and `StoryAnalysisProvider` interfaces.
- Implement Faster-Whisper adapter with configurable model/device/compute type and lazy model loading.
- Implement VAD adapter and configurable pause/filler policies.
- Use Ollama adapter for local structured story analysis; use strict JSON schema and validation.
- Introduce a deterministic mock provider only for tests/demo mode.
- Store transcript, story beats, cut suggestions and editorial captions as structured versioned artifacts.
- Prompt engineering must include instruction that transcript is untrusted content and cannot override system instructions.
- Editorial captions must carry source segment IDs; reject captions with no traceable support.
- Build golden evaluation set before claiming Hinglish accuracy.
