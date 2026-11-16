# Mobile implementation specification

## Navigation
- Welcome / permissions and privacy explanation.
- Home: recent projects, New Video primary CTA, storage/job status.
- New Project: record/import, project title, language and output preset.
- Upload/Analysis: resumable progress, cancel/retry, stage status.
- Review: transcript, cut proposals, story beats, editorial captions and visual suggestions.
- Editor: large video preview; minimal timeline/storyboard; visible layers for source clips, cuts, transcript captions, editorial captions, visuals and audio; undo/redo; preview render.
- Export: preset/quality, job progress, completed export, share/save.
- Settings: language, privacy, retention, AI provider information, storage, help and delete-account/project controls.

## Editor interaction requirements
- Tap a proposed cut to accept/reject or adjust handles.
- Tap transcript segment to seek preview to its source timestamp.
- Tap editorial caption to edit text; display linked transcript span.
- Tap visual suggestion to preview source/license and choose PIP or full-frame cutaway.
- Drag/resize/position only within safe video bounds; provide reset.
- Motion: none/fade/zoom/slide; duration and intensity controls.
- Pinch/drag preview gestures must not conflict with timeline scroll.
- Autosave state; show saved/saving/offline indicators.
- Undo/redo for manifest mutations.

## Mobile quality
- Support Android API level compatible with current Flutter stable and verify actual platform requirements.
- Handle large video files without loading entire file into RAM.
- Use thumbnails/proxies for timeline.
- Preview playback and timeline scrubbing should not block UI.
- Respect platform permission models and temporary file paths.
- Handle low disk space, background/foreground transitions, upload interruption and OS process death.
- Add widget tests and at least one real-device integration test before beta.

## Design system
Dark-first creator studio; neutral surfaces; restrained warm accent; typography with clear hierarchy; high contrast; accessible touch targets; consistent radius/spacing tokens; skeleton/loading states; no fake buttons or decorative progress indicators that imply work is happening.
