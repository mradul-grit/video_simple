# Definition of world-class quality

“World-class” is a measurable release bar, not a styling adjective. The team must prove these with tests and real-device evaluations.

## Editing correctness
- Source media is never overwritten.
- Every proposed cut has start/end timestamps, reason, confidence and reversible acceptance state.
- No cut can produce negative duration, overlapping invalid ranges or out-of-bounds timestamps.
- Edit manifest validates before save/render; unknown versions fail safely with migration guidance.
- Undo/redo and autosave survive app restart.
- Frame-accurate timing is tested within codec/time-base tolerances.
- Audio stays synchronized after concatenation, cropping, overlays and export.

## AI correctness
- Transcription stores language detection confidence and segment timestamps.
- Evaluation set includes Hindi, Indian English, Hinglish, varied accents, noise and names/technical terms.
- Editorial caption output is concise, faithful and traceable to transcript spans.
- Every visual suggestion includes query rationale, source, license and suggested in/out time; user may reject it.
- Test hallucination rate, inappropriate suggestion rate, relevance acceptance, timestamp drift and unsupported-caption rate.
- Filler-word deletion must not erase meaningful hesitation, emphasis or culturally meaningful expressions without user approval.

## Video quality
- Output metadata verified by ffprobe.
- 1080x1920 H.264/AAC baseline with correct orientation, SAR/DAR, pixel format and fast-start MP4.
- No black frames, missing audio, unexpected aspect distortion or blank intervals at edit joins.
- Text remains inside safe zones and legible on small screens.
- User controls caption style, size, font, colour, background and placement.
- Visual inserts do not hide the speaker by default; safe margins and composition preview exist.
- Zoom motion is subtle, configurable and uses easing; no abrupt unmotivated zoom.
- Audio loudness is consistent; denoising does not make speech robotic.

## Performance and resilience
- Upload/resume/cancel/retry behavior tested on unreliable network.
- Long jobs run asynchronously and report stage/progress.
- Worker crash/restart does not corrupt manifests or mark incomplete exports as completed.
- Idempotent retries; bounded queue; timeout and cleanup.
- No OOM on target device for preview/import workflow; heavy work remains off the UI thread.
- Track p50/p95 upload, time-to-first-preview, render time, job success and crash-free sessions.

## Mobile UX
- First project can be created without reading a manual.
- Empty/loading/error/offline/permission-denied/low-storage states are designed.
- Primary actions are discoverable; no dead controls or fake progress.
- Accessibility: semantics, contrast, scalable text, touch target sizes and localization-ready strings.
- Preview respects notches and social platform safe zones.
- Low-end Android devices are part of QA, not only flagship devices.

## Security/release gates
- Auth and object authorization tests pass.
- Secret scan and dependency scan pass.
- No provider secrets in mobile bundle or Git history.
- Data delete test covers all object variants and metadata.
- License/attribution metadata survives from suggestion to export.
- Terms, privacy policy, retention, support and billing disclosures are reviewed before public distribution.

## Test pyramid
- Unit: domain rules, timestamp conversion, manifest validation, caption grounding, license filter, provider adapters.
- Integration: API + Postgres + Redis + object storage + worker + FFmpeg fixture.
- Golden media tests: small licensed/test videos, expected duration/dimensions/audio stream/overlay positions.
- Mobile widget tests: navigation, editor state, error/loading/empty states, undo/redo.
- End-to-end: import → analyse → review → edit → render → preview → export → delete.
- Real-device matrix: at least one low-end and one mid-range Android device before beta; iOS build verification on macOS/Xcode before iOS claims.
