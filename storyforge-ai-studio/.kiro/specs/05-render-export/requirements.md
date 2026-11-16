# Spec 05 — Rendering and export

- Render jobs run asynchronously and report queued/validating/rendering/finalizing/completed/failed/cancelled states.
- Renderer uses validated manifest and immutable input assets.
- Baseline MP4 output: 1080x1920, H.264, AAC, yuv420p, fast-start.
- Maintain A/V sync and expected duration; handle mixed source sizes, orientations and frame rates.
- Apply selected cuts, captions, visuals, zoom motion, audio filters and basic colour adjustments.
- Provide preview-quality and final-quality presets.
- Validate export using ffprobe before marking complete.
- Retry failure safely; no partial output is listed as completed.
- User can download/share or delete export.
