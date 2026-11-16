# Spec 03 — Contextual visual suggestions

## Goal
Suggest relevant supporting images/illustrations/video clips at story-specific timestamps.

- Each visual beat contains transcript references, query terms, rationale, suggested start/end time and confidence.
- Search provider returns candidates with preview, provider, creator, source page, exact license and attribution fields.
- Default commercial workflow excludes non-commercial and no-derivatives licenses; unknown licenses are not auto-approved.
- User can preview, reject, replace, select and position candidate.
- Candidate placement supports picture-in-picture and full-frame cutaway.
- Motion presets support none/fade/slide/zoom with duration/intensity.
- Generated images are unavailable unless an approved local or paid provider is configured; cost and provider are disclosed.
- If provider is offline or returns no candidates, show graceful empty state and allow manual asset upload.
