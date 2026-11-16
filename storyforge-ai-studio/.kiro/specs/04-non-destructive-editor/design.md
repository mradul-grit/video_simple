# Spec 04 — Design

- Treat `EDIT_MANIFEST.schema.json` as canonical and extend by versioned migration, not informal JSON.
- Build editor state as immutable manifest snapshots and command-based undo/redo.
- Timeline uses seconds internally, converts to frame/time-base only at render boundary.
- Use thumbnail/proxy assets, not full-resolution video decode for the entire timeline.
- Preview uses video_player or a verified Flutter-compatible preview layer; final render remains backend.
- Enforce safe zones for social overlays; give user composition presets.
