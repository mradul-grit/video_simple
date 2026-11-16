# Spec 04 — Non-destructive editor

- Show video preview and a simple time-aligned storyboard/timeline.
- Show distinct layers for source video, cuts, transcript captions, editorial captions, visuals and audio settings.
- Every edit is represented in versioned EditManifest and can be undone/redone.
- User can accept/reject/adjust cut proposals.
- User can edit caption wording, font, size, colour, background, alignment and safe-zone placement.
- User can select visual PIP/cutaway, timing, scale, crop, position and motion.
- Original media remains immutable; preview is a derived asset.
- Auto-save and optimistic concurrency protect against lost edits.
