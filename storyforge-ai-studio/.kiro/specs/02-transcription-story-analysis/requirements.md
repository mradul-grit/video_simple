# Spec 02 — Transcription and story analysis

## Goal
Turn speech into timestamped transcript, story beats, reviewable cut proposals and concise editorial captions.

- User can choose language: auto, Hindi, Indian English or supported multilingual option.
- System stores detected language and confidence.
- Transcript segments have stable IDs, start/end timestamps, text and confidence when available.
- VAD identifies speech and pauses, but pauses alone never prove content is unnecessary.
- Cut proposals include source time range, reason, confidence and reversible status.
- Filler words are identified with source spans; user can accept/reject each proposal.
- Editorial captions are separate from verbatim transcript captions.
- Every editorial caption references one or more transcript segment IDs and must not introduce unsupported facts.
- Low-confidence transcription or caption grounding is clearly marked for review.
- Analysis runs asynchronously and can be retried idempotently.
