# Spec 03 — Design

- Implement `VisualSearchProvider` protocol.
- Add Openverse adapter with license filters and complete attribution fields.
- Add Pixabay adapter only if API key is provided; cache per provider requirements, respect rate limits, download assets before persistent use and show attribution.
- Add optional ComfyUI adapter behind disabled-by-default configuration.
- Build relevance scoring using query match, aspect ratio, visual type, license eligibility and semantic model score if available.
- Store every suggestion and its origin/rights metadata. Preserve rights metadata to export credits.
- Never search from raw video frames or upload media to third-party services without explicit consent.
